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
documents below (standings/roster/player stats) are placeholders
pending a real capture -- see the TODO on each.
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

# --- Data queries (PENDING real capture) ---
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

MATCH_QUERY = None
TEAM_ROSTER_QUERY = None
PLAYER_STATS_QUERY = None
STANDINGS_QUERY = None
