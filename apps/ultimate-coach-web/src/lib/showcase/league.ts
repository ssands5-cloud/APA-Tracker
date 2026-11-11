/**
 * The one season the showcase renders. By default it is the invented simulation. When the owner has
 * switched on the local real-data beta (see lib/server/showcase-real.ts) it is their own division.
 * Everything else in the showcase reads from here, so both sources produce identical screens.
 */
import { buildSeason } from './engine.ts';
import { simulateSeason } from './simulate.ts';
import { loadRealSeason } from '../server/showcase-real.ts';

const season = buildSeason(loadRealSeason() ?? simulateSeason());

export const {
  LEAGUE, MY_TEAM, provenance, standings, powerRankings, upcoming, featured, myTeamOnBye, byeTeams, feed, weeks,
  allPlayers, allTeams, allResults, player, team, teamRecord, resultsByWeek, weekStars, teamPointsByWeek, teamPointsGrid,
  leagueAvgByWeek, headToHead,
} = season;

export { playerWinProb, teamWinProb, winPct, ppm, ratingTrend } from './engine.ts';
export type { Player, Team, StandingRow, PowerRow, Preview, TeamMatch, IndividualMatch, ActivityItem } from './types.ts';
