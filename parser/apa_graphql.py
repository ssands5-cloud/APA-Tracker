"""
GraphQL query/mutation documents for the APA / CPA "Member Services" API.

league.poolplayers.com and accounts.poolplayers.com are both client-side
apps (a React SPA and a Next.js app, respectively) that read and write
all data through a single GraphQL endpoint -- there is no server-rendered
HTML to scrape and no separate REST API. GRAPHQL_ENDPOINT and every
document below were reverse-engineered from the production JS bundles
those apps serve publicly (view-source on our own account's session --
the same requests the official web app makes), not guessed.

Auth documents (login/authorize/generateAccessToken/revokeToken) are
confirmed working shapes, pulled verbatim from the bundle. The data
the team documents below were captured from the authenticated team page.
"""

GRAPHQL_ENDPOINT = "https://gql.poolplayers.com/graphql"

# --- Auth (confirmed: found in accounts.poolplayers.com's login chunk) ---

LOGIN_MUTATION = """
    mutation login($username: String!, $password: String!) {
  login(input: {username: $username, password: $password}) {
    __typename
    ... on SuccessLoginPayload {
      deviceRefreshToken
    }
    ... on PartialSuspendedLoginPayload {
      leagueIds
      deviceRefreshToken
    }
    ... on DeniedLoginPayload {
      reason
    }
  }
}
"""

# Exchanges the short-lived deviceRefreshToken (from LOGIN_MUTATION) for a
# durable refreshToken. Confirmed from the same chunk.
AUTHORIZE_MUTATION = """
    mutation authorize($deviceRefreshToken: String!) {
  authorize(deviceRefreshToken: $deviceRefreshToken) {
    refreshToken
  }
}
"""

# Exchanges the durable refreshToken for a short-lived accessToken, used as
# the `authorization` header value on every other call. Confirmed from
# league.poolplayers.com's main bundle (GenerateAccessTokenMutation).
GENERATE_ACCESS_TOKEN_MUTATION = """
  mutation GenerateAccessTokenMutation($refreshToken: String!) {
    generateAccessToken(refreshToken: $refreshToken) {
      accessToken
    }
  }
"""

# Invalidates a refreshToken server-side (logout). Confirmed from the
# accounts.poolplayers.com bundle.
REVOKE_TOKEN_MUTATION = """
    mutation revokeToken($refreshToken: String!) {
  revokeRefreshToken(refreshToken: $refreshToken)
}
"""

# --- Data queries captured from the authenticated team page ---
#
# The matchup page (league.poolplayers.com/<league>/match/<id>) renders a
# roster table (player name, skill level, matches won/played, win %, PPM,
# PA) plus team names/records and match metadata, but its query lives in a
# shared chunk that wasn't identified from static bundle inspection alone.
#
# TODO: capture the real request from DevTools (Network tab -> filter
# Fetch/XHR -> the POST to gql.poolplayers.com/graphql -> Copy as fetch)
# while viewing:
#   - a matchup page  -> fill MATCH_QUERY
#   - a team page      -> fill TEAM_ROSTER_QUERY
#   - "My Stats"        -> fill PLAYER_STATS_QUERY
#   - a standings/division page -> fill STANDINGS_QUERY
# Redact the `authorization` header value before sharing -- only the
# query/variables/response shape is needed, never the live token.

TEAM_PAGE_QUERY = """
query teamPage($id: Int!) {
  team(id: $id) {
    id name number isTied standing
    division { id name number timeOfPlay nightOfPlay format state isTournament }
    location { id name address { id name } }
    session { id name }
    league { id slug }
  }
}
"""

TEAM_ROSTER_QUERY = """
query teamRoster($id: Int!) {
  team(id: $id) {
    id name number
    league { id slug }
    division { id type }
    roster {
      id memberNumber displayName matchesWon matchesPlayed
      ... on EightBallPlayer { pa ppm skillLevel }
      ... on NineBallPlayer { pa ppm skillLevel }
      member { id }
    }
  }
}
"""

TEAM_SCHEDULE_QUERY = """
query teamSchedule($id: Int!) {
  team(id: $id) {
    id sessionBonusPoints sessionPoints sessionTotalPoints
    division { id isTournament }
    matches(unscheduled: true) {
      week type id isBye status scoresheet startTime isMine isPaid
      isTournament isScored isFinalized isPlayoff description tableNumber
      results { homeAway points { total } }
      timeZone { id name }
      location { id name address { id name } }
      home { id name number isMine }
      away { id name number isMine }
      division { id scheduleInEdit isTournament }
    }
  }
}
"""

# --- Division queries, captured 2026-09-03 from the real division standings
# page (docs/graphql-captures/2026-09-03-shapes.json has the full sanitized
# capture: field names and types, no data). This is the query that used to be
# guessed at as "LeagueBox" -- the real operation is spelled divsionStandings,
# missing the first "i", and GraphQL matches operation names exactly.

DIVISION_STANDINGS_QUERY = """
query divsionStandings($id: Int!) {
  division(id: $id) {
    id
    teams {
      id name number standing pointsLastWeek lastWeek
      sessionTotalPoints totalTeamMatchesPlayed isTied isBye
      league { id slug }
    }
  }
}
"""

DIVISION_CONTACTS_QUERY = """
query DivisionContacts($id: Int!) {
  division(id: $id) {
    id name
    contacts { phone alias { id displayName } }
  }
}
"""

DIVISION_ROSTERS_QUERY = """
query divisionRosters($id: Int!) {
  division(id: $id) {
    id
    teams {
      isBye
      id name number
      league { id slug }
      division { id type }
      roster {
        id memberNumber displayName matchesWon matchesPlayed
        ... on EightBallPlayer { pa ppm skillLevel }
        ... on NineBallPlayer { pa ppm skillLevel }
        member { id }
      }
    }
  }
}
"""

# --- Division schedule and match detail: captured, but trimmed here ---
#
# The real divisionSchedule and MatchPage documents (see the same capture
# file) also request orderItems { order { member { firstName lastName } } }
# and, on MatchPage, fees { amount tax total }. Those are billing/order
# fields from the app's payment flow -- personal and financial data this
# tracker has no reason to request, store, or be liable for. The versions
# below ask for everything actually used (results, scores, schedule dates)
# and nothing from that subtree.

DIVISION_SCHEDULE_QUERY = """
query divisionSchedule($id: Int!) {
  division(id: $id) {
    id
    teams { id name number active isBye }
    schedule {
      id description date weekOfPlay skip
      matches {
        id isBye status startTime isScored isFinalized isPlayoff tableNumber
        results { homeAway points { total } }
        home { id name number }
        away { id name number }
      }
    }
  }
}
"""

MATCH_DETAIL_QUERY = """
query MatchPage($id: Int!) {
  match(id: $id) {
    id isFinalized isTournament tableNumber startTime week isBye isScored
    home { id name number }
    away { id name number }
    results {
      homeAway overUnder forfeits matchesWon matchesPlayed
      points { bonus penalty won adjustment sportsmanship total skillLevelViolationAdjustment }
      scores {
        id
        player { id displayName }
        matchPositionNumber playerPosition skillLevel
        eightBallWins eightOnBreak eightBallBreakAndRun
        nineBallPoints nineOnSnap nineBallBreakAndRun nineBallMatchPointsEarned
        winLoss matchForfeited doublesMatch eightBallMatchPointsEarned incompleteMatch
      }
    }
  }
}
"""

# --- Viewer-scoped queries: no id needed at all ---
#
# Captured 2026-09-03 from a real logged-in session (55-operation capture,
# see docs/graphql-captures/2026-09-03-full-session/HANDOFF.md for the full
# writeup). Both take zero variables -- they read the currently authenticated
# member implicitly, via `viewer`. This is a real design change from every
# query above: apa_config.yaml hardcodes one team.team_id, but the real
# capture proved the account plays on 4 teams, not 1. These two replace that
# assumption rather than extend it.
#
# Both are trimmed from the real captured documents the same way
# MATCH_DETAIL_QUERY and DIVISION_SCHEDULE_QUERY already are:
# matchesByViewer's real query additionally requests orderItems { order {
# member { firstName lastName } } } (billing/order PII) and fee /
# membershipExpires / scoresheet / isPaid (account/billing fields )-- none
# of that is requested here.

DASHBOARD_TEAMS_QUERY = """
query dashboardTeams {
  viewer {
    id
    ... on Member {
      leagueTeams: teams(type: [RELEASED, WEEKLY], current: true) {
        id name standing totalTeamMatchesPlayed isTied
        division { id type isTournament }
        league { id slug }
        session { id name }
      }
      tournamentTeams: teams(type: [TOURNAMENT], current: true) {
        id name standing totalTeamMatchesPlayed isTied
        division { id type isTournament }
        league { id slug }
        session { id name }
      }
    }
  }
}
"""

MATCHES_BY_VIEWER_QUERY = """
query matchesByViewer {
  viewer {
    id
    ... on Member {
      teams {
        id name number
        session { id name }
        matches {
          type id week isBye status startTime isMine isScored isFinalized isPlayoff tableNumber
          results { homeAway points { total } }
          home { id name number }
          away { id name number }
        }
      }
    }
  }
}
"""

# Retained for compatibility with code that checks these names.
LEAGUE_BOX_QUERY = None  # superseded by DIVISION_STANDINGS_QUERY -- see above
MATCH_QUERY = None
PLAYER_STATS_QUERY = None
STANDINGS_QUERY = None
