import type { Metadata } from 'next';
import { Navigation } from '@/components/navigation';
import { snapshot } from '@/lib/snapshot';
import './globals.css';

export const metadata: Metadata = {
  title: { default: 'Ultimate Coach · Demo', template: '%s · Ultimate Coach Demo' },
  description: 'A read-only league-night simulation using historical rosters and matchup evidence.',
  robots: { index: false, follow: false },
};
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><a className="skip-link" href="#content">Skip to content</a>
    <aside className="sidebar"><a href="/" className="brand" aria-label="Ultimate Coach home"><span className="brand-mark" aria-hidden="true">UC</span><span>ULTIMATE<br/><b>COACH</b></span></a>
      <p className="sidebar-caption">THE CAPTAIN’S CORNER</p><Navigation/>
      <div className="sidebar-foot"><span className="status-dot"/> HISTORICAL REPLAY · READ ONLY<p>Clear evidence.<br/>Your decision.</p></div></aside>
    <div className="workspace"><div className="topbar"><span>Match-night companion</span><span className="demo-pill">HISTORICAL DEMO</span></div>
      <div className="demo-banner"><strong>{snapshot.label}</strong><br/>{snapshot.provenance.notice} Export captured {snapshot.provenance.capturedAt}; latest recorded result {snapshot.provenance.latestResult}.</div>
      <main id="content" tabIndex={-1}>{children}</main><footer>ULTIMATE COACH <span>Historical engine guidance · simulated night · captain decides</span></footer>
    </div></body></html>;
}
