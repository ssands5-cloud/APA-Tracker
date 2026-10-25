/** Display the engine's label without assigning confidence or a new score. */
export function evidenceLabel(level: string): string {
  if (['Strong', 'Solid', 'Thin'].includes(level)) return `${level} Evidence`;
  return level;
}
