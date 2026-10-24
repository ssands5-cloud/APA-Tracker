// Test-only renderer: exercises the real TSX without a signed-in session or private data.
import { readFile, mkdtemp, writeFile, rm } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

let input = '';
for await (const chunk of process.stdin) input += chunk;
const { snapshot, matchNight = false, withShell = false, view: viewName = 'command' } = JSON.parse(input);
const temp = await mkdtemp(path.join(process.cwd(), 'node_modules', '.command-render-'));
try {
  if (!['command', 'dossiers', 'briefing'].includes(viewName)) throw new Error('Unsupported test view');
  const source = await readFile(viewName === 'command' ? 'src/components/captain-command.tsx' : 'src/components/captain-decisions.tsx', 'utf8');
  const labelUrl = pathToFileURL(path.resolve('src/lib/evidence-label.ts')).href;
  const { outputText } = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } });
  const file = path.join(temp, 'command.mjs');
  await writeFile(file, outputText.replace("'../lib/evidence-label'", JSON.stringify(labelUrl)));
  const components = await import(pathToFileURL(file).href);
  const Component = components[viewName === 'command' ? 'CaptainCommand' : viewName === 'dossiers' ? 'ThreatDossiers' : 'CaptainBriefing'];
  let view = React.createElement(Component, { snapshot, matchNight });
  if (withShell) {
    // Render the actual outer layout. Navigation itself is unrelated to this
    // test and requires Next's router, so stub that child only.
    const layoutSource = (await readFile('src/app/layout.tsx', 'utf8'))
      .replace("import { Navigation } from '@/components/navigation';", 'const Navigation = () => null;')
      .replace("import './globals.css';", '');
    const layout = ts.transpileModule(layoutSource, { compilerOptions: {
      module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
    } });
    const layoutFile = path.join(temp, 'layout.mjs');
    await writeFile(layoutFile, layout.outputText);
    const { default: Layout } = await import(pathToFileURL(layoutFile).href);
    // Extract only the actual route navigation, without importing its authorization or data loader.
    const route = await readFile('src/app/dashboard/[[...section]]/page.tsx', 'utf8');
    const navigation = route.match(/<nav className="private-nav"[\s\S]+?<\/nav>/)?.[0];
    if (!navigation) throw new Error('Historical navigation markup missing');
    const nav = ts.transpileModule(`export function HistoricalNavigation() { const path = []; return (${navigation}); }`, { compilerOptions: {
      module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
    } });
    const navFile = path.join(temp, 'historical-navigation.mjs');
    await writeFile(navFile, nav.outputText);
    const { HistoricalNavigation } = await import(pathToFileURL(navFile).href);
    view = React.createElement(Layout, null,
      React.createElement('div', { className: 'private-shell' }, React.createElement(HistoricalNavigation), view));
  }
  process.stdout.write(renderToStaticMarkup(view));
} finally {
  await rm(temp, { recursive: true, force: true });
}
