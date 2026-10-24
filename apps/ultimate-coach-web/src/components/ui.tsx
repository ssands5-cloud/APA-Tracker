import type { ReactNode } from 'react';

export function PageTitle({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return <header className="page-title"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="intro">{children}</p></header>;
}
export function Card({ title, kicker, children, className = '' }: { title: string; kicker?: string; children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{kicker ? <p className="eyebrow">{kicker}</p> : null}<h2>{title}</h2>{children}</section>;
}
export function Notice({ children }: { children: ReactNode }) { return <p className="notice">{children}</p>; }
