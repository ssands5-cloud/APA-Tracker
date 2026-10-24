'use client';

import { usePathname } from 'next/navigation';

const pages = [ ['/', 'Home', '01'], ['/match-night', 'Match Night', '02'],
  ['/recommendations', 'Recommendations', '03'], ['/threats', 'Shark Tank', '04'],
  ['/team-status', 'Team Status', '05'], ['/summary', "Captain's Briefing", '06'] ] as const;

export function Navigation() {
  const path = usePathname();
  return <nav className="navigation" aria-label="Main navigation">{pages.map(([href, title, n]) =>
    <a key={href} href={href} aria-current={path === href ? 'page' : undefined}>
      <span className="nav-number" aria-hidden="true">{n}</span>{title}<span className="nav-arrow" aria-hidden="true">↗</span>
    </a>)}</nav>;
}
