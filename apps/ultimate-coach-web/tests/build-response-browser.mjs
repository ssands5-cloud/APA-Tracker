// Test-only bundle of the actual client component, suitable for static fixtures.
// Run from apps/ultimate-coach-web: node tests/build-response-browser.mjs
// Negative control: add --stale-player-mutation, then run response-browser.py
// --bundle-dir test-results/response-browser-stale-player; it must fail on Riley's name.
import { readFile, mkdir, writeFile, rm } from 'node:fs/promises';
import path from 'node:path';
import ts from 'typescript';
import { execFileSync } from 'node:child_process';
import w from 'next/dist/compiled/webpack/webpack.js';

const baseline = process.argv.includes('--baseline');
const stalePlayerMutation = process.argv.includes('--stale-player-mutation');
if (stalePlayerMutation && baseline) throw new Error('Use the pinned baseline and stale-player mutation separately.');
const output = path.resolve(baseline ? 'test-results/response-browser-baseline' : stalePlayerMutation ? 'test-results/response-browser-stale-player' : 'test-results/response-browser');
const source = path.join(output, 'source');
await mkdir(source, { recursive: true });
const transpile = text => ts.transpileModule(text, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
for (const [name, file] of Object.entries({ 'historical-opponent-view': 'src/components/historical-opponent-view.tsx', 'opponent-link': 'src/components/opponent-link.ts', 'snapshot-types': 'src/lib/snapshot-types.ts', 'evidence-label': 'src/lib/evidence-label.ts' })) {
  // A pinned pre-fix client proves the regression without reverting shared source.
  const original = baseline && name === 'historical-opponent-view'
    ? execFileSync('git', ['show', 'f63353f:apps/ultimate-coach-web/' + file], { encoding: 'utf8' })
    : await readFile(file, 'utf8');
  // Mutate only a temporary test copy; production source is never rewritten.
  const nameExpression = '<h2 className="re-answer-name">{answer.player}</h2>';
  if (stalePlayerMutation && name === 'historical-opponent-view' && original.split(nameExpression).length !== 2) throw new Error('Expected exactly one recommendation name expression for the negative control.');
  const mutated = stalePlayerMutation && name === 'historical-opponent-view'
    ? original.replace(nameExpression, '<h2 className="re-answer-name">{responses[opponents[0].id]?.player}</h2>')
    : original;
  const text = mutated.replaceAll("'@/lib/snapshot-types'", "'./snapshot-types.mjs'").replaceAll("'./opponent-link'", "'./opponent-link.mjs'").replaceAll("'../lib/evidence-label'", "'./evidence-label.mjs'");
  await writeFile(path.join(source, name + '.mjs'), transpile(text));
}
await writeFile(path.join(source, 'entry.mjs'), `import React from 'react'; import {createRoot} from 'react-dom/client'; import {HistoricalOpponentView} from './historical-opponent-view.mjs'; window.mountResponseExplorer = (snapshot, target = document.getElementById('response-root')) => createRoot(target).render(React.createElement(HistoricalOpponentView, {snapshot}));`);
await new Promise((resolve, reject) => w.webpack({ mode: 'development', entry: path.join(source, 'entry.mjs'), output: {path: output, filename: 'response.js'}, devtool: false }, (error, stats) => error || stats.hasErrors() ? reject(error || new Error(stats.toString())) : resolve()));
await rm(source, { recursive: true, force: true });
console.log(path.join(output, 'response.js'));
