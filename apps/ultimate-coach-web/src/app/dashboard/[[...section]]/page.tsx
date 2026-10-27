import { ClerkProvider } from '@clerk/nextjs';
import { redirect, notFound } from 'next/navigation';
import { authorizedSnapshot } from '@/lib/server/historical-snapshot';
import { HomePage, MatchNightPage, RecommendationsPage, ThreatsPage, TeamStatusPage, SummaryPage } from '@/components/dashboard-pages';
import { SignOut } from '@/components/sign-out';

export const dynamic = 'force-dynamic';
export const revalidate = 0;
export const runtime = 'nodejs';

const pages = { '': HomePage, 'match-night': MatchNightPage, recommendations: RecommendationsPage,
  threats: ThreatsPage, 'team-status': TeamStatusPage, summary: SummaryPage };

export default async function HistoricalPage({ params }: { params: Promise<{ section?: string[] }> }) {
  const path = (await params).section ?? [];
  if (path.length > 1 || !Object.hasOwn(pages, path[0] ?? '')) notFound();
  const result = await authorizedSnapshot();
  if (!result.ok) {
    if (result.reason === 'anonymous') redirect('/sign-in');
    if (result.reason === 'denied') redirect('/access-denied');
    const retryPath = path[0] ? `/dashboard/${path[0]}` : '/dashboard';
    return <main className="auth-page"><h1>Historical dashboard temporarily unavailable</h1>
      <p>Historical data could not be loaded. Try again, or contact your administrator if this continues.</p>
      <a className="button" href={retryPath}>Try historical dashboard again</a>
      <p><a className="text-link" href="/">Return to public demo</a></p></main>;
  }
  const Page = pages[(path[0] ?? '') as keyof typeof pages];
  const snapshot = result.snapshot;
  return <ClerkProvider><div className="private-shell"><header className="private-header"><a href="/dashboard">Ultimate Coach · protected snapshot</a><SignOut/></header>
    <p className="demo-banner"><strong>{snapshot.label}</strong><br/>{snapshot.provenance.notice} Captured {snapshot.provenance.capturedAt}; latest result {snapshot.provenance.latestResult}.</p>
    <nav className="private-nav" aria-label="Historical dashboard navigation">{[['','Home'],['match-night','Match Night'],['recommendations','Recommendations'],['threats','Shark Tank'],['team-status','Team Status'],['summary',"Captain's Briefing"]].map(([slug,title]) => <a key={slug} href={`/dashboard${slug?'/'+slug:''}`} aria-current={(path[0]??'')===slug?'page':undefined}>{title}</a>)}</nav>
    <section id="historical-content"><Page snapshot={snapshot}/></section></div></ClerkProvider>;
}
