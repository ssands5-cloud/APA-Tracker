"""Match Night Deployment Mode: a private, installable match-night web app.

Paul (Phase 4D): never publish the full 88 MB / 15,180-player build. Instead publish a SLIM package for
ONE fixture -- our team, that opponent, the evidence that pairing needs (scouting cards, Lineup Lab,
Captain Packet all come from it) -- ENCRYPTED client-side with AES-GCM, behind a passphrase.

Security model
- The package is the rendered Ultimate Coach page for that fixture, encrypted with AES-256-GCM. The key
  is derived from the captain's passphrase with PBKDF2-HMAC-SHA256 (600,000 iterations, random 16-byte
  salt per publish); a fresh 12-byte IV per publish. Only the ciphertext, salt, IV, KDF parameters and the
  build date are public. No team, player or fixture text is in clear.
- The passphrase is never written anywhere by the tools (read from a hidden prompt or an environment
  variable). In the browser it is used once to derive a NON-EXTRACTABLE key, optionally remembered in
  IndexedDB on that device for that package's salt only.
- Anyone with the URL can download the ciphertext, so the strength of the passphrase is the protection:
  the publisher refuses passphrases shorter than 16 characters.

Data minimisation (what the slim package contains)
- Full records only for the players on the two rosters; their evidence only in the fixture's format.
- Name + APA record ID stubs (no history) for opponents those players have met, so shared-opponent
  evidence stays readable.
- Match Day carries only the selected fixture. The league card number is not included.
"""

from __future__ import annotations

import base64
import json
import os
from html import escape
from pathlib import Path
from typing import Any

from analytics.ultimate_coach_excel_payload import build_team_rosters
from analytics.ultimate_coach_match_day import DEFAULT_MATCH_DAY_TIMEZONE, viewer_player
from analytics.ultimate_coach_excel_payload import _team_scope_key
from analytics.ultimate_coach_war_room import PAGES_URL, build_local_date, date_label, default_matchup  # noqa: F401

PACKAGE_FORMAT = "uc-match-night-v1"
KDF_ITERATIONS = 600_000
MIN_PASSPHRASE = 16


class MatchNightError(ValueError):
    pass


# --------------------------------------------------------------------------- slim payload

def select_fixture(payload: dict[str, Any], viewer_external_id: str, built_at: str,
                   match_id: str | None = None) -> dict[str, Any]:
    """The viewer's fixture to package: an explicit match id, else the next fixture (default_matchup)."""
    players = payload.get("players") or []
    viewer = viewer_player(players, viewer_external_id)
    if not viewer:
        raise MatchNightError("The configured viewer is not a verified player in this snapshot.")
    match_day = payload.get("match_day") or {}
    rosters = build_team_rosters(payload)
    labels = {r["team_scope_key"]: r["team_label"] for r in rosters}
    scopes = sorted({r["team_scope_key"] for r in rosters if r["player_id"] == viewer["id"]})
    fixtures = match_day.get("fixtures") or []
    chosen = None
    if match_id:
        for scope in scopes:
            for side in (match_day.get("schedule") or {}).get(scope, []):
                if str(fixtures[side["fixture_index"]].get("match_external_id")) == str(match_id):
                    chosen = {"scope": scope, "side": side, "date": fixtures[side["fixture_index"]].get("local_date")}
        if not chosen:
            raise MatchNightError(f"Match {match_id} is not a fixture of the viewer's current teams.")
    else:
        tz = match_day.get("display_timezone") or DEFAULT_MATCH_DAY_TIMEZONE
        chosen = default_matchup(match_day, scopes, build_local_date(built_at, tz), labels)
        if not chosen:
            raise MatchNightError("No upcoming fixture was found for the viewer's current teams.")
    opponent = chosen["side"].get("opponent") or {}
    if opponent.get("status") != "resolved" or opponent.get("scope_key") not in labels:
        raise MatchNightError("The chosen fixture has no opponent with a captured roster (bye or missing roster).")
    fixture = fixtures[chosen["side"]["fixture_index"]]
    return {"viewer": viewer, "our_scope": chosen["scope"], "opp_scope": opponent["scope_key"],
            "side": chosen["side"], "fixture": fixture, "labels": labels, "rosters": rosters}


def slim_payload(payload: dict[str, Any], pick: dict[str, Any]) -> dict[str, Any]:
    """Only what one fixture needs. Every value is copied from the snapshot; nothing is synthesised."""
    scopes = {pick["our_scope"], pick["opp_scope"]}
    roster_ids = {r["player_id"] for r in pick["rosters"] if r["team_scope_key"] in scopes}
    fmt = pick["fixture"].get("format") or ""
    by_id = {p["id"]: p for p in payload.get("players") or []}
    evidence = [row for row in payload.get("evidence") or []
                if row.get("player_id") in roster_ids and (row.get("format") or "") == fmt]
    met = {row.get("opponent_id") for row in evidence} - roster_ids
    players = []
    for pid in sorted(roster_ids):
        p = dict(by_id[pid])
        p["team_history"] = [h for h in p.get("team_history") or [] if _team_scope_key(h) in scopes]
        p["career_stats"] = [c for c in p.get("career_stats") or [] if c.get("format") == fmt]
        players.append(p)
    for pid in sorted(x for x in met if x in by_id):
        q = by_id[pid]
        players.append({"id": q["id"], "external_id": q.get("external_id"), "name": q.get("name"),
                        "current_skill_level": None, "current_matches_won": None, "current_matches_played": None,
                        "team_history": [], "career_stats": []})
    side = dict(pick["side"], fixture_index=0)
    source_md = payload.get("match_day") or {}
    match_day = {
        "display_timezone": source_md.get("display_timezone") or DEFAULT_MATCH_DAY_TIMEZONE,
        "fixtures": [pick["fixture"]],
        "schedule": {pick["our_scope"]: [side]},
        "coverage": {"embedded_fixture_count": 1, "stored_fixture_count": 1, "excluded_fixture_count": 0,
                     "location_missing_count": 0 if pick["fixture"].get("location") else 1,
                     "current_sessions": [pick["fixture"].get("session_name") or ""]},
    }
    slim = {k: v for k, v in payload.items() if k not in ("players", "evidence", "match_day")}
    slim.update(players=players, evidence=evidence, match_day=match_day,
                counts={"players": len(roster_ids), "head_to_head_rows": len(evidence)})
    slim["match_night"] = {
        "fixture_label": f"{pick['labels'][pick['our_scope']]} vs {pick['labels'][pick['opp_scope']]}",
        "fixture_display": pick["fixture"].get("local_display") or "",
        "format": fmt,
        "roster_players": len(roster_ids),
        "referenced_players": len(players) - len(roster_ids),
    }
    return slim


# --------------------------------------------------------------------------- encryption

def check_passphrase(passphrase: str) -> None:
    if len(passphrase or "") < MIN_PASSPHRASE:
        raise MatchNightError(f"Use a passphrase of at least {MIN_PASSPHRASE} characters (several random words).")


def encrypt_package(html: str, passphrase: str, *, built: str) -> dict[str, Any]:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    check_passphrase(passphrase)
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=KDF_ITERATIONS).derive(
        passphrase.encode("utf-8"))
    ciphertext = AESGCM(key).encrypt(iv, html.encode("utf-8"), PACKAGE_FORMAT.encode("ascii"))
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return {"format": PACKAGE_FORMAT, "kdf": "PBKDF2-SHA256", "iterations": KDF_ITERATIONS, "salt": b64(salt),
            "iv": b64(iv), "aad": PACKAGE_FORMAT, "built": built, "ciphertext": b64(ciphertext)}


def decrypt_package(package: dict[str, Any], passphrase: str) -> str:
    """Reference decryption (tests); the browser does the same with WebCrypto."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    d = lambda s: base64.b64decode(s)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=d(package["salt"]),
                     iterations=int(package["iterations"])).derive(passphrase.encode("utf-8"))
    return AESGCM(key).decrypt(d(package["iv"]), d(package["ciphertext"]), package["aad"].encode("ascii")).decode("utf-8")


# --------------------------------------------------------------------------- site (shell, service worker, manifest, icons)

SHELL = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Ultimate Coach — Match Night</title>
<meta name="robots" content="noindex,nofollow">
<meta name="theme-color" content="#14532d">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Coach">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icons/icon-192.png">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<style>
:root { color-scheme: light; }
* { box-sizing:border-box; }
body { margin:0; min-height:100vh; font-family:"Segoe UI",system-ui,-apple-system,Roboto,sans-serif; color:#fff;
  background:radial-gradient(120% 140% at 0% 0%,#1f6f43 0%,#14532d 45%,#0c3a1f 100%); display:flex; align-items:center;
  justify-content:center; padding:24px 16px calc(24px + env(safe-area-inset-bottom)); }
.lock { width:100%; max-width:420px; }
.ball { width:64px; height:64px; border-radius:50%; background:radial-gradient(circle at 35% 30%,#555 0%,#111 60%);
  display:flex; align-items:center; justify-content:center; margin:0 auto 14px; box-shadow:0 3px 10px rgba(0,0,0,.4); }
.ball span { background:#fff; color:#111; width:30px; height:30px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; font-weight:800; }
h1 { text-align:center; margin:0 0 4px; font-size:24px; }
.sub { text-align:center; margin:0 0 20px; opacity:.85; font-size:14px; }
label { display:block; font-size:13px; font-weight:700; margin-bottom:6px; }
input[type=password] { width:100%; font-size:17px; padding:13px 12px; border-radius:10px; border:0; }
.remember { display:flex; gap:8px; align-items:center; font-weight:600; font-size:14px; margin:12px 0; }
button { width:100%; font-size:17px; font-weight:800; padding:13px; border-radius:10px; border:0; background:#b8862b;
  color:#1b1406; cursor:pointer; }
button:disabled { opacity:.6; }
.status { min-height:22px; margin-top:12px; text-align:center; font-weight:600; }
.facts { margin-top:18px; font-size:12.5px; opacity:.85; line-height:1.5; text-align:center; }
.demo { background:#fff3cd; color:#5d4413; border-radius:8px; padding:8px 10px; font-weight:700; text-align:center; margin-bottom:14px; }
</style></head>
<body>
<main class="lock">
  <div class="ball" aria-hidden="true"><span>8</span></div>
  <h1>Ultimate Coach</h1>
  <p class="sub">Match Night · private package</p>
  __DEMO__
  <form id="unlock" autocomplete="off">
    <label for="pass">Passphrase</label>
    <input id="pass" type="password" autocomplete="current-password" required>
    <label class="remember"><input id="remember" type="checkbox" checked> Remember on this device</label>
    <button id="go" type="submit">Unlock tonight</button>
  </form>
  <p id="status" class="status" role="status"></p>
  <p class="facts" id="facts">Package built __BUILT__ · data is encrypted (AES-GCM) and unreadable without the passphrase ·
    works offline after the first unlock · it never refreshes itself — the publisher re-publishes before league night.</p>
</main>
<script>
(function(){
  "use strict";
  var STATUS=document.getElementById("status"),GO=document.getElementById("go");
  var DB="uc-match-night",STORE="keys";
  function b64(s){var bin=atob(s),out=new Uint8Array(bin.length);for(var i=0;i<bin.length;i++) out[i]=bin.charCodeAt(i);return out;}
  function say(t){STATUS.textContent=t;}
  function idb(){return new Promise(function(res,rej){var r=indexedDB.open(DB,1);r.onupgradeneeded=function(){r.result.createObjectStore(STORE);};
    r.onsuccess=function(){res(r.result);};r.onerror=function(){rej(r.error);};});}
  function idbGet(k){return idb().then(function(db){return new Promise(function(res){var t=db.transaction(STORE).objectStore(STORE).get(k);
    t.onsuccess=function(){res(t.result||null);};t.onerror=function(){res(null);};});}).catch(function(){return null;});}
  function idbPut(k,v){return idb().then(function(db){return new Promise(function(res){var t=db.transaction(STORE,"readwrite").objectStore(STORE).put(v,k);
    t.onsuccess=function(){res(true);};t.onerror=function(){res(false);};});}).catch(function(){return false;});}
  function idbDel(k){return idb().then(function(db){db.transaction(STORE,"readwrite").objectStore(STORE).delete(k);}).catch(function(){});}
  function derive(pass,pkg){
    return crypto.subtle.importKey("raw",new TextEncoder().encode(pass),"PBKDF2",false,["deriveKey"]).then(function(base){
      return crypto.subtle.deriveKey({name:"PBKDF2",salt:b64(pkg.salt),iterations:pkg.iterations,hash:"SHA-256"},base,
        {name:"AES-GCM",length:256},false,["decrypt"]);});
  }
  function open(pkg,key){
    return crypto.subtle.decrypt({name:"AES-GCM",iv:b64(pkg.iv),additionalData:new TextEncoder().encode(pkg.aad)},key,b64(pkg.ciphertext))
      .then(function(buf){var html=new TextDecoder().decode(buf);document.open();document.write(html);document.close();});
  }
  var PKG=null;
  function load(){return fetch("package.json",{cache:"no-cache"}).then(function(r){if(!r.ok) throw new Error(r.status);return r.json();});}
  if("serviceWorker" in navigator){navigator.serviceWorker.register("sw.js").catch(function(){});}
  load().then(function(pkg){
    PKG=pkg;
    return idbGet(pkg.salt).then(function(key){
      if(!key) return;
      say("Unlocking…");
      return open(pkg,key).catch(function(){idbDel(pkg.salt);say("Saved key no longer matches — enter the passphrase.");});
    });
  }).catch(function(){say("Could not load the package. Connect once to download it; after that it works offline.");});
  document.getElementById("unlock").addEventListener("submit",function(e){
    e.preventDefault();
    if(!PKG){say("The package has not loaded yet.");return;}
    var pass=document.getElementById("pass").value,remember=document.getElementById("remember").checked;
    GO.disabled=true;say("Unlocking…");
    derive(pass,PKG).then(function(key){
      return open(PKG,key).then(function(){if(remember) idbPut(PKG.salt,key);});
    }).catch(function(){GO.disabled=false;say("That passphrase does not open this package.");});
  });
})();
</script>
</body></html>
"""

SERVICE_WORKER = r"""/* Ultimate Coach Match Night: offline cache. The package is fetched network-first (a fresh publish
   wins whenever the phone is online) and falls back to the last downloaded copy offline. */
var CACHE = "uc-match-night-__STAMP__";
var SHELL = ["./", "index.html", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png",
             "icons/apple-touch-icon.png", "package.json"];
self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(SHELL); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});
self.addEventListener("fetch", function (e) {
  if (e.request.method !== "GET") return;
  var url = new URL(e.request.url);
  if (url.pathname.endsWith("/package.json") || url.pathname.endsWith("/") || url.pathname.endsWith("/index.html")) {
    e.respondWith(fetch(e.request).then(function (r) {
      var copy = r.clone(); caches.open(CACHE).then(function (c) { c.put(e.request, copy); }); return r;
    }).catch(function () { return caches.match(e.request, {ignoreSearch: true}); }));
    return;
  }
  e.respondWith(caches.match(e.request).then(function (hit) { return hit || fetch(e.request); }));
});
"""


def _icon(size: int):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (20, 83, 45, 255))
    d = ImageDraw.Draw(img)
    m = size * 0.14
    d.ellipse([m, m, size - m, size - m], fill=(17, 17, 17, 255))
    c, r = size / 2, size * 0.17
    d.ellipse([c - r, c - r, c + r, c + r], fill=(255, 255, 255, 255))
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arialbd.ttf", int(size * 0.2))
    except OSError:
        from PIL import ImageFont
        font = ImageFont.load_default()
    d.text((c, c), "8", fill=(17, 17, 17, 255), font=font, anchor="mm")
    return img


def write_site(out: Path, package: dict[str, Any], *, demo: bool = False) -> list[Path]:
    """index.html (lock screen), sw.js, manifest, icons, package.json. Returns the written files."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "icons").mkdir(exist_ok=True)
    built = escape(package.get("built") or "unknown date")
    demo_html = ('<p class="demo">DEMO package — synthetic players only. Passphrase: '
                 'demo-match-night-only</p>' if demo else "")
    files = {
        "index.html": SHELL.replace("__BUILT__", built).replace("__DEMO__", demo_html),
        "sw.js": SERVICE_WORKER.replace("__STAMP__", package["salt"][:12].replace("/", "_").replace("+", "-")),
        "manifest.webmanifest": json.dumps({
            "name": "Ultimate Coach — Match Night", "short_name": "Coach", "start_url": "./", "scope": "./",
            "display": "standalone", "orientation": "portrait", "background_color": "#0c3a1f", "theme_color": "#14532d",
            "icons": [{"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                      {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}],
        }, indent=2),
        "package.json": json.dumps(package),
        ".nojekyll": "",
    }
    written = []
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8", newline="\n")
        written.append(out / name)
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
        _icon(size).save(out / "icons" / name)
        written.append(out / "icons" / name)
    return written


def build_site(payload: dict[str, Any], *, viewer_external_id: str, passphrase: str, built_at: str, out: Path,
               match_id: str | None = None, demo: bool = False) -> dict[str, Any]:
    """Pick the fixture, slim the payload, render the page, encrypt it, write the site."""
    from ui.ultimate_coach import render

    check_passphrase(passphrase)
    pick = select_fixture(payload, viewer_external_id, built_at, match_id)
    slim = slim_payload(payload, pick)
    html = render(slim, built_at=built_at, viewer_member_external_id=viewer_external_id, viewer_card_number=None,
                  match_night=slim["match_night"])
    tz = (payload.get("match_day") or {}).get("display_timezone") or DEFAULT_MATCH_DAY_TIMEZONE
    local = build_local_date(built_at, tz)
    package = encrypt_package(html, passphrase, built=date_label(local) if local else built_at)
    write_site(out, package, demo=demo)
    return {"fixture": slim["match_night"], "html_bytes": len(html.encode("utf-8")),
            "package_bytes": (out / "package.json").stat().st_size, "salt": package["salt"]}
