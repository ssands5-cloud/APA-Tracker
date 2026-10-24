// Test-only renderer: exercises the real TSX without a signed-in session or private data.
import { readFile, mkdtemp, writeFile, rm } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

let input = '';
for await (const chunk of process.stdin) input += chunk;
const { snapshot, matchNight = false, withShell = false } = JSON.parse(input);
const temp = await mkdtemp(path.join(process.cwd(), 'node_modules', '.command-render-'));
try {
  const source = await readFile('src/components/captain-command.tsx', 'utf8');
  const labelUrl = pathToFileURL(path.resolve('src/lib/evidence-label.ts')).href;
  const { outputText } = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } });
  const file = path.join(temp, 'command.mjs');
  await writeFile(file, outputText.replace("'../lib/evidence-label'", JSON.stringify(labelUrl)));
  const { CaptainCommand } = await import(pathToFileURL(file).href);
  let view = React.createElement(CaptainCommand, { snapshot, matchNight });
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
    view = React.createElement(Layout, null,
      React.createElement('div', { className: 'private-shell' }, view));
  }
  process.stdout.write(renderToStaticMarkup(view));
} finally {
  await rm(temp, { recursive: true, force: true });
}
