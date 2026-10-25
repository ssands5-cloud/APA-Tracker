/** Resolve a scouting link only against the opponents in the current fixture. */
export function opponentFromSearch(search: string, opponents: readonly { id: string }[]): string | null {
  const requested = new URLSearchParams(search).get('opponent');
  return requested && opponents.some(opponent => opponent.id === requested) ? requested : null;
}
