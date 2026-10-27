// Test-only SSR composition. No route, authorization, or data-loader is executed.
// Client explorer, router navigation and account button are placeholders; their
// interactions require browser checks. All page and shell markup is real source.
import { readFile, mkdtemp, writeFile, rm } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
let input = ''; for await (const chunk of process.stdin) input += chunk;
const { snapshot, page = 'HomePage' } = JSON.parse(input);
const slugs = {HomePage:'', MatchNightPage:'match-night', ThreatsPage:'threats', SummaryPage:'summary'};
if (!(page in slugs)) throw new Error('Unsupported page');
const temp = await mkdtemp(path.join(process.cwd(), 'node_modules', '.page-render-'));
const transpile = source => ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
try {
  for (const name of ['snapshot-types','evidence-label']) {
    await writeFile(path.join(temp, name+'.mjs'), transpile(await readFile('src/lib/'+name+'.ts','utf8')));
  }
  for (const name of ['ui','plan-board','captain-command','captain-decisions','dashboard-pages']) {
    let source = await readFile('src/components/'+name+'.tsx','utf8');
    source = source.replace("import { HistoricalOpponentView } from './historical-opponent-view';", 'function HistoricalOpponentView() { return <section id="response-explorer" data-test-client-placeholder="true">Client explorer placeholder</section>; }');
    source = source.replaceAll("'@/lib/snapshot-types'", "'./snapshot-types.mjs'").replaceAll("'../lib/evidence-label'", "'./evidence-label.mjs'");
    for (const dependency of ['ui','plan-board','captain-command','captain-decisions']) source = source.replaceAll("'./"+dependency+"'", "'./"+dependency+".mjs'");
    await writeFile(path.join(temp,name+'.mjs'),transpile(source));
  }
  const components = await import(pathToFileURL(path.join(temp,'dashboard-pages.mjs')).href);
  // Retain the complete real protected presentation return, including metadata
  // and account controls. Never import or call its authorization/data-loader.
  const route = await readFile('src/app/dashboard/[[...section]]/page.tsx','utf8');
  const presentation = route.slice(route.indexOf('return <ClerkProvider>'),route.lastIndexOf('\n}'));
  if (!presentation.startsWith('return <ClerkProvider>')) throw new Error('Protected shell return missing');
  await writeFile(path.join(temp,'shell.mjs'),transpile(`const ClerkProvider = ({children}) => children; const SignOut = () => <button data-test-account-placeholder="true">Sign out</button>; export function Shell({snapshot, Page, path}) { ${presentation} }`));
  const { Shell } = await import(pathToFileURL(path.join(temp,'shell.mjs')).href);
  const layout = (await readFile('src/app/layout.tsx','utf8')).replace("import { Navigation } from '@/components/navigation';",'const Navigation = () => null;').replace("import './globals.css';",'');
  await writeFile(path.join(temp,'layout.mjs'),transpile(layout));
  const { default: Layout } = await import(pathToFileURL(path.join(temp,'layout.mjs')).href);
  process.stdout.write(renderToStaticMarkup(React.createElement(Layout,null,React.createElement(Shell,{snapshot, Page:components[page],path:[slugs[page]]}))));
} finally { await rm(temp,{recursive:true,force:true}); }
