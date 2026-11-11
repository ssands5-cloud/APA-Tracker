'use client';

import { usePathname } from 'next/navigation';
import { NAV } from './nav-items.ts';

function active(path: string, href: string) { return href === '/showcase' ? path === href : path.startsWith(href); }

export function ShowcaseNav() {
  const path = usePathname();
  return <nav className="bc-nav" aria-label="Showcase navigation">{NAV.map(([href, label]) =>
    <a key={href} href={href} aria-current={active(path, href) ? 'page' : undefined}>{label}</a>)}</nav>;
}

export function ShowcaseTabBar() {
  const path = usePathname();
  return <nav className="bc-tabbar" aria-label="Showcase sections">{NAV.slice(0, 4).map(([href, label]) =>
    <a key={href} href={href} aria-current={active(path, href) ? 'page' : undefined}>{label.replace('Power ', '')}</a>)}</nav>;
}
