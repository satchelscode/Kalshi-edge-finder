import os
import requests
import math
import time
from flask import Flask, render_template, jsonify, request, redirect
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import json
from difflib import SequenceMatcher

app = Flask(__name__)

# Configuration
ODDS_API_KEY = os.environ.get('ODDS_API_KEY')
KALSHI_API_KEY_ID = os.environ.get('KALSHI_API_KEY_ID')
KALSHI_PRIVATE_KEY = os.environ.get('KALSHI_PRIVATE_KEY')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# ============================================================
# SPORTS CONFIGURATION
# Maps Kalshi series tickers to The Odds API sport keys
# Each entry: kalshi_series -> (odds_api_key, display_name, team_map)
# ============================================================

# Team abbreviation maps per sport
NBA_TEAMS = {
    'MIA': 'Miami Heat', 'CHI': 'Chicago Bulls', 'MIL': 'Milwaukee Bucks',
    'WAS': 'Washington Wizards', 'PHI': 'Philadelphia 76ers', 'SAC': 'Sacramento Kings',
    'ATL': 'Atlanta Hawks', 'HOU': 'Houston Rockets', 'DAL': 'Dallas Mavericks',
    'CHA': 'Charlotte Hornets', 'DET': 'Detroit Pistons', 'PHX': 'Phoenix Suns',
    'BKN': 'Brooklyn Nets', 'DEN': 'Denver Nuggets', 'MIN': 'Minnesota Timberwolves',
    'OKC': 'Oklahoma City Thunder', 'BOS': 'Boston Celtics', 'NYK': 'New York Knicks',
    'POR': 'Portland Trail Blazers', 'LAL': 'Los Angeles Lakers', 'LAC': 'LA Clippers',
    'GSW': 'Golden State Warriors', 'UTA': 'Utah Jazz', 'MEM': 'Memphis Grizzlies',
    'NOP': 'New Orleans Pelicans', 'ORL': 'Orlando Magic', 'TOR': 'Toronto Raptors',
    'CLE': 'Cleveland Cavaliers', 'IND': 'Indiana Pacers', 'SAS': 'San Antonio Spurs',
}

NHL_TEAMS = {
    'ANA': 'Anaheim Ducks', 'ARI': 'Arizona Coyotes', 'BOS': 'Boston Bruins',
    'BUF': 'Buffalo Sabres', 'CGY': 'Calgary Flames', 'CAR': 'Carolina Hurricanes',
    'CHI': 'Chicago Blackhawks', 'COL': 'Colorado Avalanche', 'CBJ': 'Columbus Blue Jackets',
    'DAL': 'Dallas Stars', 'DET': 'Detroit Red Wings', 'EDM': 'Edmonton Oilers',
    'FLA': 'Florida Panthers', 'LA': 'Los Angeles Kings', 'MIN': 'Minnesota Wild',
    'MTL': 'Montreal Canadiens', 'NSH': 'Nashville Predators', 'NJ': 'New Jersey Devils',
    'NYI': 'New York Islanders', 'NYR': 'New York Rangers', 'OTT': 'Ottawa Senators',
    'PHI': 'Philadelphia Flyers', 'PIT': 'Pittsburgh Penguins', 'SJ': 'San Jose Sharks',
    'SEA': 'Seattle Kraken', 'STL': 'St. Louis Blues', 'TB': 'Tampa Bay Lightning',
    'TOR': 'Toronto Maple Leafs', 'UTA': 'Utah Hockey Club', 'VAN': 'Vancouver Canucks',
    'VGK': 'Vegas Golden Knights', 'WSH': 'Washington Capitals', 'WPG': 'Winnipeg Jets',
}

NFL_TEAMS = {
    'ARI': 'Arizona Cardinals', 'ATL': 'Atlanta Falcons', 'BAL': 'Baltimore Ravens',
    'BUF': 'Buffalo Bills', 'CAR': 'Carolina Panthers', 'CHI': 'Chicago Bears',
    'CIN': 'Cincinnati Bengals', 'CLE': 'Cleveland Browns', 'DAL': 'Dallas Cowboys',
    'DEN': 'Denver Broncos', 'DET': 'Detroit Lions', 'GB': 'Green Bay Packers',
    'HOU': 'Houston Texans', 'IND': 'Indianapolis Colts', 'JAX': 'Jacksonville Jaguars',
    'KC': 'Kansas City Chiefs', 'LV': 'Las Vegas Raiders', 'LAC': 'Los Angeles Chargers',
    'LAR': 'Los Angeles Rams', 'MIA': 'Miami Dolphins', 'MIN': 'Minnesota Vikings',
    'NE': 'New England Patriots', 'NO': 'New Orleans Saints', 'NYG': 'New York Giants',
    'NYJ': 'New York Jets', 'PHI': 'Philadelphia Eagles', 'PIT': 'Pittsburgh Steelers',
    'SF': 'San Francisco 49ers', 'SEA': 'Seattle Seahawks', 'TB': 'Tampa Bay Buccaneers',
    'TEN': 'Tennessee Titans', 'WAS': 'Washington Commanders',
}

MLB_TEAMS = {
    'ARI': 'Arizona Diamondbacks', 'ATL': 'Atlanta Braves', 'BAL': 'Baltimore Orioles',
    'BOS': 'Boston Red Sox', 'CHC': 'Chicago Cubs', 'CWS': 'Chicago White Sox',
    'CIN': 'Cincinnati Reds', 'CLE': 'Cleveland Guardians', 'COL': 'Colorado Rockies',
    'DET': 'Detroit Tigers', 'HOU': 'Houston Astros', 'KC': 'Kansas City Royals',
    'LAA': 'Los Angeles Angels', 'LAD': 'Los Angeles Dodgers', 'MIA': 'Miami Marlins',
    'MIL': 'Milwaukee Brewers', 'MIN': 'Minnesota Twins', 'NYM': 'New York Mets',
    'NYY': 'New York Yankees', 'OAK': 'Oakland Athletics', 'PHI': 'Philadelphia Phillies',
    'PIT': 'Pittsburgh Pirates', 'SD': 'San Diego Padres', 'SF': 'San Francisco Giants',
    'SEA': 'Seattle Mariners', 'STL': 'St. Louis Cardinals', 'TB': 'Tampa Bay Rays',
    'TEX': 'Texas Rangers', 'TOR': 'Toronto Blue Jays', 'WSH': 'Washington Nationals',
}

# Sports config: kalshi_series -> (odds_api_key, display_name, team_map, is_two_way)
# is_two_way: True for sports with only win/lose (no draw), False for soccer (3-way)
SPORTS_CONFIG = {
    # US Major Sports
    'KXNBAGAME': ('basketball_nba', 'NBA', NBA_TEAMS, True),
    'KXNCAAMBGAME': ('basketball_ncaab', 'NCAAB', {}, True),
    'KXNFLGAME': ('americanfootball_nfl', 'NFL', NFL_TEAMS, True),
    'KXNCAAFGAME': ('americanfootball_ncaaf', 'NCAAF', {}, True),
    'KXNHLGAME': ('icehockey_nhl', 'NHL', NHL_TEAMS, True),
    'KXMLBGAME': ('baseball_mlb', 'MLB', MLB_TEAMS, True),

    # Combat Sports
    'KXUFCFIGHT': ('mma_mixed_martial_arts', 'UFC/MMA', {}, True),

    # Soccer (3-way markets - win/draw/lose on FanDuel, but Kalshi is win only)
    'KXEPLGAME': ('soccer_epl', 'EPL', {}, False),
    'KXLALIGAGAME': ('soccer_spain_la_liga', 'La Liga', {}, False),
    'KXBUNDESLIGAGAME': ('soccer_germany_bundesliga', 'Bundesliga', {}, False),
    'KXSERIEAGAME': ('soccer_italy_serie_a', 'Serie A', {}, False),
    'KXLIGUE1GAME': ('soccer_france_ligue_one', 'Ligue 1', {}, False),
    'KXMLSGAME': ('soccer_usa_mls', 'MLS', {}, False),
    'KXUCLGAME': ('soccer_uefa_champs_league', 'Champions League', {}, False),
}

# Track which edges we've already notified about (prevent duplicate alerts)
_notified_edges = set()

# Team name mapping cache (auto-learned over time)
TEAM_NAME_CACHE_FILE = '/tmp/team_name_cache.json'


def load_team_name_cache():
    """Load previously learned team name mappings"""
    try:
        if os.path.exists(TEAM_NAME_CACHE_FILE):
            with open(TEAM_NAME_CACHE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading cache: {e}")
    return {}


def save_team_name_cache(cache):
    """Save learned team name mappings"""
    try:
        with open(TEAM_NAME_CACHE_FILE, 'w') as f:
            json.dump(cache, f)
    except Exception as e:
        print(f"Error saving cache: {e}")


TEAM_NAME_CACHE = load_team_name_cache()


def fuzzy_match_team(kalshi_name: str, fanduel_teams: List[str], threshold: float = 0.6) -> Optional[str]:
    """
    Fuzzy match Kalshi team name to FanDuel team name.
    Returns the best match if confidence is above threshold.
    """
    if not kalshi_name or not fanduel_teams:
        return None

    # Check cache first
    if kalshi_name in TEAM_NAME_CACHE:
        cached_match = TEAM_NAME_CACHE[kalshi_name]
        if cached_match in fanduel_teams:
            print(f"   Cache hit: {kalshi_name} -> {cached_match}")
            return cached_match

    best_match = None
    best_score = 0

    for fd_team in fanduel_teams:
        # Calculate similarity
        score = SequenceMatcher(None, kalshi_name.lower(), fd_team.lower()).ratio()

        # Also check if kalshi abbreviation appears in fanduel name
        if kalshi_name.lower() in fd_team.lower():
            score = max(score, 0.8)

        # Check if fanduel name contains kalshi name as substring
        kalshi_words = kalshi_name.lower().split()
        fd_words = fd_team.lower().split()
        word_matches = sum(1 for kw in kalshi_words if any(kw in fw for fw in fd_words))
        if word_matches > 0:
            score = max(score, 0.5 + (word_matches * 0.2))

        if score > best_score:
            best_score = score
            best_match = fd_team

    if best_score >= threshold:
        # Auto-learn this mapping
        TEAM_NAME_CACHE[kalshi_name] = best_match
        save_team_name_cache(TEAM_NAME_CACHE)
        print(f"   Fuzzy match ({best_score:.2f}): {kalshi_name} -> {best_match} [LEARNED]")
        return best_match

    print(f"   No match for {kalshi_name} (best: {best_match} at {best_score:.2f})")
    return None


def send_telegram_notification(edge: Dict):
    """Send Telegram notification for an arbitrage opportunity"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("   Telegram not configured - skipping notification")
        return

    # Deduplicate: don't send same alert twice
    edge_key = f"{edge['game']}_{edge['team']}_{edge['arbitrage_profit']:.1f}"
    if edge_key in _notified_edges:
        print(f"   Already notified for {edge_key} - skipping")
        return
    _notified_edges.add(edge_key)

    try:
        profit_pct = edge['arbitrage_profit']
        game = edge['game']
        sport = edge.get('sport', '')
        kalshi_method = edge['kalshi_method']
        kalshi_price = edge['kalshi_price']
        fd_team = edge['fanduel_opposite_team']
        fd_odds = edge['fanduel_opposite_odds']
        total_prob = edge['total_implied_prob']

        message = f"""
+EV OPPORTUNITY FOUND ({sport})

Game: {game}
Edge: {profit_pct:.2f}%

Strategy:
Kalshi: {kalshi_method} at ${kalshi_price:.2f}
FanDuel fair value: {fd_team} at {fd_odds:.2f}

Details:
Total implied probability: {total_prob:.2f}%
Kalshi after fees: {edge['kalshi_prob_after_fees']:.2f}%
FanDuel opposite: {edge['fanduel_opposite_prob']:.2f}%

https://kalshi-edge-finder.onrender.com
"""

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
        }

        response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            print(f"   Telegram notification sent!")
        else:
            print(f"   Telegram error: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"   Telegram notification failed: {e}")


class OddsConverter:
    @staticmethod
    def american_to_implied_prob(odds: int) -> float:
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)

    @staticmethod
    def decimal_to_implied_prob(odds: float) -> float:
        return 1 / odds

    @staticmethod
    def prob_to_american(prob: float) -> int:
        if prob >= 0.5:
            return int(-100 * prob / (1 - prob))
        else:
            return int(100 * (1 - prob) / prob)


class FanDuelAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.the-odds-api.com/v4"

    def get_odds(self, sport_key: str) -> Dict:
        """
        Fetch odds for any sport from FanDuel via The Odds API, filtered to today only.

        Returns TWO dicts:
        - odds_dict: team_name -> {odds, team, game_id}
        - games_dict: game_id -> {home, away} (teams paired by game)
        Wrapped in a single dict: {'odds': odds_dict, 'games': games_dict}
        """
        try:
            now_utc = datetime.now(timezone.utc)
            start_of_today = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_today = start_of_today + timedelta(days=1)

            url = f"{self.base_url}/sports/{sport_key}/odds/"
            params = {
                'apiKey': self.api_key,
                'regions': 'us',
                'markets': 'h2h',
                'bookmakers': 'fanduel',
                'oddsFormat': 'decimal',
                'commenceTimeFrom': start_of_today.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'commenceTimeTo': end_of_today.strftime('%Y-%m-%dT%H:%M:%SZ')
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            odds_dict = {}
            games_dict = {}

            for game in data:
                game_id = game.get('id', '')
                home_team = game.get('home_team', '')
                away_team = game.get('away_team', '')

                if home_team and away_team:
                    games_dict[game_id] = {'home': home_team, 'away': away_team}

                for bookmaker in game.get('bookmakers', []):
                    if bookmaker['key'] == 'fanduel':
                        for market in bookmaker.get('markets', []):
                            if market['key'] == 'h2h':
                                for outcome in market.get('outcomes', []):
                                    team_name = outcome['name']
                                    odds = outcome['price']
                                    odds_dict[team_name] = {
                                        'odds': odds,
                                        'team': team_name,
                                        'game_id': game_id
                                    }

            print(f"   Fetched {len(odds_dict)} FanDuel {sport_key} odds in {len(games_dict)} games (today: {start_of_today.strftime('%Y-%m-%d')})")
            return {'odds': odds_dict, 'games': games_dict}

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 422:
                print(f"   Sport {sport_key} not available on The Odds API right now (422)")
            else:
                print(f"   Error fetching FanDuel {sport_key} odds: {e}")
            return {'odds': {}, 'games': {}}
        except Exception as e:
            print(f"   Error fetching FanDuel {sport_key} odds: {e}")
            return {'odds': {}, 'games': {}}


class KalshiAPI:
    def __init__(self, api_key_id: str = None, private_key: str = None):
        self.BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
        self.api_key_id = api_key_id
        self.private_key = private_key
        self.session = requests.Session()

        headers = {'Accept': 'application/json'}
        if api_key_id:
            headers['KALSHI-ACCESS-KEY'] = api_key_id
            print("   Using authenticated Kalshi API")
        else:
            print("   Using Kalshi public API (no authentication)")

        self.session.headers.update(headers)

    def get_markets(self, series_ticker: str = None, limit: int = 200, status: str = 'open') -> List[Dict]:
        """Get markets with pagination support"""
        all_markets = []
        cursor = None

        try:
            while True:
                url = f"{self.BASE_URL}/markets"
                params = {'limit': limit, 'status': status}

                if series_ticker:
                    params['series_ticker'] = series_ticker
                if cursor:
                    params['cursor'] = cursor

                response = self.session.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()

                markets = data.get('markets', [])
                all_markets.extend(markets)

                cursor = data.get('cursor')
                if not cursor:
                    break

                print(f"   Fetched {len(markets)} markets (total: {len(all_markets)})...")
                time.sleep(0.5)

            series_info = f" from {series_ticker}" if series_ticker else ""
            print(f"   Total: {len(all_markets)} markets{series_info}")
            return all_markets

        except requests.exceptions.HTTPError as e:
            print(f"   HTTP Error {e.response.status_code}: {e}")
            return all_markets
        except Exception as e:
            print(f"   Error fetching markets: {e}")
            return all_markets

    def get_orderbook(self, ticker: str) -> Optional[Dict]:
        """Get orderbook for a specific market"""
        try:
            url = f"{self.BASE_URL}/markets/{ticker}/orderbook"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"   Orderbook error for {ticker}: {e}")
            return None


def match_kalshi_to_fanduel_game(team1_name, team2_name, fd_odds, fd_games):
    """
    Find a FanDuel game where BOTH Kalshi teams match.
    Returns (fd_team1_name, fd_team2_name) or (None, None) if no valid match.

    This prevents matching Kalshi abbreviations to random unrelated FanDuel teams.
    """
    # For each FanDuel game, try to match both Kalshi teams
    for game_id, game_info in fd_games.items():
        fd_home = game_info['home']
        fd_away = game_info['away']

        # Try matching team1 to home/away and team2 to the other
        t1_matches_home = _name_matches(team1_name, fd_home)
        t1_matches_away = _name_matches(team1_name, fd_away)
        t2_matches_home = _name_matches(team2_name, fd_home)
        t2_matches_away = _name_matches(team2_name, fd_away)

        if t1_matches_home and t2_matches_away:
            return fd_home, fd_away
        if t1_matches_away and t2_matches_home:
            return fd_away, fd_home

    return None, None


def _name_matches(kalshi_name: str, fd_name: str, threshold: float = 0.55) -> bool:
    """Check if a Kalshi team name matches a FanDuel team name."""
    k = kalshi_name.lower().strip()
    f = fd_name.lower().strip()

    # Exact match
    if k == f:
        return True

    # Kalshi name is contained in FanDuel name (e.g., "SYR" in "Syracuse Orange")
    if k in f:
        return True

    # Check if any Kalshi word is a significant part of the FanDuel name
    k_words = k.split()
    f_words = f.split()

    # Any full word match (e.g., "Syracuse" matches "Syracuse Orange")
    for kw in k_words:
        if len(kw) >= 3:  # Skip very short words
            for fw in f_words:
                if kw == fw or (len(kw) >= 4 and kw in fw):
                    return True

    # SequenceMatcher for full string similarity
    score = SequenceMatcher(None, k, f).ratio()
    if score >= threshold:
        return True

    # Check cache
    if kalshi_name in TEAM_NAME_CACHE and TEAM_NAME_CACHE[kalshi_name] == fd_name:
        return True

    return False


def find_edges(kalshi_api, fd_data, min_edge=0.005, series_ticker='KXNBAGAME',
               sport_name='NBA', team_map=None):
    """
    Find +EV opportunities by checking BOTH ways to bet on each outcome.

    For each team winning, we can either:
    1. Buy YES on that team
    2. Buy NO on their opponent

    We pick the CHEAPER option and compare against FanDuel fair value.

    CRITICAL: Both Kalshi teams must match to the SAME FanDuel game to prevent
    false matches (e.g., Kalshi "VAN vs MISS" matching to random FanDuel teams).
    """
    if team_map is None:
        team_map = {}

    fanduel_odds = fd_data['odds']
    fanduel_games = fd_data['games']
    converter = OddsConverter()
    edges = []

    print(f"\n{'='*60}")
    print(f"FINDING EDGES: {sport_name} ({series_ticker})")
    print(f"{'='*60}")
    print(f"   FanDuel has {len(fanduel_odds)} outcomes in {len(fanduel_games)} games")

    # Get all markets for the specified series
    kalshi_markets = kalshi_api.get_markets(series_ticker=series_ticker, limit=200)

    if not kalshi_markets:
        print(f"   No Kalshi markets found for {series_ticker}")
        return edges

    # Filter for TODAY only
    today_str = datetime.utcnow().strftime('%y%b%d').upper()
    today_markets = [m for m in kalshi_markets if today_str in m.get('ticker', '')]
    print(f"   TODAY's markets ({today_str}): {len(today_markets)}")

    if not today_markets:
        print(f"   No games today for {sport_name}")
        return edges

    # Group markets by game
    games = {}
    for market in today_markets:
        ticker = market.get('ticker', '')
        parts = ticker.split('-')
        if len(parts) < 3:
            continue

        game_code = '-'.join(parts[:-1])
        team_abbrev = parts[-1]

        if game_code not in games:
            games[game_code] = {}
        games[game_code][team_abbrev] = market

    print(f"   Found {len(games)} unique Kalshi games\n")

    for game_code, team_markets in games.items():
        if len(team_markets) != 2:
            continue

        team_abbrevs = list(team_markets.keys())
        team1_abbrev, team2_abbrev = team_abbrevs[0], team_abbrevs[1]
        team1_name = team_map.get(team1_abbrev, team1_abbrev)
        team2_name = team_map.get(team2_abbrev, team2_abbrev)

        # CRITICAL: Match BOTH teams to the SAME FanDuel game
        fd_team1, fd_team2 = match_kalshi_to_fanduel_game(
            team1_name, team2_name, fanduel_odds, fanduel_games
        )

        if not fd_team1 or not fd_team2:
            print(f"   Skipping {team1_name} vs {team2_name} - no matching FanDuel game")
            continue

        # Verify both teams have odds
        if fd_team1 not in fanduel_odds or fd_team2 not in fanduel_odds:
            print(f"   Skipping {team1_name} vs {team2_name} - FanDuel odds incomplete")
            continue

        # Cache the successful mappings
        if team1_name != fd_team1:
            TEAM_NAME_CACHE[team1_name] = fd_team1
        if team2_name != fd_team2:
            TEAM_NAME_CACHE[team2_name] = fd_team2
        save_team_name_cache(TEAM_NAME_CACHE)

        print(f"{'='*60}")
        print(f"   {sport_name}: {team1_name} vs {team2_name}")
        if team1_name != fd_team1:
            print(f"   Matched: {team1_name} -> {fd_team1}, {team2_name} -> {fd_team2}")

        # Get orderbooks
        ob1 = kalshi_api.get_orderbook(team_markets[team1_abbrev]['ticker'])
        ob2 = kalshi_api.get_orderbook(team_markets[team2_abbrev]['ticker'])

        if not ob1 or not ob2:
            print(f"   Missing orderbook\n")
            continue

        def get_prices(ob):
            data = ob.get('orderbook', {})
            yes_bids = data.get('yes', [])
            no_bids = data.get('no', [])
            if not yes_bids or not no_bids:
                return None, None
            yes_price = max(yes_bids, key=lambda x: x[0])[0] / 100
            no_price = max(no_bids, key=lambda x: x[0])[0] / 100
            return yes_price, no_price

        team1_yes, team1_no = get_prices(ob1)
        team2_yes, team2_no = get_prices(ob2)

        if None in [team1_yes, team1_no, team2_yes, team2_no]:
            print(f"   Incomplete prices\n")
            continue

        print(f"   {team1_name}: YES={team1_yes:.2f}, NO={team1_no:.2f}")
        print(f"   {team2_name}: YES={team2_yes:.2f}, NO={team2_no:.2f}")

        # Find BEST price for each outcome
        team1_best_price = min(team1_yes, team2_no)
        team1_method = f"YES on {team1_name}" if team1_yes <= team2_no else f"NO on {team2_name}"

        team2_best_price = min(team2_yes, team1_no)
        team2_method = f"YES on {team2_name}" if team2_yes <= team1_no else f"NO on {team1_name}"

        print(f"\n   BEST PRICES:")
        print(f"   {team1_name} wins: ${team1_best_price:.2f} ({team1_method})")
        print(f"   {team2_name} wins: ${team2_best_price:.2f} ({team2_method})")

        # Check each outcome against FanDuel
        for team_name, best_price, method, fd_name, fd_opp_name in [
            (team1_name, team1_best_price, team1_method, fd_team1, fd_team2),
            (team2_name, team2_best_price, team2_method, fd_team2, fd_team1)
        ]:
            # FanDuel odds for the OPPOSITE outcome
            fd_opposite_odds = fanduel_odds[fd_opp_name]['odds']
            fd_opposite_prob = converter.decimal_to_implied_prob(fd_opposite_odds)

            # Kalshi fee: round_up(0.07 * C * P * (1-P))
            P = best_price
            C = 100
            fee_total = math.ceil(0.07 * C * P * (1 - P) * 100) / 100
            fee_per_contract = fee_total / C
            effective_cost = P + fee_per_contract
            kalshi_prob_after_fees = effective_cost

            total_prob = kalshi_prob_after_fees + fd_opposite_prob

            if total_prob < 1.0:
                arbitrage_profit = (1.0 / total_prob) - 1

                print(f"\n   {team_name} ({fd_name}):")
                print(f"      Kalshi: ${P:.2f} ({P*100:.1f}%) - {method}")
                print(f"      Kalshi fee: ${fee_per_contract:.4f}/contract")
                print(f"      Kalshi after fees: ${effective_cost:.4f} ({kalshi_prob_after_fees*100:.2f}%)")
                print(f"      FanDuel {fd_opp_name}: {fd_opposite_odds:.2f} ({fd_opposite_prob*100:.2f}%)")
                print(f"      Total implied prob: {total_prob*100:.2f}%")
                print(f"      +EV: {arbitrage_profit*100:.2f}%")

                edge_data = {
                    'sport': sport_name,
                    'game': f"{fd_name} vs {fd_opp_name}",
                    'team': fd_name,
                    'opposite_team': fd_opp_name,
                    'kalshi_price': best_price,
                    'kalshi_fee_per_contract': fee_per_contract,
                    'kalshi_price_after_fees': effective_cost,
                    'kalshi_prob_after_fees': kalshi_prob_after_fees * 100,
                    'kalshi_method': method,
                    'fanduel_opposite_team': fd_opp_name,
                    'fanduel_opposite_odds': fd_opposite_odds,
                    'fanduel_opposite_prob': fd_opposite_prob * 100,
                    'total_implied_prob': total_prob * 100,
                    'arbitrage_profit': arbitrage_profit * 100,
                    'recommendation': f"Buy {method} on Kalshi at ${best_price:.2f} (FanDuel fair value: {fd_opp_name} at {fd_opposite_odds:.2f})",
                    'strategy': f"1. Buy {method} on Kalshi\n2. FanDuel benchmark: {fd_opp_name} at {fd_opposite_odds:.2f}"
                }

                edges.append(edge_data)
                send_telegram_notification(edge_data)
            else:
                print(f"\n   {team_name} ({fd_name}):")
                print(f"      Kalshi after fees: ${effective_cost:.4f} ({kalshi_prob_after_fees*100:.2f}%)")
                print(f"      FanDuel {fd_opp_name}: {fd_opposite_odds:.2f} ({fd_opposite_prob*100:.2f}%)")
                print(f"      Total implied prob: {total_prob*100:.2f}%")
                print(f"      No edge (total > 100%)")

        print()

    print(f"{'='*60}")
    print(f"   {sport_name}: Found {len(edges)} edges\n")
    return edges


def scan_all_sports(kalshi_api, fanduel_api, min_edge=0.005):
    """Scan all configured sports for +EV opportunities"""
    all_edges = []
    sports_scanned = []
    sports_with_games = []

    for kalshi_series, (odds_api_key, display_name, team_map, is_two_way) in SPORTS_CONFIG.items():
        print(f"\n--- Fetching FanDuel odds for {display_name} ({odds_api_key}) ---")

        fd_data = fanduel_api.get_odds(odds_api_key)

        if not fd_data['odds']:
            print(f"   No FanDuel odds for {display_name} today - skipping")
            sports_scanned.append(display_name)
            continue

        sports_scanned.append(display_name)
        sports_with_games.append(display_name)

        sport_edges = find_edges(
            kalshi_api, fd_data, min_edge,
            series_ticker=kalshi_series,
            sport_name=display_name,
            team_map=team_map
        )
        all_edges.extend(sport_edges)

        # Small delay between sports to avoid rate limits
        time.sleep(0.5)

    print(f"\n{'='*60}")
    print(f"SCAN COMPLETE")
    print(f"Sports checked: {', '.join(sports_scanned)}")
    print(f"Sports with games today: {', '.join(sports_with_games) if sports_with_games else 'None'}")
    print(f"Total edges found: {len(all_edges)}")
    print(f"{'='*60}\n")

    return all_edges, sports_scanned, sports_with_games


@app.route('/')
def index():
    """Redirect to debug view"""
    return redirect('/debug')


@app.route('/api/status')
def status():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'odds_api_configured': bool(ODDS_API_KEY),
        'kalshi_authenticated': bool(KALSHI_API_KEY_ID),
        'sports_configured': list(SPORTS_CONFIG.keys())
    })


@app.route('/api/scan', methods=['POST'])
def scan():
    """Trigger a new scan"""
    return jsonify({'message': 'Scan started'})


@app.route('/api/edges')
def get_edges():
    """Main endpoint - fetch and return edges for ALL sports"""
    try:
        min_edge = float(request.args.get('min_edge', 0.005))

        print("\n" + "="*60)
        print("STARTING FULL EDGE SCAN - ALL SPORTS")
        print("="*60)

        if not ODDS_API_KEY:
            return jsonify({'error': 'ODDS_API_KEY not configured'}), 500

        kalshi = KalshiAPI(KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY)
        fanduel = FanDuelAPI(ODDS_API_KEY)

        all_edges, sports_scanned, sports_with_games = scan_all_sports(kalshi, fanduel, min_edge)

        # Group edge counts by sport
        sport_counts = {}
        for edge in all_edges:
            sport = edge.get('sport', 'Unknown')
            sport_counts[sport] = sport_counts.get(sport, 0) + 1

        return jsonify({
            'edges': all_edges,
            'total_count': len(all_edges),
            'sport_counts': sport_counts,
            'sports_scanned': sports_scanned,
            'sports_with_games': sports_with_games,
            'timestamp': datetime.utcnow().isoformat(),
            'min_edge': min_edge
        })

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/debug')
def debug_view():
    """HTML view of edges across all sports"""
    try:
        kalshi = KalshiAPI(KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY)
        fanduel = FanDuelAPI(ODDS_API_KEY)

        all_edges, sports_scanned, sports_with_games = scan_all_sports(kalshi, fanduel, min_edge=0.005)

        # Sport badge colors
        sport_colors = {
            'NBA': '#e74c3c', 'NCAAB': '#3498db', 'NFL': '#2ecc71', 'NCAAF': '#27ae60',
            'NHL': '#9b59b6', 'MLB': '#e67e22', 'UFC/MMA': '#e74c3c',
            'EPL': '#3d195b', 'La Liga': '#ff4b44', 'Bundesliga': '#d20515',
            'Serie A': '#024494', 'Ligue 1': '#091c3e', 'MLS': '#5f259f',
            'Champions League': '#0a1128',
        }

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Kalshi Edge Finder - All Sports</title>
            <meta http-equiv="refresh" content="300">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                    color: #eee;
                    min-height: 100vh;
                }}
                .container {{ max-width: 1200px; margin: 0 auto; }}
                h1 {{
                    color: #00ff88;
                    text-align: center;
                    font-size: 2.5em;
                    margin-bottom: 10px;
                }}
                .subtitle {{
                    text-align: center;
                    color: #aaa;
                    margin-bottom: 10px;
                    font-size: 1.1em;
                }}
                .sports-list {{
                    text-align: center;
                    color: #888;
                    margin-bottom: 30px;
                    font-size: 0.9em;
                }}
                .edge {{
                    background: #16213e;
                    padding: 20px;
                    margin: 15px 0;
                    border-radius: 12px;
                    border-left: 4px solid #00ff88;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.3);
                }}
                .edge:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 6px 12px rgba(0,255,136,0.2);
                    transition: all 0.3s ease;
                }}
                .game {{
                    font-size: 0.9em;
                    color: #888;
                    margin-bottom: 8px;
                }}
                .team {{
                    font-weight: bold;
                    color: #ff6b6b;
                    font-size: 1.3em;
                    margin-bottom: 10px;
                }}
                .row {{
                    display: flex;
                    justify-content: space-between;
                    margin: 8px 0;
                    padding: 8px 0;
                    border-bottom: 1px solid #2a2a3e;
                }}
                .label {{ color: #aaa; }}
                .value {{ font-weight: 600; }}
                .positive {{ color: #00ff88; font-weight: bold; font-size: 1.1em; }}
                .method {{
                    background: #0f3460;
                    padding: 6px 12px;
                    border-radius: 6px;
                    display: inline-block;
                    margin-top: 10px;
                    font-size: 0.95em;
                }}
                .count {{
                    text-align: center;
                    font-size: 1.2em;
                    margin: 20px 0;
                    padding: 15px;
                    background: #0f3460;
                    border-radius: 8px;
                }}
                .sport-badge {{
                    display: inline-block;
                    padding: 4px 10px;
                    border-radius: 4px;
                    font-size: 0.75em;
                    font-weight: bold;
                    margin-left: 10px;
                    color: white;
                }}
                .no-arb {{
                    text-align: center;
                    padding: 60px 20px;
                    color: #888;
                    font-size: 1.2em;
                }}
                .no-arb p {{ margin: 15px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Kalshi Edge Finder</h1>
                <div class="subtitle">+EV opportunities across all sports | Auto-refreshes every 5 minutes</div>
                <div class="sports-list">Scanning: {', '.join(sports_scanned)} | Games today: {', '.join(sports_with_games) if sports_with_games else 'None'}</div>
                <div class="count">
        """

        if all_edges:
            html += f"Found <strong style='color: #00ff88;'>{len(all_edges)}</strong> +EV opportunities!"
        else:
            html += "No +EV opportunities right now"

        html += "</div>"

        if all_edges:
            for edge in all_edges:
                sport = edge.get('sport', 'Unknown')
                badge_color = sport_colors.get(sport, '#666')
                html += f"""
            <div class="edge">
                <div class="game">{edge['game']}<span class="sport-badge" style="background: {badge_color};">{sport}</span></div>
                <div class="team">{edge['team']}</div>
                <div class="row">
                    <span class="label">Kalshi:</span>
                    <span class="value">${edge['kalshi_price']:.2f} -> ${edge['kalshi_price_after_fees']:.4f} after fees ({edge['kalshi_prob_after_fees']:.2f}%)</span>
                </div>
                <div class="row">
                    <span class="label">FanDuel Fair Value:</span>
                    <span class="value">{edge['opposite_team']} at {edge['fanduel_opposite_odds']:.2f} ({edge['fanduel_opposite_prob']:.1f}%)</span>
                </div>
                <div class="row">
                    <span class="label">Total Probability:</span>
                    <span class="value">{edge['total_implied_prob']:.2f}%</span>
                </div>
                <div class="row">
                    <span class="label">Edge:</span>
                    <span class="positive">{edge['arbitrage_profit']:.2f}% +EV</span>
                </div>
                <div class="method">{edge['recommendation']}</div>
            </div>
            """
        else:
            html += """
            <div class="no-arb">
                <p>All markets are currently efficient</p>
                <p style="font-size: 0.95em; color: #aaa;">No +EV opportunities available right now.</p>
                <p style="font-size: 0.9em; margin-top: 25px; color: #666;">Best times: during live games, breaking news, early morning</p>
            </div>
            """

        html += """
            </div>
        </body>
        </html>
        """
        return html

    except Exception as e:
        return f"<h1 style='color: red;'>Error:</h1><pre>{str(e)}</pre>", 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
