/*
 * Paste this into Chrome's DevTools Console while on league.poolplayers.com,
 * already logged in. No install, no Python, no Playwright -- it runs inside
 * the browser tab itself and watches network traffic the page already makes.
 *
 * WHAT IT DOES NOT DO
 *   - It never reads or touches your password. You are already logged in
 *     before you paste this; it only watches requests the page sends.
 *   - It never sends anything anywhere. Everything stays in this tab's
 *     memory until you explicitly copy it.
 *
 * HOW TO USE
 *   1. Log into APA normally, in a real tab.
 *   2. Open DevTools (F12) -> Console tab.
 *   3. Paste this whole file there and press Enter. You'll see
 *      "APA capture armed."
 *   4. Without reloading the page, click into your team page, then your
 *      division standings page (in-app navigation is fine and expected;
 *      a full page reload would wipe what's captured so far).
 *   5. Back in the console, run:  apaShapes()
 *      It prints what was captured and copies a SANITIZED version to your
 *      clipboard -- field names and types only, no names, ids, or scores.
 *      Paste that into the chat.
 *
 * If you want a local copy with the real data (for your own use, not to
 * share), run apaFull() instead -- same idea, but unredacted. Never paste
 * that one into the chat; it has your teammates' names in it.
 */
(() => {
  const GRAPHQL_HOST = "gql.poolplayers.com/graphql";
  const captures = {};

  // Short ALL_CAPS strings are enum values (COMPLETED, HOME, EIGHT_BALL), not
  // names -- kept because they're the schema. Anchored and length-capped so
  // nothing that looks like a shouted sentence, or an all-caps ID, matches.
  const ENUM_RE = /^[A-Z][A-Z0-9_]{0,31}$/;

  function summarizeShape(value) {
    if (typeof value === "boolean") return "bool"; // checked first: not a number
    if (value === null || value === undefined) return "null";
    if (typeof value === "number") return Number.isInteger(value) ? "int" : "float";
    if (typeof value === "string") return ENUM_RE.test(value) ? value : "str";
    if (Array.isArray(value)) {
      if (value.length === 0) return [];
      return [summarizeShape(value[0]), `...${value.length} item(s)`];
    }
    if (typeof value === "object") {
      const out = {};
      for (const key of Object.keys(value)) out[key] = summarizeShape(value[key]);
      return out;
    }
    return typeof value;
  }

  // Held in this tab's memory only, never auto-copied and never printed.
  // apaToken() is the single place it can leave, and it leaves as a command
  // meant for your own terminal.
  let accessToken = null;

  function rememberToken(headers) {
    if (accessToken || !headers) return;
    let value = null;
    if (typeof headers.get === "function") {
      value = headers.get("authorization"); // a Headers instance
    } else if (Array.isArray(headers)) {
      const found = headers.find((pair) => String(pair[0]).toLowerCase() === "authorization");
      value = found ? found[1] : null;
    } else {
      const key = Object.keys(headers).find((k) => k.toLowerCase() === "authorization");
      value = key ? headers[key] : null;
    }
    if (value) accessToken = String(value);
  }

  function record(operationName, variables, query, response) {
    captures[operationName] = { operationName, variables, query, response };
    console.log("captured:", operationName);
  }

  function handleGraphQLCall(url, rawBody, getResponseJson) {
    if (!url.includes(GRAPHQL_HOST) || !rawBody) return;
    let parsedBody;
    try {
      parsedBody = JSON.parse(rawBody);
    } catch (e) {
      return;
    }
    const items = Array.isArray(parsedBody) ? parsedBody : [parsedBody];
    // getResponseJson() -- rather than an already-created promise -- is
    // called only once every early-return above has passed, so a promise
    // that might reject is never left without a .catch() attached to it.
    getResponseJson()
      .then((responseJson) => {
        const responseItems = Array.isArray(responseJson) ? responseJson : [responseJson];
        items.forEach((item, index) => {
          if (!item || !item.operationName) return;
          // Apollo can batch several operations into one HTTP call; the
          // response array lines up with the request array by position.
          const response =
            responseItems[index] !== undefined ? responseItems[index] : responseItems[0];
          record(item.operationName, item.variables, item.query, response);
        });
      })
      .catch(() => {});
  }

  // --- Patch fetch (Apollo's normal transport) ---
  const originalFetch = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    const body = (init && init.body) || (typeof input === "object" && input.body) || null;
    if (url.includes(GRAPHQL_HOST)) {
      rememberToken((init && init.headers) || (typeof input === "object" && input.headers));
    }
    return originalFetch.apply(this, arguments).then((response) => {
      if (typeof body === "string") {
        try {
          handleGraphQLCall(url, body, () => response.clone().json());
        } catch (e) {
          /* already consumed -- ignore */
        }
      }
      return response;
    });
  };

  // --- Patch XMLHttpRequest too, in case the app uses it instead ---
  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__apaUrl = url;
    return originalOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (body) {
    if (this.__apaUrl && typeof body === "string") {
      this.addEventListener("load", () => {
        const xhr = this;
        try {
          handleGraphQLCall(xhr.__apaUrl, body, () => Promise.resolve(JSON.parse(xhr.responseText)));
        } catch (e) {
          /* ignore */
        }
      });
    }
    return originalSend.apply(this, arguments);
  };

  function buildShapes() {
    const shapes = {};
    for (const name of Object.keys(captures)) {
      const c = captures[name];
      shapes[name] = {
        operationName: c.operationName,
        variables: summarizeShape(c.variables),
        query: c.query, // the query document itself: schema text, not data
        response: summarizeShape(c.response),
      };
    }
    return shapes;
  }

  window.apaShapes = function () {
    const names = Object.keys(captures);
    if (names.length === 0) {
      console.log("Nothing captured yet. Visit your team page and standings page first.");
      return;
    }
    const text = JSON.stringify(buildShapes(), null, 2);
    copy(text); // DevTools console builtin -- clipboard, nothing sent anywhere
    console.log(`Captured: ${names.join(", ")}`);
    console.log("Sanitized shapes copied to your clipboard. Paste it into the chat.");
    return buildShapes();
  };

  window.apaFull = function () {
    const names = Object.keys(captures);
    if (names.length === 0) {
      console.log("Nothing captured yet.");
      return;
    }
    copy(JSON.stringify(captures, null, 2));
    console.log(`Captured (FULL, has real data): ${names.join(", ")}`);
    console.log("Copied to clipboard. This has real names in it -- local use only, do not share.");
    return captures;
  };

  window.apaToken = function () {
    if (!accessToken) {
      console.log("No access token seen yet. Load a page that fetches data first.");
      return;
    }
    // Copied as a ready-to-run command so it goes clipboard -> your own
    // terminal in one step, with no hand-copying of the token itself.
    copy(`$env:APA_ACCESS_TOKEN = "${accessToken}"; python -m scheduler.graphql_sync`);
    console.log("%cCopied a PowerShell command to your clipboard.", "font-weight:bold");
    console.log("Paste it into PowerShell in the repo folder and press Enter.");
    console.log("%cThis one contains your live token. Never paste it into a chat.",
                "color:#c00;font-weight:bold");
  };

  console.log("APA capture armed. Browse your team page and standings page now (no reload).");
  console.log("  apaShapes()  -> sanitized schema, safe to share");
  console.log("  apaToken()   -> a ready-to-run sync command, for YOUR terminal only");
})();
