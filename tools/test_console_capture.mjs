// Functional test for apa-console-capture.js, run in Node with faked browser
// globals. Not part of the pytest suite (it's browser JS) -- run manually:
//   node tools/test_console_capture.mjs

import { readFileSync } from "fs";

let failures = 0;
function assert(cond, msg) {
  if (!cond) {
    failures++;
    console.error("FAIL:", msg);
  } else {
    console.log("ok:", msg);
  }
}

// --- Fake browser environment ---
let clipboard = null;
globalThis.copy = (text) => {
  clipboard = text;
};

const REAL_TEAM_RESPONSE = {
  data: {
    team: {
      id: 13082948,
      name: "Chalk It Up",
      standing: 3,
      isTied: false,
      division: { id: 436670, nightOfPlay: "THURSDAY", format: "EIGHT_BALL" },
      roster: [
        {
          displayName: "Shawna Larsen",
          memberNumber: "80200640",
          email: "shawna.larsen@example.com",
          skillLevel: 3,
          ppm: 2.33,
          member: null,
        },
        {
          displayName: "Robert Chen",
          memberNumber: "80200641",
          skillLevel: 5,
          ppm: 1.9,
          member: { id: 7 },
        },
      ],
    },
  },
};

class FakeResponse {
  constructor(body) {
    this._body = body;
  }
  clone() {
    return new FakeResponse(this._body);
  }
  async json() {
    return this._body;
  }
}

let fetchCallCount = 0;
globalThis.window = {
  fetch: async (url, init) => {
    fetchCallCount++;
    return new FakeResponse(REAL_TEAM_RESPONSE);
  },
};

globalThis.XMLHttpRequest = class {
  open(method, url) {
    this.__apaUrl = url;
  }
  addEventListener(event, cb) {
    this._cb = cb;
  }
  send(body) {
    this.responseText = JSON.stringify(REAL_TEAM_RESPONSE);
    if (this._cb) this._cb();
  }
};

// --- Load and eval the script (it's an IIFE attaching to window.fetch etc.) ---
const src = readFileSync(new URL("./apa-console-capture.js", import.meta.url), "utf8");
eval(src);

console.log("APA capture armed" in {} ? "" : ""); // no-op, script already logged its own banner

// --- Drive it exactly like the real page would: a batched Apollo POST ---
const requestBody = JSON.stringify([
  {
    operationName: "teamPage",
    variables: { id: 13082948 },
    query: "query teamPage($id: Int!) { team(id: $id) { id name } }",
  },
]);

await window.fetch("https://gql.poolplayers.com/graphql", { body: requestBody });
// allow the .then() chain inside the patched fetch to resolve
await new Promise((r) => setTimeout(r, 10));

console.log("\n--- Running assertions ---");

const shapes = window.apaShapes();
assert(shapes && shapes.teamPage, "teamPage was captured");
assert(clipboard !== null, "apaShapes() copied something to the clipboard");

const clipped = JSON.parse(clipboard);
assert(clipped.teamPage.response.data.team.id === "int", "id became a type, not a value");
assert(clipped.teamPage.response.data.team.name === "str", "name became a type, not a value");
assert(
  clipped.teamPage.response.data.team.division.nightOfPlay === "THURSDAY",
  "enum-like value THURSDAY was preserved"
);

const rendered = JSON.stringify(clipped);
const secrets = [
  "Chalk It Up",
  "Shawna Larsen",
  "Robert Chen",
  "shawna.larsen@example.com",
  "80200640",
  "80200641",
  "13082948",
  "436670",
];
for (const secret of secrets) {
  assert(!rendered.includes(secret), `"${secret}" did not leak into apaShapes() output`);
}

// The query TEXT itself is expected to survive (it's schema, not data).
assert(rendered.includes("query teamPage"), "the query document text is preserved");

// --- Non-GraphQL fetches must be ignored entirely ---
const before = Object.keys(shapes).length;
await window.fetch("https://example.com/not-graphql", { body: "irrelevant" });
await new Promise((r) => setTimeout(r, 10));
assert(Object.keys(window.apaShapes()).length === before, "a non-GraphQL URL is ignored");

// --- apaFull() DOES carry the real data (that's its whole point) ---
window.apaFull();
assert(clipboard.includes("Chalk It Up"), "apaFull() intentionally keeps real data");

console.log(failures === 0 ? "\nALL PASSED" : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
