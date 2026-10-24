import type { Metadata } from 'next';
import { Navigation } from '@/components/navigation';
import './globals.css';

export const metadata: Metadata = {
  title: { default: 'Ultimate Coach · Demo', template: '%s · Ultimate Coach Demo' },
  description: 'A read-only captain dashboard using entirely synthetic demonstration data.',
  robots: { index: false, follow: false },
};
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><a className="skip-link" href="#content">Skip to content</a>
    <div className="workspace"><div className="topbar"><span>Match-night companion</span><span className="demo-pill">SYNTHETIC DEMO</span></div>
      <div className="demo-banner"><strong>Demo data only.</strong> Invented teams and records. No live APA connection. <a className="text-link" href="/dashboard">Open protected historical dashboard →</a></div>
      <main id="content" tabIndex={-1}>{children}</main><footer>ULTIMATE COACH <span>Illustrative guidance · not predictions · captain decides</span></footer>
    </div>
    <aside className="sidebar"><a href="/" className="brand" aria-label="Ultimate Coach home"><span className="brand-mark" aria-hidden="true">UC</span><span>ULTIMATE<br/><b>COACH</b></span></a>
      <p className="sidebar-caption">THE CAPTAIN’S CORNER</p><Navigation/>
      <div className="sidebar-foot"><span className="status-dot"/> PHASE 1 · READ ONLY<p>Clear evidence.<br/>Your decision.</p></div></aside>
    </body></html>;
}
