# Match Night Deployment Mode (Phase 4D)

Ultimate Coach on a phone during live APA matches, as a **private match-night web app** rather than a
public data repository.

**URL:** https://ssands5-cloud.github.io/APA-Tracker/ (GitHub Pages, `gh-pages` branch)

**Source of this design.** Paul's Phase 4D directive asked for a GitHub Pages deployment with Homepage =
Tonight. Before publishing, Claude asked him directly in the Claude Code session, on 2026-10-07, how to
handle the fact that Pages is public while the full build holds every player's records. Paul answered
in that session:

> "Implement Match Night Deployment Mode. Do not deploy full 88 MB public builds. Generate slim
> fixture-specific packages containing only: selected team, selected opponent, relevant evidence,
> scouting cards, lineup lab, captain packet. Encrypt package client-side using AES-GCM. Require
> passphrase before loading. Support: GitHub Pages, Add to Home Screen, Phone usage, Offline caching."

He later added: "Don't publish real data or handle my real passphrase until the publishing safeguards
are verified."

## What is published
GitHub Pages sites from this repository are **public**, so the full build (88 MB, 15,180 players) is
never published. Instead `scripts/build_match_night_package.py` publishes one **fixture-specific**
package:

| Included | Not included |
|---|---|
| Our roster and the opponent's roster: full records (team scope, SL, team W-L, league lifetime in the fixture's format) | Any other team's roster or history |
| Those players' recorded games in the fixture's format (evidence for the matrix, sends, risks, cards, Lineup Lab, Captain Packet, meetings) | Other formats; other players' games |
| Name and APA record ID only for opponents those players have met (so shared-opponent evidence is readable) | Their histories |
| That one fixture on Match Day | The rest of the schedule; the league card number |

The page inside is the normal Ultimate Coach cockpit, in match-night mode: a compact header and a
banner naming the fixture. Tonight comes first: the match, best sends, dangerous opponents and open
risks, then the counts.

## Security model
- The rendered page is encrypted with **AES-256-GCM**.
  - The key comes from the passphrase via **PBKDF2-HMAC-SHA256, 600,000 iterations**, with a random 16-byte salt and 12-byte IV for every publish.
  - Decryption happens in the browser (WebCrypto).
- Publicly visible: the ciphertext, salt, IV, KDF parameters and the build date. No player, team or fixture text is in clear (tested).
- The passphrase is **never printed or saved** by the tools. It comes from a hidden prompt or the `UC_MATCH_NIGHT_PASSPHRASE` environment variable, and it must be at least 16 characters. Use several random words.
- On the phone, "Remember on this device" stores a **non-extractable** key in IndexedDB, valid only for that package. Each publish uses a new salt, so after a re-publish you enter the passphrase once more.
- Anyone can download the ciphertext and try passwords offline: the passphrase's strength is the protection. Old packages remain, encrypted, in the `gh-pages` history (no force-pushes).
- `noindex` is set, but the URL itself is not a secret.

## First unlock vs. launching from the Home Screen
- **First open (and after every re-publish):** the lock screen appears, showing "Package built <date>".
  Enter the passphrase once; Tonight opens.
- **Later launches from the Home Screen:** with "Remember on this device" checked, the saved key opens
  the package straight into **Tonight**, with no passphrase. Homepage = Tonight applies from this point
  on. This works offline once the phone has downloaded the package.
- After a re-publish (new salt), the saved key no longer fits, so the lock screen asks once more.
- A **DEMO** package says so on the lock screen, in a banner, above Tonight and in the printed packet. A
  remembered or offline launch can therefore never present the synthetic demo as a real match.

## Offline cache
- The service worker keeps only its own caches (prefix `uc-match-night-`). Caches of other projects on
  the shared `ssands5-cloud.github.io` origin are never removed.
- The package is fetched network-first. A 404/5xx response never replaces the last good copy; the
  cached package is served instead.

## Publish (the captain or whoever runs the builds)
```powershell
.\tools\publish_match_night.ps1                  # next fixture; prompts for the passphrase (hidden, twice)
.\tools\publish_match_night.ps1 -MatchId 51419770
.\tools\publish_match_night.ps1 -Demo            # synthetic demo package, no real data
```
What it does (`scripts/publish_match_night.py`, fail-closed). Before anything is built, deleted,
copied, fetched or checked out, it checks:
- The checkout is the canonical repository: exact common git dir and `origin` URL.
- The build folder is exactly `<repo>/tmp/match_night_site`.
- The Pages checkout is the linked worktree `.worktrees/gh-pages` of that repository, on branch
  `gh-pages`, with **no uncommitted work** and no files outside the published allowlist.

Then it:
- Removes, copies and stages **only the allowlisted generated files**, naming them explicitly. Any git
  failure stops the run. Hooks are never bypassed.
- Reads the staging DB read-only (its hash is checked before and after).
- Builds the encrypted site in `tmp/match_night_site`.
- Commits it to `gh-pages` through the worktree `.worktrees/gh-pages`, inside the repository, and pushes.
- Pages updates within about a minute.

## On the phone
- **Install.**
  - iPhone (Safari): open the URL, then Share → **Add to Home Screen**.
  - Android (Chrome): ⋮ → **Add to Home screen** / **Install app**.
  - The home-screen app opens full screen ("Coach").
- **Unlock** once with the passphrase. Leave "Remember on this device" checked.
- **Before league night:** after a re-publish, open the app once while online. The package is fetched network-first and the lock screen shows *Package built <date>*.
- **Offline:** after one unlock the app opens with no signal, from the service-worker cache. The data is frozen at its build date, and results recorded after it are not included.
- **Freshness indicators:**
  - "Package built" on the lock screen.
  - The match-night banner.
  - "Built … / latest recorded result … / N earlier fixtures still show UNPLAYED" in the page.
- **Your marks and notes** (availability, lineup, played, coach notes) stay in that phone's browser storage. Clearing Safari or Chrome website data removes them.

## Limitations
- One fixture per publish. Re-publish for the next week or another team.
- iOS Safari and Android Chrome are verified by emulation:
  - CI tests use Chromium with phone viewports.
  - Local checks also use Playwright's WebKit with an iPhone profile.
  - Real-device use is **PENDING PAUL REVIEW**.
- If the browser's storage is cleared or private browsing is used, the passphrase is asked again and planning marks are not kept.
