type DecisionBriefProps = { action: string; why: string; tradeoff: string; href: string; link: string };

export function DecisionBrief({ action, why, tradeoff, href, link }: DecisionBriefProps) {
  return <section className="decision-brief" aria-label="Captain decision briefing">
    <div><p className="decision-brief-label">What to do</p><h2>{action}</h2></div>
    <div><p className="decision-brief-label">Why</p><p>{why}</p></div>
    <div><p className="decision-brief-label">Keep in mind</p><p>{tradeoff}</p></div>
    <a href={href}>{link} →</a>
  </section>;
}
