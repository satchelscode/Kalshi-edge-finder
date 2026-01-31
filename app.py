import os
import requests
import math
import time
import re
import uuid
import base64
from flask import Flask, render_template, jsonify, request, redirect
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import json
from difflib import SequenceMatcher
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding

app = Flask(__name__)

# Configuration
ODDS_API_KEY = os.environ.get('ODDS_API_KEY')
KALSHI_API_KEY_ID = os.environ.get('KALSHI_API_KEY_ID')
KALSHI_PRIVATE_KEY = os.environ.get('KALSHI_PRIVATE_KEY')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# ============================================================
# AUTO-TRADE CONFIGURATION
# ============================================================
AUTO_TRADE_ENABLED = os.environ.get('AUTO_TRADE_ENABLED', 'false').lower() == 'true'
TARGET_PROFIT = float(os.environ.get('TARGET_PROFIT', '1.00'))  # Target profit per trade in dollars
MIN_EDGE_PCT = float(os.environ.get('MIN_EDGE_PCT', '5.0'))     # Minimum edge % to auto-trade
MAX_CONTRACTS_PER_ORDER = int(os.environ.get('MAX_CONTRACTS_PER_ORDER', '10'))  # Safety cap
MAX_DAILY_TRADES = int(os.environ.get('MAX_DAILY_TRADES', '20'))  # Max trades per day
MAX_DAILY_SPEND = float(os.environ.get('MAX_DAILY_SPEND', '20.00'))  # Max total spend per day

# Track auto-trade state
_trades_today = []  # List of {ticker, side, count, price, cost, time}
_traded_markets = set()  # Tickers we've already traded (no double-trading)

# ============================================================
# SPORTS CONFIGURATION
# ============================================================

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

# Moneyline game markets: kalshi_series -> (odds_api_key, display_name, team_map)
MONEYLINE_SPORTS = {
    # Currently in-season
    'KXNBAGAME': ('basketball_nba', 'NBA', NBA_TEAMS),
    'KXNCAAMBGAME': ('basketball_ncaab', 'NCAAB', {}),
    'KXNHLGAME': ('icehockey_nhl', 'NHL', NHL_TEAMS),
    'KXUFCFIGHT': ('mma_mixed_martial_arts', 'UFC/MMA', {}),
    'KXEPLGAME': ('soccer_epl', 'EPL', {}),
    'KXLALIGAGAME': ('soccer_spain_la_liga', 'La Liga', {}),
    'KXBUNDESLIGAGAME': ('soccer_germany_bundesliga', 'Bundesliga', {}),
    'KXSERIEAGAME': ('soccer_italy_serie_a', 'Serie A', {}),
    'KXLIGUE1GAME': ('soccer_france_ligue_one', 'Ligue 1', {}),
    'KXUCLGAME': ('soccer_uefa_champs_league', 'Champions League', {}),
    # Off-season (uncomment when active):
    # 'KXNFLGAME': ('americanfootball_nfl', 'NFL', NFL_TEAMS),
    # 'KXNCAAFGAME': ('americanfootball_ncaaf', 'NCAAF', {}),
    # 'KXMLBGAME': ('baseball_mlb', 'MLB', MLB_TEAMS),
    # 'KXMLSGAME': ('soccer_usa_mls', 'MLS', {}),
}

# Spread markets: kalshi_series -> (odds_api_sport, display_name, team_map)
SPREAD_SPORTS = {
    'KXNBASPREAD': ('basketball_nba', 'NBA Spread', NBA_TEAMS),
    'KXNHLSPREAD': ('icehockey_nhl', 'NHL Spread', NHL_TEAMS),
    # 'KXNFLSPREAD': ('americanfootball_nfl', 'NFL Spread', NFL_TEAMS),
}

# Total (over/under) markets: kalshi_series -> (odds_api_sport, display_name)
TOTAL_SPORTS = {
    'KXNBATOTAL': ('basketball_nba', 'NBA Total'),
    'KXNHLTOTAL': ('icehockey_nhl', 'NHL Total'),
    # 'KXNFLTOTAL': ('americanfootball_nfl', 'NFL Total'),
}

# Player prop markets: kalshi_series -> (odds_api_sport, odds_api_market, display_name)
PLAYER_PROP_SPORTS = {
    'KXNBAPTS': ('basketball_nba', 'player_points', 'NBA Points'),
    'KXNBAREB': ('basketball_nba', 'player_rebounds', 'NBA Rebounds'),
    'KXNBAAST': ('basketball_nba', 'player_assists', 'NBA Assists'),
    'KXNBA3PT': ('basketball_nba', 'player_threes', 'NBA 3-Pointers'),
}

# Track which edges we've already notified about
_notified_edges = set()

# Team name mapping cache
TEAM_NAME_CACHE_FILE = '/tmp/team_name_cache.json'


def load_team_name_cache():
    try:
        if os.path.exists(TEAM_NAME_CACHE_FILE):
            with open(TEAM_NAME_CACHE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading cache: {e}")
    return {}


def save_team_name_cache(cache):
    try:
        with open(TEAM_NAME_CACHE_FILE, 'w') as f:
            json.dump(cache, f)
    except Exception as e:
        print(f"Error saving cache: {e}")


TEAM_NAME_CACHE = load_team_name_cache()


def _name_matches(kalshi_name: str, fd_name: str, threshold: float = 0.55) -> bool:
    k = kalshi_name.lower().strip()
    f = fd_name.lower().strip()
    if k == f:
        return True
    if k in f:
        return True
    k_words = k.split()
    f_words = f.split()
    for kw in k_words:
        if len(kw) >= 3:
            for fw in f_words:
                if kw == fw or (len(kw) >= 4 and kw in fw):
                    return True
    score = SequenceMatcher(None, k, f).ratio()
    if score >= threshold:
        return True
    if kalshi_name in TEAM_NAME_CACHE and TEAM_NAME_CACHE[kalshi_name] == fd_name:
        return True
    return False


def match_kalshi_to_fanduel_game(team1_name, team2_name, fd_games):
    """Match BOTH Kalshi teams to the SAME FanDuel game."""
    for game_id, game_info in fd_games.items():
        fd_home = game_info['home']
        fd_away = game_info['away']
        t1h = _name_matches(team1_name, fd_home)
        t1a = _name_matches(team1_name, fd_away)
        t2h = _name_matches(team2_name, fd_home)
        t2a = _name_matches(team2_name, fd_away)
        if t1h and t2a:
            return fd_home, fd_away, game_id
        if t1a and t2h:
            return fd_away, fd_home, game_id
    return None, None, None


def _match_player_name(kalshi_name: str, fd_name: str) -> bool:
    """Match player names between Kalshi and FanDuel."""
    k = kalshi_name.lower().strip()
    f = fd_name.lower().strip()
    if k == f:
        return True
    # Check last name match (most reliable)
    k_parts = k.split()
    f_parts = f.split()
    if k_parts and f_parts:
        if k_parts[-1] == f_parts[-1]:  # Same last name
            # Also check first initial or first name
            if k_parts[0][0] == f_parts[0][0]:
                return True
    score = SequenceMatcher(None, k, f).ratio()
    return score >= 0.75


def kalshi_fee(price: float, contracts: int = 100) -> float:
    """Calculate Kalshi taker fee per contract."""
    fee_total = math.ceil(0.07 * contracts * price * (1 - price) * 100) / 100
    return fee_total / contracts


def send_telegram_notification(edge: Dict):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    edge_key = f"{edge.get('market_type','')}{edge['game']}_{edge['team']}_{edge['arbitrage_profit']:.1f}"
    if edge_key in _notified_edges:
        return
    _notified_edges.add(edge_key)
    try:
        market_type = edge.get('market_type', 'Moneyline')
        sport = edge.get('sport', '')
        message = f"""+EV OPPORTUNITY ({sport} - {market_type})

{edge['game']}
{edge['recommendation']}

Edge: {edge['arbitrage_profit']:.2f}%
Total implied prob: {edge['total_implied_prob']:.2f}%
Kalshi after fees: {edge['kalshi_prob_after_fees']:.2f}%
FanDuel fair value: {edge['fanduel_opposite_prob']:.2f}%

https://kalshi-edge-finder.onrender.com"""
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': message}, timeout=10)
    except Exception as e:
        print(f"   Telegram failed: {e}")


def calculate_contracts(price: float, target_profit: float = 1.0) -> int:
    """
    Calculate number of contracts to target a specific profit.

    On Kalshi, each contract pays $1 if it resolves in your favor.
    Profit per contract = $1.00 - price - fee_per_contract
    Contracts needed = ceil(target_profit / profit_per_contract)
    """
    fee = kalshi_fee(price)
    profit_per_contract = 1.0 - price - fee
    if profit_per_contract <= 0:
        return 0
    contracts = math.ceil(target_profit / profit_per_contract)
    return max(1, contracts)


def _reset_daily_trades_if_needed():
    """Reset trade tracking at the start of each new day."""
    global _trades_today
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if _trades_today and _trades_today[0].get('date') != today:
        _trades_today = []
        _traded_markets.clear()


def _daily_spend() -> float:
    """Total dollars spent on trades today."""
    return sum(t.get('cost', 0) for t in _trades_today)


def auto_trade_edge(kalshi_api, edge: Dict) -> Optional[Dict]:
    """
    Automatically place a trade on Kalshi for a detected edge.

    Safety checks:
    - AUTO_TRADE_ENABLED must be true
    - Edge must exceed MIN_EDGE_PCT
    - Must not have already traded this market
    - Must not exceed daily trade count or spend limits
    - Private key must be loaded

    Returns order result or None.
    """
    if not AUTO_TRADE_ENABLED:
        return None

    if not kalshi_api.private_key:
        return None

    _reset_daily_trades_if_needed()

    # Check edge threshold
    edge_pct = edge.get('arbitrage_profit', 0)
    if edge_pct < MIN_EDGE_PCT:
        print(f"   Auto-trade skip: edge {edge_pct:.1f}% < min {MIN_EDGE_PCT}%")
        return None

    # Check daily limits
    if len(_trades_today) >= MAX_DAILY_TRADES:
        print(f"   Auto-trade skip: daily trade limit reached ({MAX_DAILY_TRADES})")
        return None
    if _daily_spend() >= MAX_DAILY_SPEND:
        print(f"   Auto-trade skip: daily spend limit reached (${MAX_DAILY_SPEND:.2f})")
        return None

    # Determine what to trade from the edge info
    ticker = edge.get('ticker')
    side = edge.get('trade_side')
    price = edge.get('kalshi_price')
    if not ticker or not side or price is None:
        print(f"   Auto-trade skip: missing trade info (ticker={ticker}, side={side})")
        return None

    # Don't double-trade the same market
    trade_key = f"{ticker}_{side}"
    if trade_key in _traded_markets:
        print(f"   Auto-trade skip: already traded {trade_key}")
        return None

    # Calculate order size
    contracts = calculate_contracts(price, TARGET_PROFIT)
    contracts = min(contracts, MAX_CONTRACTS_PER_ORDER)
    if contracts <= 0:
        return None

    price_cents = int(round(price * 100))
    total_cost = price * contracts

    # Final spend check
    if _daily_spend() + total_cost > MAX_DAILY_SPEND:
        # Reduce contracts to stay within budget
        remaining_budget = MAX_DAILY_SPEND - _daily_spend()
        contracts = int(remaining_budget / price)
        if contracts <= 0:
            print(f"   Auto-trade skip: would exceed daily spend limit")
            return None

    print(f"\n   AUTO-TRADE: {contracts}x {side} {ticker} @ ${price:.2f} "
          f"(edge: {edge_pct:.1f}%, target profit: ${TARGET_PROFIT:.2f})")

    # Place the order
    order = kalshi_api.place_order(ticker, side, contracts, price_cents, action='buy')

    if order:
        trade_record = {
            'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            'time': datetime.now(timezone.utc).strftime('%H:%M:%S'),
            'ticker': ticker,
            'side': side,
            'count': contracts,
            'price': price,
            'cost': price * contracts,
            'edge_pct': edge_pct,
            'order_id': order.get('order_id', 'unknown'),
            'sport': edge.get('sport', ''),
            'game': edge.get('game', ''),
            'market_type': edge.get('market_type', ''),
        }
        _trades_today.append(trade_record)
        _traded_markets.add(trade_key)

        # Send Telegram notification about the trade
        _send_trade_notification(trade_record)

    return order


def _send_trade_notification(trade: Dict):
    """Send Telegram alert when a trade is placed."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        message = f"""AUTO-TRADE PLACED

{trade['game']} ({trade['sport']} - {trade['market_type']})
{trade['count']}x {trade['side'].upper()} {trade['ticker']} @ ${trade['price']:.2f}

Cost: ${trade['cost']:.2f}
Edge: {trade['edge_pct']:.1f}%
Order ID: {trade['order_id']}
Trades today: {len(_trades_today)} | Spent: ${_daily_spend():.2f}/${MAX_DAILY_SPEND:.2f}"""
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': message}, timeout=10)
    except Exception as e:
        print(f"   Trade notification failed: {e}")


class OddsConverter:
    @staticmethod
    def decimal_to_implied_prob(odds: float) -> float:
        return 1 / odds


class FanDuelAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.the-odds-api.com/v4"

    def _fetch(self, sport_key: str, markets: str = 'h2h') -> list:
        """Base fetch method with today-only filtering."""
        try:
            now_utc = datetime.now(timezone.utc)
            start_of_today = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_today = start_of_today + timedelta(days=1)

            url = f"{self.base_url}/sports/{sport_key}/odds/"
            params = {
                'apiKey': self.api_key,
                'regions': 'us',
                'markets': markets,
                'bookmakers': 'fanduel',
                'oddsFormat': 'decimal',
                'commenceTimeFrom': start_of_today.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'commenceTimeTo': end_of_today.strftime('%Y-%m-%dT%H:%M:%SZ')
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 'unknown'
            print(f"   FanDuel {sport_key}/{markets}: HTTP {status}")
            return []
        except Exception as e:
            print(f"   FanDuel {sport_key}/{markets} error: {e}")
            return []

    def get_moneyline(self, sport_key: str) -> Dict:
        """Get h2h moneyline odds."""
        data = self._fetch(sport_key, 'h2h')
        odds_dict = {}
        games_dict = {}
        for game in data:
            game_id = game.get('id', '')
            home = game.get('home_team', '')
            away = game.get('away_team', '')
            if home and away:
                games_dict[game_id] = {'home': home, 'away': away}
            for bm in game.get('bookmakers', []):
                if bm['key'] == 'fanduel':
                    for mkt in bm.get('markets', []):
                        if mkt['key'] == 'h2h':
                            for o in mkt.get('outcomes', []):
                                odds_dict[o['name']] = {'odds': o['price'], 'game_id': game_id}
        print(f"   FanDuel {sport_key} moneyline: {len(odds_dict)} outcomes in {len(games_dict)} games")
        return {'odds': odds_dict, 'games': games_dict}

    def get_spreads(self, sport_key: str) -> Dict:
        """Get spread lines. Returns {game_id: {team_name: {point, odds}}}."""
        data = self._fetch(sport_key, 'spreads')
        spreads = {}
        games_dict = {}
        for game in data:
            game_id = game.get('id', '')
            home = game.get('home_team', '')
            away = game.get('away_team', '')
            if home and away:
                games_dict[game_id] = {'home': home, 'away': away}
            for bm in game.get('bookmakers', []):
                if bm['key'] == 'fanduel':
                    for mkt in bm.get('markets', []):
                        if mkt['key'] == 'spreads':
                            game_spreads = {}
                            for o in mkt.get('outcomes', []):
                                game_spreads[o['name']] = {
                                    'point': o.get('point', 0),
                                    'odds': o['price']
                                }
                            if game_spreads:
                                spreads[game_id] = game_spreads
        print(f"   FanDuel {sport_key} spreads: {len(spreads)} games")
        return {'spreads': spreads, 'games': games_dict}

    def get_totals(self, sport_key: str) -> Dict:
        """Get over/under lines. Returns {game_id: {point, over_odds, under_odds}}."""
        data = self._fetch(sport_key, 'totals')
        totals = {}
        games_dict = {}
        for game in data:
            game_id = game.get('id', '')
            home = game.get('home_team', '')
            away = game.get('away_team', '')
            if home and away:
                games_dict[game_id] = {'home': home, 'away': away}
            for bm in game.get('bookmakers', []):
                if bm['key'] == 'fanduel':
                    for mkt in bm.get('markets', []):
                        if mkt['key'] == 'totals':
                            game_total = {}
                            for o in mkt.get('outcomes', []):
                                if o['name'] == 'Over':
                                    game_total['over_odds'] = o['price']
                                    game_total['point'] = o.get('point', 0)
                                elif o['name'] == 'Under':
                                    game_total['under_odds'] = o['price']
                            if 'over_odds' in game_total and 'under_odds' in game_total:
                                totals[game_id] = game_total
        print(f"   FanDuel {sport_key} totals: {len(totals)} games")
        return {'totals': totals, 'games': games_dict}

    def get_player_props(self, sport_key: str, market_key: str) -> Dict:
        """Get player prop lines. Returns {game_id: [{name, point, odds, description}]}."""
        data = self._fetch(sport_key, market_key)
        props = {}
        games_dict = {}
        for game in data:
            game_id = game.get('id', '')
            home = game.get('home_team', '')
            away = game.get('away_team', '')
            if home and away:
                games_dict[game_id] = {'home': home, 'away': away}
            for bm in game.get('bookmakers', []):
                if bm['key'] == 'fanduel':
                    for mkt in bm.get('markets', []):
                        if mkt['key'] == market_key:
                            game_props = []
                            for o in mkt.get('outcomes', []):
                                if o.get('name') == 'Over':
                                    game_props.append({
                                        'player': o.get('description', ''),
                                        'point': o.get('point', 0),
                                        'over_odds': o['price'],
                                    })
                            if game_props:
                                props[game_id] = game_props
        total_props = sum(len(v) for v in props.values())
        print(f"   FanDuel {sport_key} {market_key}: {total_props} props in {len(props)} games")
        return {'props': props, 'games': games_dict}


class KalshiAPI:
    def __init__(self, api_key_id: str = None, private_key: str = None):
        self.BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
        self.api_key_id = api_key_id
        self.private_key = None
        self.session = requests.Session()
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        if api_key_id:
            headers['KALSHI-ACCESS-KEY'] = api_key_id
        self.session.headers.update(headers)

        # Load RSA private key for authenticated (trading) requests
        if private_key:
            try:
                # Handle newlines encoded as literal \n in env vars
                key_str = private_key.replace('\\n', '\n')
                self.private_key = serialization.load_pem_private_key(
                    key_str.encode('utf-8'), password=None
                )
                print("   Kalshi RSA private key loaded successfully")
            except Exception as e:
                print(f"   Warning: Could not load Kalshi private key: {e}")
                self.private_key = None

    def _sign_request(self, method: str, path: str) -> Dict[str, str]:
        """Generate RSA-PSS signed headers for authenticated Kalshi endpoints."""
        timestamp = str(int(datetime.now(timezone.utc).timestamp() * 1000))
        msg = f"{timestamp}{method}{path}"
        signature = self.private_key.sign(
            msg.encode('utf-8'),
            asym_padding.PSS(
                mgf=asym_padding.MGF1(hashes.SHA256()),
                salt_length=asym_padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )
        return {
            'KALSHI-ACCESS-KEY': self.api_key_id,
            'KALSHI-ACCESS-SIGNATURE': base64.b64encode(signature).decode('utf-8'),
            'KALSHI-ACCESS-TIMESTAMP': timestamp,
        }

    def get_markets(self, series_ticker: str, limit: int = 200, status: str = 'open') -> List[Dict]:
        all_markets = []
        cursor = None
        try:
            while True:
                params = {'limit': limit, 'status': status, 'series_ticker': series_ticker}
                if cursor:
                    params['cursor'] = cursor
                response = self.session.get(f"{self.BASE_URL}/markets", params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                markets = data.get('markets', [])
                all_markets.extend(markets)
                cursor = data.get('cursor')
                if not cursor:
                    break
                time.sleep(1.0)  # Respect Kalshi rate limits between paginated requests
            print(f"   Kalshi {series_ticker}: {len(all_markets)} markets")
            return all_markets
        except Exception as e:
            print(f"   Kalshi {series_ticker} error: {e}")
            return all_markets

    def get_orderbook(self, ticker: str) -> Optional[Dict]:
        try:
            response = self.session.get(f"{self.BASE_URL}/markets/{ticker}/orderbook", timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return None

    def get_balance(self) -> Optional[float]:
        """Get account balance in dollars. Requires RSA auth."""
        if not self.private_key:
            return None
        try:
            path = "/trade-api/v2/portfolio/balance"
            headers = self._sign_request("GET", path)
            response = self.session.get(f"{self.BASE_URL}/portfolio/balance",
                                        headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('balance', 0) / 100  # cents to dollars
        except Exception as e:
            print(f"   Balance check error: {e}")
            return None

    def place_order(self, ticker: str, side: str, count: int, price_cents: int,
                    action: str = 'buy') -> Optional[Dict]:
        """
        Place an order on Kalshi.

        Args:
            ticker: Market ticker (e.g., KXNBAGAME-26JAN31MIA-MIA)
            side: 'yes' or 'no'
            count: Number of contracts
            price_cents: Price in cents (1-99)
            action: 'buy' or 'sell'

        Returns:
            Order response dict or None on failure
        """
        if not self.private_key:
            print("   Cannot place order: no private key loaded")
            return None

        path = "/trade-api/v2/portfolio/orders"
        headers = self._sign_request("POST", path)

        body = {
            'ticker': ticker,
            'side': side,
            'action': action,
            'type': 'limit',
            'count': count,
            'client_order_id': str(uuid.uuid4()),
        }
        if side == 'yes':
            body['yes_price'] = price_cents
        else:
            body['no_price'] = price_cents

        try:
            response = self.session.post(f"{self.BASE_URL}/portfolio/orders",
                                         headers=headers, json=body, timeout=10)
            response.raise_for_status()
            result = response.json()
            order = result.get('order', result)
            print(f"   ORDER PLACED: {action} {count}x {side} {ticker} @ {price_cents}c "
                  f"(order_id: {order.get('order_id', 'unknown')})")
            return order
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else 'unknown'
            body_text = e.response.text if e.response else ''
            print(f"   ORDER FAILED ({status}): {action} {count}x {side} {ticker} @ {price_cents}c - {body_text}")
            return None
        except Exception as e:
            print(f"   ORDER ERROR: {e}")
            return None


def get_best_yes_price(ob: Dict) -> Optional[float]:
    """Get best YES price from orderbook (what you'd pay to buy YES)."""
    data = ob.get('orderbook', {})
    yes_bids = data.get('yes', [])
    if not yes_bids:
        return None
    return max(yes_bids, key=lambda x: x[0])[0] / 100


def get_best_no_price(ob: Dict) -> Optional[float]:
    """Get best NO price from orderbook."""
    data = ob.get('orderbook', {})
    no_bids = data.get('no', [])
    if not no_bids:
        return None
    return max(no_bids, key=lambda x: x[0])[0] / 100


# ============================================================
# MONEYLINE EDGE FINDER (existing logic, cleaned up)
# ============================================================

def find_moneyline_edges(kalshi_api, fd_data, series_ticker, sport_name, team_map):
    converter = OddsConverter()
    fanduel_odds = fd_data['odds']
    fanduel_games = fd_data['games']
    edges = []
    today_str = datetime.utcnow().strftime('%y%b%d').upper()

    kalshi_markets = kalshi_api.get_markets(series_ticker)
    today_markets = [m for m in kalshi_markets if today_str in m.get('ticker', '')]
    if not today_markets:
        return edges

    # Group by game
    games = {}
    for m in today_markets:
        ticker = m.get('ticker', '')
        parts = ticker.split('-')
        if len(parts) < 3:
            continue
        game_code = '-'.join(parts[:-1])
        team_abbrev = parts[-1]
        if game_code not in games:
            games[game_code] = {}
        games[game_code][team_abbrev] = m

    for game_code, team_markets in games.items():
        if len(team_markets) != 2:
            continue
        abbrevs = list(team_markets.keys())
        t1_name = team_map.get(abbrevs[0], abbrevs[0])
        t2_name = team_map.get(abbrevs[1], abbrevs[1])

        fd_t1, fd_t2, _ = match_kalshi_to_fanduel_game(t1_name, t2_name, fanduel_games)
        if not fd_t1 or fd_t1 not in fanduel_odds or fd_t2 not in fanduel_odds:
            continue

        ob1 = kalshi_api.get_orderbook(team_markets[abbrevs[0]]['ticker'])
        time.sleep(0.15)
        ob2 = kalshi_api.get_orderbook(team_markets[abbrevs[1]]['ticker'])
        time.sleep(0.15)
        if not ob1 or not ob2:
            continue

        t1_yes = get_best_yes_price(ob1)
        t1_no = get_best_no_price(ob1)
        t2_yes = get_best_yes_price(ob2)
        t2_no = get_best_no_price(ob2)
        if None in [t1_yes, t1_no, t2_yes, t2_no]:
            continue

        t1_ticker = team_markets[abbrevs[0]]['ticker']
        t2_ticker = team_markets[abbrevs[1]]['ticker']

        for name, best_p, method, fd_opp, trade_ticker, trade_side in [
            (t1_name, min(t1_yes, t2_no),
             f"YES on {t1_name}" if t1_yes <= t2_no else f"NO on {t2_name}", fd_t2,
             t1_ticker if t1_yes <= t2_no else t2_ticker,
             'yes' if t1_yes <= t2_no else 'no'),
            (t2_name, min(t2_yes, t1_no),
             f"YES on {t2_name}" if t2_yes <= t1_no else f"NO on {t1_name}", fd_t1,
             t2_ticker if t2_yes <= t1_no else t1_ticker,
             'yes' if t2_yes <= t1_no else 'no'),
        ]:
            fee = kalshi_fee(best_p)
            eff = best_p + fee
            fd_prob = converter.decimal_to_implied_prob(fanduel_odds[fd_opp]['odds'])
            total = eff + fd_prob
            if total < 1.0:
                profit = (1.0 / total - 1) * 100
                edge = {
                    'market_type': 'Moneyline',
                    'sport': sport_name,
                    'game': f"{fd_t1} vs {fd_t2}",
                    'team': name,
                    'opposite_team': fd_opp,
                    'kalshi_price': best_p,
                    'kalshi_price_after_fees': eff,
                    'kalshi_prob_after_fees': eff * 100,
                    'kalshi_method': method,
                    'fanduel_opposite_team': fd_opp,
                    'fanduel_opposite_odds': fanduel_odds[fd_opp]['odds'],
                    'fanduel_opposite_prob': fd_prob * 100,
                    'total_implied_prob': total * 100,
                    'arbitrage_profit': profit,
                    'recommendation': f"Buy {method} on Kalshi at ${best_p:.2f} (FanDuel: {fd_opp} at {fanduel_odds[fd_opp]['odds']:.2f})",
                    'ticker': trade_ticker,
                    'trade_side': trade_side,
                }
                edges.append(edge)
                send_telegram_notification(edge)
                auto_trade_edge(kalshi_api, edge)
    return edges


# ============================================================
# SPREAD EDGE FINDER
# ============================================================

def find_spread_edges(kalshi_api, fd_data, series_ticker, sport_name, team_map):
    """
    Compare Kalshi spread markets against FanDuel spread lines.

    Kalshi: "GSW wins by 4.5+" is a YES/NO binary at some price
    FanDuel: GSW -4.5 at decimal odds

    If Kalshi YES price (after fees) implies lower prob than FanDuel for same spread = +EV
    """
    converter = OddsConverter()
    fd_spreads = fd_data['spreads']
    fd_games = fd_data['games']
    edges = []
    today_str = datetime.utcnow().strftime('%y%b%d').upper()

    kalshi_markets = kalshi_api.get_markets(series_ticker)
    today_markets = [m for m in kalshi_markets if today_str in m.get('ticker', '')]
    if not today_markets:
        return edges

    # Step 1: Group Kalshi markets by game code (both teams together)
    # Ticker format: KXNBASPREAD-26JAN30DETGSW-GSW4
    game_groups = {}  # game_code -> [{ticker, team_abbrev, floor_strike, market}]
    for m in today_markets:
        ticker = m.get('ticker', '')
        parts = ticker.split('-')
        if len(parts) < 3:
            continue

        game_part = parts[1]  # e.g., 26JAN30DETGSW
        game_code = f"{parts[0]}-{game_part}"
        team_spread_part = parts[-1]  # e.g., GSW4

        match = re.match(r'^([A-Z]+?)(\d+)$', team_spread_part)
        if not match:
            continue
        team_abbrev = match.group(1)

        floor_strike = m.get('floor_strike')
        if floor_strike is None:
            subtitle = m.get('subtitle', '') or m.get('title', '') or ''
            spread_match = re.search(r'(\d+\.?\d*)', subtitle)
            if spread_match:
                floor_strike = float(spread_match.group(1))
            else:
                continue
        floor_strike = float(floor_strike)

        if game_code not in game_groups:
            game_groups[game_code] = []
        game_groups[game_code].append({
            'ticker': ticker,
            'team_abbrev': team_abbrev,
            'team_name': team_map.get(team_abbrev, team_abbrev),
            'floor_strike': floor_strike,
            'market': m,
        })

    # Step 2: For each game group, find the two team abbreviations and match BOTH to same FD game
    for game_code, markets in game_groups.items():
        # Get unique team abbrevs in this game
        team_abbrevs = list(set(mk['team_abbrev'] for mk in markets))
        if len(team_abbrevs) < 2:
            continue

        t1_name = team_map.get(team_abbrevs[0], team_abbrevs[0])
        t2_name = team_map.get(team_abbrevs[1], team_abbrevs[1])

        # Require BOTH teams match the SAME FanDuel game
        fd_t1, fd_t2, matched_game_id = match_kalshi_to_fanduel_game(t1_name, t2_name, fd_games)
        if not fd_t1 or not matched_game_id or matched_game_id not in fd_spreads:
            continue

        fd_game_spreads = fd_spreads[matched_game_id]
        print(f"   Spread match: {t1_name} vs {t2_name} -> {fd_t1} vs {fd_t2}")

        # Step 3: For each market in this game, compare to FanDuel spread
        for mk in markets:
            team_name = mk['team_name']
            floor_strike = mk['floor_strike']
            ticker = mk['ticker']

            # Find which FD team this Kalshi team corresponds to
            fd_team_name = None
            if _name_matches(team_name, fd_t1):
                fd_team_name = fd_t1
            elif _name_matches(team_name, fd_t2):
                fd_team_name = fd_t2
            else:
                continue

            if fd_team_name not in fd_game_spreads:
                continue

            fd_spread = fd_game_spreads[fd_team_name]
            fd_point = abs(fd_spread['point'])
            fd_odds = fd_spread['odds']

            # Only compare EXACT matching spread lines (within 0.5 points)
            if abs(floor_strike - fd_point) > 0.5:
                continue

            # Get Kalshi orderbook
            ob = kalshi_api.get_orderbook(ticker)
            if not ob:
                continue
            time.sleep(0.15)

            yes_price = get_best_yes_price(ob)
            if yes_price is None:
                continue

            fee = kalshi_fee(yes_price)
            eff = yes_price + fee

            fd_prob = converter.decimal_to_implied_prob(fd_odds)

            if eff < fd_prob:
                edge_pct = ((fd_prob / eff) - 1) * 100
                game_name = f"{fd_games[matched_game_id]['away']} at {fd_games[matched_game_id]['home']}"
                edge = {
                    'market_type': 'Spread',
                    'sport': sport_name,
                    'game': game_name,
                    'team': f"{team_name} -{floor_strike}",
                    'opposite_team': fd_team_name,
                    'kalshi_price': yes_price,
                    'kalshi_price_after_fees': eff,
                    'kalshi_prob_after_fees': eff * 100,
                    'kalshi_method': f"YES on {team_name} -{floor_strike}",
                    'fanduel_opposite_team': f"{fd_team_name} {fd_spread['point']}",
                    'fanduel_opposite_odds': fd_odds,
                    'fanduel_opposite_prob': fd_prob * 100,
                    'total_implied_prob': (eff + (1 - fd_prob)) * 100,
                    'arbitrage_profit': edge_pct,
                    'recommendation': f"Buy YES {team_name} -{floor_strike} on Kalshi at ${yes_price:.2f} (FanDuel: {fd_team_name} {fd_spread['point']} at {fd_odds:.2f})",
                    'ticker': ticker,
                    'trade_side': 'yes',
                }
                edges.append(edge)
                send_telegram_notification(edge)
                auto_trade_edge(kalshi_api, edge)

    return edges


# ============================================================
# TOTALS EDGE FINDER
# ============================================================

def find_total_edges(kalshi_api, fd_data, series_ticker, sport_name, team_map):
    """
    Compare Kalshi total (over/under) markets against FanDuel totals.

    Kalshi: "Over 224.5 points" at some YES price
    FanDuel: Over 224.5 at decimal odds

    Match by game (both teams) + exact line value, compare prices.
    """
    converter = OddsConverter()
    fd_totals = fd_data['totals']
    fd_games = fd_data['games']
    edges = []
    today_str = datetime.utcnow().strftime('%y%b%d').upper()

    kalshi_markets = kalshi_api.get_markets(series_ticker)
    today_markets = [m for m in kalshi_markets if today_str in m.get('ticker', '')]
    if not today_markets:
        return edges

    # Step 1: Group by game code to identify both teams
    # Ticker format: KXNBATOTAL-26JAN30DETGSW-239
    game_groups = {}  # game_code -> [market_info]
    for m in today_markets:
        ticker = m.get('ticker', '')
        parts = ticker.split('-')
        if len(parts) < 3:
            continue

        game_part = parts[1]
        game_code = f"{parts[0]}-{game_part}"

        floor_strike = m.get('floor_strike')
        if floor_strike is None:
            line_part = parts[-1]
            try:
                floor_strike = float(line_part) + 0.5
            except ValueError:
                continue
        floor_strike = float(floor_strike)

        if game_code not in game_groups:
            game_groups[game_code] = {'game_part': game_part, 'markets': []}
        game_groups[game_code]['markets'].append({
            'ticker': ticker,
            'floor_strike': floor_strike,
            'market': m,
        })

    # Step 2: Match each game group to FanDuel by finding team abbrevs in game_part
    for game_code, group in game_groups.items():
        game_part = group['game_part']

        # Find which FanDuel game this matches by checking team abbreviations in game_part
        matched_game_id = None
        for gid, ginfo in fd_games.items():
            home_found = False
            away_found = False
            for abbr, full_name in team_map.items():
                if abbr in game_part:
                    if _name_matches(full_name, ginfo['home']):
                        home_found = True
                    elif _name_matches(full_name, ginfo['away']):
                        away_found = True
            # Require BOTH teams found in the game_part
            if home_found and away_found:
                matched_game_id = gid
                break

        if not matched_game_id or matched_game_id not in fd_totals:
            continue

        fd_total = fd_totals[matched_game_id]
        fd_line = fd_total['point']
        game_name = f"{fd_games[matched_game_id]['away']} at {fd_games[matched_game_id]['home']}"

        # Step 3: For each total market in this game, compare to FanDuel
        for mk in group['markets']:
            floor_strike = mk['floor_strike']
            ticker = mk['ticker']

            # Only compare EXACT matching lines (within 0.5 points)
            if abs(floor_strike - fd_line) > 0.5:
                continue

            ob = kalshi_api.get_orderbook(ticker)
            if not ob:
                continue
            time.sleep(0.15)

            yes_price = get_best_yes_price(ob)  # YES = Over
            no_price = get_best_no_price(ob)    # NO = Under

            # Check Over: Kalshi YES vs FanDuel Over
            if yes_price is not None:
                fee = kalshi_fee(yes_price)
                eff = yes_price + fee
                fd_over_prob = converter.decimal_to_implied_prob(fd_total['over_odds'])
                if eff < fd_over_prob:
                    edge_pct = ((fd_over_prob / eff) - 1) * 100
                    edge = {
                        'market_type': 'Total',
                        'sport': sport_name,
                        'game': game_name,
                        'team': f"Over {floor_strike}",
                        'opposite_team': f"Under {floor_strike}",
                        'kalshi_price': yes_price,
                        'kalshi_price_after_fees': eff,
                        'kalshi_prob_after_fees': eff * 100,
                        'kalshi_method': f"YES Over {floor_strike}",
                        'fanduel_opposite_team': f"Over {fd_line}",
                        'fanduel_opposite_odds': fd_total['over_odds'],
                        'fanduel_opposite_prob': fd_over_prob * 100,
                        'total_implied_prob': (eff + (1 - fd_over_prob)) * 100,
                        'arbitrage_profit': edge_pct,
                        'recommendation': f"Buy YES Over {floor_strike} on Kalshi at ${yes_price:.2f} (FanDuel Over {fd_line} at {fd_total['over_odds']:.2f})",
                        'ticker': ticker,
                        'trade_side': 'yes',
                    }
                    edges.append(edge)
                    send_telegram_notification(edge)
                    auto_trade_edge(kalshi_api, edge)

            # Check Under: Kalshi NO (= Under) vs FanDuel Under
            if no_price is not None:
                under_cost = no_price
                fee = kalshi_fee(under_cost)
                eff = under_cost + fee
                fd_under_prob = converter.decimal_to_implied_prob(fd_total['under_odds'])
                if eff < fd_under_prob:
                    edge_pct = ((fd_under_prob / eff) - 1) * 100
                    edge = {
                        'market_type': 'Total',
                        'sport': sport_name,
                        'game': game_name,
                        'team': f"Under {floor_strike}",
                        'opposite_team': f"Over {floor_strike}",
                        'kalshi_price': under_cost,
                        'kalshi_price_after_fees': eff,
                        'kalshi_prob_after_fees': eff * 100,
                        'kalshi_method': f"NO (Under) {floor_strike}",
                        'fanduel_opposite_team': f"Under {fd_line}",
                        'fanduel_opposite_odds': fd_total['under_odds'],
                        'fanduel_opposite_prob': fd_under_prob * 100,
                        'total_implied_prob': (eff + (1 - fd_under_prob)) * 100,
                        'arbitrage_profit': edge_pct,
                        'recommendation': f"Buy NO (Under {floor_strike}) on Kalshi at ${under_cost:.2f} (FanDuel Under {fd_line} at {fd_total['under_odds']:.2f})",
                        'ticker': ticker,
                        'trade_side': 'no',
                    }
                    edges.append(edge)
                    send_telegram_notification(edge)
                    auto_trade_edge(kalshi_api, edge)

    return edges


# ============================================================
# PLAYER PROPS EDGE FINDER
# ============================================================

def find_player_prop_edges(kalshi_api, fd_data, series_ticker, sport_name, fd_market_key):
    """
    Compare Kalshi player prop markets against FanDuel player props.

    Kalshi: "Nikola Jokic: 25+ points" at YES price
    FanDuel: "Nikola Jokic Over 24.5 points" at decimal odds

    Match by player name + line value, compare prices.
    """
    converter = OddsConverter()
    fd_props = fd_data['props']
    fd_games = fd_data['games']
    edges = []
    today_str = datetime.utcnow().strftime('%y%b%d').upper()

    kalshi_markets = kalshi_api.get_markets(series_ticker)
    today_markets = [m for m in kalshi_markets if today_str in m.get('ticker', '')]
    if not today_markets:
        return edges

    # Build FanDuel lookup: {player_name_lower: [{point, over_odds, game_id}]}
    fd_lookup = {}
    for game_id, props in fd_props.items():
        for prop in props:
            player = prop['player'].lower().strip()
            if player not in fd_lookup:
                fd_lookup[player] = []
            fd_lookup[player].append({
                'point': prop['point'],
                'over_odds': prop['over_odds'],
                'game_id': game_id,
            })

    for m in today_markets:
        ticker = m.get('ticker', '')
        title = m.get('title', '')
        subtitle = m.get('subtitle', '')

        # Extract player name and line from title: "Nikola Jokic: 25+ points"
        # or from subtitle: "Nikola Jokic: 25+"
        prop_match = re.match(r'^(.+?):\s*(\d+\.?\d*)\+', title or subtitle or '')
        if not prop_match:
            continue

        player_name = prop_match.group(1).strip()
        kalshi_line = float(prop_match.group(2))

        # Find matching FanDuel prop
        best_fd_match = None
        best_fd_score = 0

        for fd_player, fd_entries in fd_lookup.items():
            if _match_player_name(player_name, fd_player):
                for entry in fd_entries:
                    # FanDuel uses X.5, Kalshi uses X+. "25+" on Kalshi = "Over 24.5" on FanDuel
                    fd_line = entry['point']
                    # Match if lines are equivalent (Kalshi 25+ ~= FanDuel Over 24.5)
                    if abs(kalshi_line - (fd_line + 0.5)) <= 1.0:
                        score = 1.0 - abs(kalshi_line - (fd_line + 0.5))
                        if score > best_fd_score:
                            best_fd_score = score
                            best_fd_match = entry

        if not best_fd_match:
            continue

        ob = kalshi_api.get_orderbook(ticker)
        if not ob:
            continue
        time.sleep(0.15)

        yes_price = get_best_yes_price(ob)
        if yes_price is None:
            continue

        fee = kalshi_fee(yes_price)
        eff = yes_price + fee

        fd_over_prob = converter.decimal_to_implied_prob(best_fd_match['over_odds'])

        # Kalshi YES = player hits prop. FanDuel Over = same thing.
        # If Kalshi is cheaper than FanDuel implies -> +EV
        if eff < fd_over_prob:
            edge_pct = ((fd_over_prob / eff) - 1) * 100
            game_id = best_fd_match['game_id']
            game_info = fd_games.get(game_id, {})
            game_name = f"{game_info.get('away', '?')} at {game_info.get('home', '?')}"

            edge = {
                'market_type': 'Player Prop',
                'sport': sport_name,
                'game': game_name,
                'team': f"{player_name} {kalshi_line}+",
                'opposite_team': f"Under {best_fd_match['point']}",
                'kalshi_price': yes_price,
                'kalshi_price_after_fees': eff,
                'kalshi_prob_after_fees': eff * 100,
                'kalshi_method': f"YES {player_name} {kalshi_line}+",
                'fanduel_opposite_team': f"{player_name} Over {best_fd_match['point']}",
                'fanduel_opposite_odds': best_fd_match['over_odds'],
                'fanduel_opposite_prob': fd_over_prob * 100,
                'total_implied_prob': (eff + (1 - fd_over_prob)) * 100,
                'arbitrage_profit': edge_pct,
                'recommendation': f"Buy YES {player_name} {kalshi_line}+ on Kalshi at ${yes_price:.2f} (FanDuel Over {best_fd_match['point']} at {best_fd_match['over_odds']:.2f})",
                'ticker': ticker,
                'trade_side': 'yes',
            }
            edges.append(edge)
            send_telegram_notification(edge)
            auto_trade_edge(kalshi_api, edge)

    return edges


# ============================================================
# MAIN SCANNER
# ============================================================

def scan_all_sports(kalshi_api, fanduel_api):
    all_edges = []
    sports_scanned = []
    sports_with_games = []

    # 1. Moneyline markets
    for kalshi_series, (odds_key, name, team_map) in MONEYLINE_SPORTS.items():
        print(f"\n--- {name} Moneyline ({kalshi_series}) ---")
        fd = fanduel_api.get_moneyline(odds_key)
        sports_scanned.append(name)
        if not fd['odds']:
            continue
        sports_with_games.append(name)
        edges = find_moneyline_edges(kalshi_api, fd, kalshi_series, name, team_map)
        all_edges.extend(edges)
        print(f"   {name} moneyline: {len(edges)} edges")
        time.sleep(1.0)

    # 2. Spread markets
    for kalshi_series, (odds_key, name, team_map) in SPREAD_SPORTS.items():
        print(f"\n--- {name} ({kalshi_series}) ---")
        fd = fanduel_api.get_spreads(odds_key)
        sports_scanned.append(name)
        if not fd['spreads']:
            continue
        sports_with_games.append(name)
        edges = find_spread_edges(kalshi_api, fd, kalshi_series, name, team_map)
        all_edges.extend(edges)
        print(f"   {name}: {len(edges)} edges")
        time.sleep(1.0)

    # 3. Total markets
    for kalshi_series, (odds_key, name) in TOTAL_SPORTS.items():
        print(f"\n--- {name} ({kalshi_series}) ---")
        # Use team_map from moneyline config if available
        team_map = {}
        for ms, (mk, mn, tm) in MONEYLINE_SPORTS.items():
            if mk == odds_key:
                team_map = tm
                break
        fd = fanduel_api.get_totals(odds_key)
        sports_scanned.append(name)
        if not fd['totals']:
            continue
        sports_with_games.append(name)
        edges = find_total_edges(kalshi_api, fd, kalshi_series, name, team_map)
        all_edges.extend(edges)
        print(f"   {name}: {len(edges)} edges")
        time.sleep(1.0)

    # 4. Player props
    for kalshi_series, (odds_key, fd_market, name) in PLAYER_PROP_SPORTS.items():
        print(f"\n--- {name} ({kalshi_series}) ---")
        fd = fanduel_api.get_player_props(odds_key, fd_market)
        sports_scanned.append(name)
        if not fd['props']:
            continue
        sports_with_games.append(name)
        edges = find_player_prop_edges(kalshi_api, fd, kalshi_series, name, fd_market)
        all_edges.extend(edges)
        print(f"   {name}: {len(edges)} edges")
        time.sleep(1.0)

    print(f"\n{'='*60}")
    print(f"SCAN COMPLETE")
    print(f"Markets checked: {', '.join(sports_scanned)}")
    print(f"Active today: {', '.join(sports_with_games) if sports_with_games else 'None'}")
    print(f"Total edges: {len(all_edges)}")
    print(f"{'='*60}\n")

    return all_edges, sports_scanned, sports_with_games


# ============================================================
# ROUTES
# ============================================================

@app.route('/')
def index():
    return redirect('/debug')


@app.route('/api/status')
def status():
    return jsonify({
        'status': 'ok',
        'odds_api_configured': bool(ODDS_API_KEY),
        'kalshi_authenticated': bool(KALSHI_API_KEY_ID),
        'auto_trade_enabled': AUTO_TRADE_ENABLED,
        'auto_trade_config': {
            'target_profit': TARGET_PROFIT,
            'min_edge_pct': MIN_EDGE_PCT,
            'max_contracts': MAX_CONTRACTS_PER_ORDER,
            'max_daily_trades': MAX_DAILY_TRADES,
            'max_daily_spend': MAX_DAILY_SPEND,
        },
        'trades_today': len(_trades_today),
        'daily_spend': _daily_spend(),
        'moneyline_sports': list(MONEYLINE_SPORTS.keys()),
        'spread_sports': list(SPREAD_SPORTS.keys()),
        'total_sports': list(TOTAL_SPORTS.keys()),
        'player_prop_sports': list(PLAYER_PROP_SPORTS.keys()),
    })


@app.route('/api/trades')
def get_trades():
    _reset_daily_trades_if_needed()
    return jsonify({
        'trades': _trades_today,
        'count': len(_trades_today),
        'daily_spend': _daily_spend(),
        'max_daily_spend': MAX_DAILY_SPEND,
        'max_daily_trades': MAX_DAILY_TRADES,
        'auto_trade_enabled': AUTO_TRADE_ENABLED,
    })


@app.route('/api/edges')
def get_edges():
    try:
        kalshi = KalshiAPI(KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY)
        fanduel = FanDuelAPI(ODDS_API_KEY)
        all_edges, scanned, active = scan_all_sports(kalshi, fanduel)
        return jsonify({
            'edges': all_edges,
            'total_count': len(all_edges),
            'sports_scanned': scanned,
            'sports_with_games': active,
            'timestamp': datetime.utcnow().isoformat(),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/debug')
def debug_view():
    try:
        kalshi = KalshiAPI(KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY)
        fanduel = FanDuelAPI(ODDS_API_KEY)
        all_edges, scanned, active = scan_all_sports(kalshi, fanduel)

        type_colors = {
            'Moneyline': '#e74c3c', 'Spread': '#3498db',
            'Total': '#e67e22', 'Player Prop': '#9b59b6',
        }

        html = f"""<!DOCTYPE html>
<html><head>
<title>Kalshi Edge Finder</title>
<meta http-equiv="refresh" content="300">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 20px; background: linear-gradient(135deg, #1a1a2e, #16213e); color: #eee; min-height: 100vh; }}
.container {{ max-width: 1200px; margin: 0 auto; }}
h1 {{ color: #00ff88; text-align: center; font-size: 2.2em; margin-bottom: 5px; }}
.sub {{ text-align: center; color: #aaa; margin-bottom: 5px; }}
.info {{ text-align: center; color: #666; font-size: 0.85em; margin-bottom: 20px; }}
.count {{ text-align: center; font-size: 1.1em; margin: 15px 0; padding: 12px; background: #0f3460; border-radius: 8px; }}
.edge {{ background: #16213e; padding: 18px; margin: 12px 0; border-radius: 10px; border-left: 4px solid #00ff88; }}
.edge:hover {{ transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,255,136,0.15); transition: all 0.2s; }}
.game {{ font-size: 0.85em; color: #888; margin-bottom: 6px; }}
.team {{ font-weight: bold; color: #ff6b6b; font-size: 1.2em; margin-bottom: 8px; }}
.row {{ display: flex; justify-content: space-between; margin: 6px 0; padding: 6px 0; border-bottom: 1px solid #2a2a3e; }}
.label {{ color: #aaa; }} .value {{ font-weight: 600; }}
.pos {{ color: #00ff88; font-weight: bold; font-size: 1.1em; }}
.method {{ background: #0f3460; padding: 5px 10px; border-radius: 5px; display: inline-block; margin-top: 8px; font-size: 0.9em; }}
.badge {{ display: inline-block; padding: 3px 8px; border-radius: 3px; font-size: 0.7em; font-weight: bold; margin-left: 8px; color: white; }}
.no-edge {{ text-align: center; padding: 50px 20px; color: #888; }}
</style></head><body><div class="container">
<h1>Kalshi Edge Finder</h1>
<div class="sub">Moneylines + Spreads + Totals + Player Props | Auto-refresh 5min</div>
<div class="info">Scanning: {', '.join(scanned)} | Active: {', '.join(active) if active else 'None'}</div>
<div class="count" style="background:{'#1a4d2e' if AUTO_TRADE_ENABLED else '#0f3460'}">
<strong>Auto-Trade: {'ON' if AUTO_TRADE_ENABLED else 'OFF'}</strong>
{f' | Target: ${TARGET_PROFIT:.2f}/trade | Min edge: {MIN_EDGE_PCT}% | Trades today: {len(_trades_today)}/{MAX_DAILY_TRADES} | Spent: ${_daily_spend():.2f}/${MAX_DAILY_SPEND:.2f}' if AUTO_TRADE_ENABLED else ' | Set AUTO_TRADE_ENABLED=true to enable'}
</div>
<div class="count">"""

        if all_edges:
            html += f"<strong style='color:#00ff88'>{len(all_edges)}</strong> +EV opportunities"
        else:
            html += "No +EV opportunities right now"
        html += "</div>"

        if all_edges:
            for e in all_edges:
                mt = e.get('market_type', 'Moneyline')
                bc = type_colors.get(mt, '#666')
                html += f"""<div class="edge">
<div class="game">{e['game']}<span class="badge" style="background:{bc}">{mt}</span><span class="badge" style="background:#444">{e['sport']}</span></div>
<div class="team">{e['team']}</div>
<div class="row"><span class="label">Kalshi:</span><span class="value">${e['kalshi_price']:.2f} -> ${e['kalshi_price_after_fees']:.4f} after fees ({e['kalshi_prob_after_fees']:.1f}%)</span></div>
<div class="row"><span class="label">FanDuel:</span><span class="value">{e['fanduel_opposite_team']} at {e['fanduel_opposite_odds']:.2f} ({e['fanduel_opposite_prob']:.1f}%)</span></div>
<div class="row"><span class="label">Edge:</span><span class="pos">{e['arbitrage_profit']:.2f}% +EV</span></div>
<div class="method">{e['recommendation']}</div></div>"""
        else:
            html += '<div class="no-edge"><p>Markets efficient right now</p><p style="color:#666;font-size:0.9em">Best times: live games, breaking news, early morning</p></div>'

        html += "</div></body></html>"
        return html

    except Exception as e:
        return f"<h1 style='color:red'>Error</h1><pre>{e}</pre>", 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
