import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

// Execute the real component/route control flow with provider and navigation
// boundaries stubbed. No credentials, database, private snapshot, or network.
type Element = { type: unknown; props: Record<string, unknown> };
const jsx = (type: unknown, props: Record<string, unknown>): Element => ({ type, props });
function load(file: string, dependencies: Record<string, unknown>) {
  const module = { exports: {} as Record<string, any> };
  const code = ts.transpileModule(readFileSync(file, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
  } }).outputText;
  runInNewContext(code, { module, exports: module.exports, require(name: string) {
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'Fragment' };
    if (Object.hasOwn(dependencies, name)) return dependencies[name];
    throw new Error(`Unexpected dependency: ${name}`);
  } }, { filename: file });
  return module.exports;
}
class Redirect extends Error { location: string; constructor(location: string) { super(location); this.location = location; } }
function dashboard(result: unknown, section: string[] = []) {
  return load('src/app/dashboard/[[...section]]/page.tsx', {
    '@clerk/nextjs': { ClerkProvider: 'ClerkProvider' },
    'next/navigation': { redirect: (url: string) => { throw new Redirect(url); }, notFound: () => { throw new Error('404'); } },
    '@/lib/server/historical-snapshot': { authorizedSnapshot: async () => result },
    '@/components/dashboard-pages': Object.fromEntries(['HomePage', 'MatchNightPage', 'RecommendationsPage', 'ThreatsPage', 'TeamStatusPage', 'SummaryPage'].map(name => [name, name])),
    '@/components/sign-out': { SignOut: 'SignOut' },
  }).default({ params: Promise.resolve({ section }) });
}
function signIn(isLoaded: boolean, isSignedIn: boolean | undefined) {
  return load('src/components/captain-sign-in.tsx', {
    '@clerk/nextjs': { SignIn: 'SignIn', useAuth: () => ({ isLoaded, isSignedIn }) },
    './sign-out': { SignOut: 'SignOut' },
  }).CaptainSignIn();
}
function nodes(value: unknown): Element[] {
  if (Array.isArray(value)) return value.flatMap(nodes);
  if (!value || typeof value !== 'object' || !('props' in value)) return [];
  const element = value as Element;
  return [element, ...nodes(element.props.children)];
}

test('unavailable historical data renders a stable page instead of restarting sign-in', async () => {
  const view = await dashboard({ ok: false, reason: 'unavailable' });
  const rendered = JSON.stringify(view);
  assert.match(rendered, /Historical dashboard temporarily unavailable/);
  assert.ok(nodes(view).some(node => node.type === 'a' && node.props.href === '/dashboard'));
  assert.ok(!nodes(view).some(node => node.props.href === '/sign-in'));
  assert.ok(!nodes(view).some(node => ['HomePage', 'MatchNightPage'].includes(String(node.type))));
});

test('anonymous and denied visitors retain their protected-route redirects', async () => {
  for (const [reason, location] of [['anonymous', '/sign-in'], ['denied', '/access-denied']]) {
    await assert.rejects(dashboard({ ok: false, reason }), (error: unknown) => error instanceof Redirect && error.location === location);
  }
});

test('a signed-in browser never mounts auto-redirecting SignIn after a server rejection', () => {
  const view = signIn(true, true);
  assert.ok(!nodes(view).some(node => node.type === 'SignIn'));
  assert.match(JSON.stringify(view), /Clerk has signed you in/);
  assert.ok(nodes(view).some(node => node.type === 'a' && node.props.href === '/dashboard'));
  assert.ok(nodes(view).some(node => node.type === 'SignOut'));
});

test('signed-out browsers keep the normal Clerk password and device-verification flow', () => {
  const form = nodes(signIn(true, false)).find(node => node.type === 'SignIn');
  assert.ok(form);
  assert.equal(form.props.routing, 'path');
  assert.equal(form.props.path, '/sign-in');
  assert.equal(form.props.forceRedirectUrl, '/dashboard');
});

test('loading provider state cannot start a premature redirect', () => {
  const view = signIn(false, undefined);
  assert.ok(!nodes(view).some(node => node.type === 'SignIn'));
  assert.ok(nodes(view).some(node => node.props.role === 'status'));
});

test('an authenticated browser and an anonymous server result cannot form an automatic loop', async () => {
  await assert.rejects(dashboard({ ok: false, reason: 'anonymous' }), (error: unknown) => error instanceof Redirect && error.location === '/sign-in');
  const landing = signIn(true, true);
  assert.ok(!nodes(landing).some(node => node.type === 'SignIn'));
});


test('an unavailable Match Night keeps retry navigation on the requested section', async () => {
  const view = await dashboard({ ok: false, reason: 'unavailable' }, ['match-night']);
  assert.ok(nodes(view).some(node => node.type === 'a' && node.props.href === '/dashboard/match-night'));
});

test('successful historical access still renders the supplied protected snapshot', async () => {
  const snapshot = { label: 'synthetic-private-sentinel', provenance: { notice: 'test only', capturedAt: 'test', latestResult: 'test' } };
  const view = await dashboard({ ok: true, snapshot }, ['match-night']);
  const page = nodes(view).find(node => node.type === 'MatchNightPage');
  assert.ok(page);
  assert.equal(page.props.snapshot, snapshot);
});

test('the actual sign-in route mounts the session-aware gate', () => {
  const route = load('src/app/sign-in/[[...sign-in]]/page.tsx', {
    '@clerk/nextjs': { ClerkProvider: 'ClerkProvider', SignIn: 'SignIn' },
    '@/lib/auth-config': { authConfigured: () => true },
    '@/components/captain-sign-in': { CaptainSignIn: 'CaptainSignIn' },
  }).default;
  const view = route();
  assert.ok(nodes(view).some(node => node.type === 'CaptainSignIn'));
  assert.ok(!nodes(view).some(node => node.type === 'SignIn'));
});
