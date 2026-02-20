import os
import requests
import math
import time
import re
import base64
import hashlib
import threading
from flask import Flask, render_template, jsonify, request, redirect, Response
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Tuple
import json
from difflib import SequenceMatcher
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

app = Flask(__name__)

# Configuration
ODDS_API_KEY = os.environ.get('ODDS_API_KEY')
KALSHI_API_KEY_ID = os.environ.get('KALSHI_API_KEY_ID')
KALSHI_PRIVATE_KEY = os.environ.get('KALSHI_PRIVATE_KEY')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

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
    # 'KXNHLGAME': ('icehockey_nhl', 'NHL', NHL_TEAMS),  # Paused — NHL arb not working properly
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
    # 'KXNHLSPREAD': ('icehockey_nhl', 'NHL Spread', NHL_TEAMS),  # Paused — NHL arb not working properly
    'KXNCAAMBSPREAD': ('basketball_ncaab', 'NCAAB Spread', {}),
    'KXEPLSPREAD': ('soccer_epl', 'EPL Spread', {}),
    'KXLALIGASPREAD': ('soccer_spain_la_liga', 'La Liga Spread', {}),
    'KXBUNDESLIGASPREAD': ('soccer_germany_bundesliga', 'Bundesliga Spread', {}),
    'KXSERIEASPREAD': ('soccer_italy_serie_a', 'Serie A Spread', {}),
    'KXLIGUE1SPREAD': ('soccer_france_ligue_one', 'Ligue 1 Spread', {}),
    'KXUCLSPREAD': ('soccer_uefa_champs_league', 'UCL Spread', {}),
    # 'KXNFLSPREAD': ('americanfootball_nfl', 'NFL Spread', NFL_TEAMS),
}

# Total (over/under) markets: kalshi_series -> (odds_api_sport, display_name)
TOTAL_SPORTS = {
    'KXNBATOTAL': ('basketball_nba', 'NBA Total'),
    # 'KXNHLTOTAL': ('icehockey_nhl', 'NHL Total'),  # Paused — NHL arb not working properly
    'KXNCAAMBTOTAL': ('basketball_ncaab', 'NCAAB Total'),
    'KXEPLTOTAL': ('soccer_epl', 'EPL Total'),
    'KXLALIGATOTAL': ('soccer_spain_la_liga', 'La Liga Total'),
    'KXBUNDESLIGATOTAL': ('soccer_germany_bundesliga', 'Bundesliga Total'),
    'KXSERIEATOTAL': ('soccer_italy_serie_a', 'Serie A Total'),
    'KXLIGUE1TOTAL': ('soccer_france_ligue_one', 'Ligue 1 Total'),
    'KXUCLTOTAL': ('soccer_uefa_champs_league', 'UCL Total'),
    # 'KXNFLTOTAL': ('americanfootball_nfl', 'NFL Total'),
}

# Player prop markets: kalshi_series -> (odds_api_sport, odds_api_market, display_name)
PLAYER_PROP_SPORTS = {
    # NBA
    'KXNBAPTS': ('basketball_nba', 'player_points', 'NBA Points'),
    'KXNBAREB': ('basketball_nba', 'player_rebounds', 'NBA Rebounds'),
    'KXNBAAST': ('basketball_nba', 'player_assists', 'NBA Assists'),
    'KXNBA3PT': ('basketball_nba', 'player_threes', 'NBA 3-Pointers'),
    # NHL
    'KXNHLPTS': ('icehockey_nhl', 'player_points', 'NHL Points'),
    'KXNHLAST': ('icehockey_nhl', 'player_assists', 'NHL Assists'),
    'KXNHLSAVES': ('icehockey_nhl', 'player_total_saves', 'NHL Saves'),
}

# BTTS (Both Teams To Score) markets: kalshi_series -> (odds_api_sport, display_name)
BTTS_SPORTS = {
    'KXEPLBTTS': ('soccer_epl', 'EPL BTTS'),
    'KXLALIGABTTS': ('soccer_spain_la_liga', 'La Liga BTTS'),
    'KXBUNDESLIGABTTS': ('soccer_germany_bundesliga', 'Bundesliga BTTS'),
    'KXSERIEABTTS': ('soccer_italy_serie_a', 'Serie A BTTS'),
    'KXLIGUE1BTTS': ('soccer_france_ligue_one', 'Ligue 1 BTTS'),
    'KXUCLBTTS': ('soccer_uefa_champs_league', 'UCL BTTS'),
}

# Tennis match-winner markets: kalshi_series -> ([odds_api_sport_keys], display_name)
# The Odds API uses tournament-specific keys; we try all and use whichever has data
ATP_TOURNAMENT_KEYS = [
    'tennis_atp_aus_open_singles', 'tennis_atp_french_open', 'tennis_atp_wimbledon',
    'tennis_atp_us_open', 'tennis_atp_indian_wells', 'tennis_atp_miami_open',
    'tennis_atp_madrid_open', 'tennis_atp_italian_open', 'tennis_atp_canadian_open',
    'tennis_atp_cincinnati_open', 'tennis_atp_shanghai_masters', 'tennis_atp_paris_masters',
    'tennis_atp_monte_carlo_masters', 'tennis_atp_dubai', 'tennis_atp_qatar_open',
    'tennis_atp_china_open',
]
WTA_TOURNAMENT_KEYS = [
    'tennis_wta_aus_open_singles', 'tennis_wta_french_open', 'tennis_wta_wimbledon',
    'tennis_wta_us_open', 'tennis_wta_indian_wells', 'tennis_wta_miami_open',
    'tennis_wta_madrid_open', 'tennis_wta_italian_open', 'tennis_wta_canadian_open',
    'tennis_wta_cincinnati_open', 'tennis_wta_dubai', 'tennis_wta_qatar_open',
    'tennis_wta_china_open', 'tennis_wta_wuhan_open',
]
TENNIS_SPORTS = {
    'KXATPMATCH': (ATP_TOURNAMENT_KEYS, 'ATP Tennis'),
    'KXWTAMATCH': (WTA_TOURNAMENT_KEYS, 'WTA Tennis'),
    'KXATPCHALLENGERMATCH': (ATP_TOURNAMENT_KEYS, 'ATP Challenger'),
    'KXWTACHALLENGERMATCH': (WTA_TOURNAMENT_KEYS, 'WTA Challenger'),
}

# Auto-trade configuration
AUTO_TRADE_ENABLED = True
MAX_POSITIONS = 999  # No practical limit
TARGET_PROFIT = 5.00  # Target $5 profit per FD arb trade
MAX_RISK = 250.00     # Max total cost per FD arb order
MIN_EDGE_PERCENT = 2.0  # Only notify/display edges >= 2% over fair value
LIVE_PROP_MIN_EDGE = 5.0  # Live props need 5%+ (FD one-way comparison, noisier)
MAX_BOOK_DIVERGENCE = 0.10  # Reject edge if FD & Pinnacle devigged probs differ by >10pp

# Multi-book fair value configuration
# Pre-game: FanDuel + Pinnacle combined devig (require both)
# Live: Pinnacle only devig (sharpest book with live odds)
PREGAME_BOOKS = ['fanduel', 'pinnacle']
LIVE_BOOK = 'pinnacle'
FAIR_VALUE_BOOKS = list(set(PREGAME_BOOKS + [LIVE_BOOK]))  # Combined for API fetch

# Crypto & Index: higher conviction (near-expiry / known outcomes), size more aggressively
CRYPTO_TARGET_PROFIT = 15.00   # Target $15 profit per crypto trade
CRYPTO_MAX_RISK = 1000.00      # Max $1000 cost per crypto order
INDEX_TARGET_PROFIT = 15.00    # Target $15 profit per index trade (S&P/Nasdaq)
INDEX_MAX_RISK = 1000.00       # Max $1000 cost per index order

# Track which edges we've already notified about
_notified_edges = set()

# ============================================================
# ORDER TRACKER (uses Kalshi API for positions, in-memory for session)
# ============================================================

class OrderTracker:
    def __init__(self):
        # In-memory set of tickers we've traded THIS session (fast lookup)
        self._session_tickers = set()
        # Cached positions from Kalshi API (refreshed each scan)
        self._api_tickers = set()
        self._position_count = 0

    def refresh_from_api(self, kalshi_api):
        """Pull current positions from Kalshi API to sync state."""
        try:
            positions = kalshi_api.get_positions()
            self._api_tickers = set()
            for pos in positions:
                ticker = pos.get('ticker', '')
                # position > 0 = YES held, position < 0 = NO held, 0 = settled/closed
                position = pos.get('position', 0)
                if ticker and position != 0:
                    self._api_tickers.add(ticker)
            self._position_count = len(self._api_tickers)
            print(f"   OrderTracker synced: {self._position_count} active positions from Kalshi API")
        except Exception as e:
            print(f"   OrderTracker sync error: {e}")

    def has_position(self, ticker: str) -> bool:
        return ticker in self._session_tickers or ticker in self._api_tickers

    def has_game_position(self, ticker: str) -> bool:
        """Check if we already have ANY position in this game/event.
        Prevents betting both sides of the same game.
        e.g. if we have KXNBAGAME-26JAN31SASCHA-SAS, this returns True
        for KXNBAGAME-26JAN31SASCHA-CHA (same game, different team)."""
        # Extract game code: everything except the last segment after the last dash
        parts = ticker.split('-')
        if len(parts) < 3:
            return self.has_position(ticker)
        game_prefix = '-'.join(parts[:-1])  # e.g. KXNBAGAME-26JAN31SASCHA
        all_tickers = self._session_tickers | self._api_tickers
        for t in all_tickers:
            if t.startswith(game_prefix):
                return True
        return False

    def can_trade(self) -> bool:
        total = len(self._session_tickers | self._api_tickers)
        return total < MAX_POSITIONS

    def add_order(self, ticker: str, order_info: Dict):
        self._session_tickers.add(ticker)

    def get_open_count(self) -> int:
        return len(self._session_tickers | self._api_tickers)


# Global order tracker instance
_order_tracker = OrderTracker()

# Background scanner state
_scan_lock = threading.Lock()
_scan_cache = {
    'edges': [],
    'sports_scanned': [],
    'sports_with_games': [],
    'timestamp': None,
    'scan_count': 0,
    'is_scanning': False,
    'prop_comparisons': [],
}
SCAN_REST_SECONDS = 30  # Rest between scans

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


def match_kalshi_to_fanduel_game(team1_name, team2_name, fd_games, kalshi_date_str=None):
    """Match BOTH Kalshi teams to the SAME FanDuel game.
    If kalshi_date_str is provided (e.g., '26JAN31'), prefer games on that date."""
    # Parse Kalshi date if provided, to filter FD games by date
    kalshi_date = None
    if kalshi_date_str:
        try:
            kalshi_date = datetime.strptime(kalshi_date_str, '%y%b%d').replace(tzinfo=timezone.utc)
        except Exception:
            pass

    candidates = []
    for game_id, game_info in fd_games.items():
        fd_home = game_info['home']
        fd_away = game_info['away']
        t1h = _name_matches(team1_name, fd_home)
        t1a = _name_matches(team1_name, fd_away)
        t2h = _name_matches(team2_name, fd_home)
        t2a = _name_matches(team2_name, fd_away)
        matched = None
        if t1h and t2a:
            matched = (fd_home, fd_away, game_id)
        elif t1a and t2h:
            matched = (fd_away, fd_home, game_id)
        if matched:
            # Score by date proximity if we have both dates
            if kalshi_date and game_info.get('commence_time'):
                try:
                    ct = datetime.fromisoformat(game_info['commence_time'].replace('Z', '+00:00'))
                    # Game should be on the Kalshi date (allow same day or next day early AM)
                    day_diff = abs((ct.date() - kalshi_date.date()).days)
                    candidates.append((day_diff, matched))
                except Exception:
                    candidates.append((0, matched))
            else:
                candidates.append((0, matched))

    if not candidates:
        return None, None, None

    # Return the closest date match
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


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
            # Require first name to match (not just initial) to avoid
            # false matches like Amen Thompson vs Ausar Thompson
            if k_parts[0] == f_parts[0]:
                return True
            # Allow match if first 3+ chars match (handles nicknames)
            if len(k_parts[0]) >= 3 and len(f_parts[0]) >= 3 and k_parts[0][:3] == f_parts[0][:3]:
                return True
    # Strict fuzzy match as last resort
    score = SequenceMatcher(None, k, f).ratio()
    return score >= 0.85


def kalshi_fee(price: float, contracts: int = 100) -> float:
    """Calculate Kalshi taker fee per contract."""
    fee_total = math.ceil(0.07 * contracts * price * (1 - price) * 100) / 100
    return fee_total / contracts


def is_game_live(commence_time_str: str) -> bool:
    """Check if a game is currently live based on commence_time."""
    if not commence_time_str:
        return False
    try:
        ct = datetime.fromisoformat(commence_time_str.replace('Z', '+00:00'))
        return ct <= datetime.now(timezone.utc)
    except Exception:
        return False


def _get_eastern_now() -> datetime:
    """Get current time in US Eastern (handles EST/EDT automatically)."""
    return datetime.now(ZoneInfo('America/New_York'))


def _get_today_date_strs() -> set:
    """Return date strings for both UTC and US Eastern to handle evening overlap.
    Kalshi tickers use US Eastern dates but UTC can roll to the next day during evening games."""
    now_utc = datetime.now(timezone.utc)
    utc_str = now_utc.strftime('%y%b%d').upper()
    eastern_str = _get_eastern_now().strftime('%y%b%d').upper()
    return {utc_str, eastern_str}


def are_odds_stale(commence_time_str: str, last_update_str: str) -> bool:
    """Check if live odds are stale.
    Returns True if the game has started but odds haven't updated since before
    the game started or are more than 15 seconds old.
    Returns False for pre-game games or if we can't determine staleness."""
    if not commence_time_str or not last_update_str:
        return False
    try:
        ct = datetime.fromisoformat(commence_time_str.replace('Z', '+00:00'))
        lu = datetime.fromisoformat(last_update_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        # Game hasn't started yet — odds are fine
        if ct > now:
            return False
        # Game is live: odds are stale if last_update is before game start
        # or more than 15 seconds old (API data must be near real-time for live)
        if lu < ct or (now - lu) > timedelta(seconds=15):
            return True
        return False
    except Exception:
        return False


def books_diverge(per_book_detail: dict) -> bool:
    """Return True if FanDuel and Pinnacle devigged probs disagree by more than MAX_BOOK_DIVERGENCE.
    Catches secretly-live games where one book has stale odds even though commence_time says pre-game."""
    if not per_book_detail or len(per_book_detail) < 2:
        return False
    probs = list(per_book_detail.values())
    return (max(probs) - min(probs)) > MAX_BOOK_DIVERGENCE


def send_telegram_notification(edge: Dict):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    # Don't notify for edges below the minimum threshold
    if edge.get('arbitrage_profit', 0) < MIN_EDGE_PERCENT:
        return
    edge_key = f"{edge.get('market_type','')}{edge['game']}_{edge['team']}_{edge['arbitrage_profit']:.1f}"
    if edge_key in _notified_edges:
        return
    _notified_edges.add(edge_key)
    try:
        market_type = edge.get('market_type', 'Moneyline')
        sport = edge.get('sport', '')
        live_tag = " LIVE" if edge.get('is_live') else " PRE-GAME"
        mode = edge.get('fair_value_mode', 'pregame/fd+pin')
        ticker = edge.get('kalshi_ticker', '')
        side = edge.get('kalshi_side', 'yes').upper()
        price = edge.get('kalshi_price', 0)

        # Format odds freshness
        odds_age_str = ""
        last_update_str = edge.get('odds_last_update', '')
        if last_update_str:
            try:
                lu = datetime.fromisoformat(last_update_str.replace('Z', '+00:00'))
                age_sec = (datetime.now(timezone.utc) - lu).total_seconds()
                if age_sec < 60:
                    odds_age_str = f"\nOdds age: {int(age_sec)}s ago"
                elif age_sec < 3600:
                    odds_age_str = f"\nOdds age: {int(age_sec/60)}m ago"
                else:
                    odds_age_str = f"\nOdds age: {int(age_sec/3600)}h {int((age_sec%3600)/60)}m ago"
            except Exception:
                pass

        # Per-book lines in American odds
        per_book = edge.get('per_book_detail', {})
        kalshi_method = edge.get('kalshi_method', '')
        kalshi_fees_prob = edge['kalshi_prob_after_fees'] / 100.0
        is_live_prop = (market_type == 'Live Prop')

        if is_live_prop:
            # Live prop: direct one-way comparison, no devigging
            fd_implied = edge['fanduel_opposite_prob'] / 100.0
            message = f"""+EV OPPORTUNITY ({sport} - {market_type})

{edge['game']}

FanDuel Live Over: {prob_to_american(fd_implied)} ({fd_implied*100:.1f}%)
Kalshi YES: {kalshi_method} @ ${price:.2f}
Kalshi after fees: {prob_to_american(kalshi_fees_prob)} ({kalshi_fees_prob*100:.1f}%)
Difference: {edge['arbitrage_profit']:.2f}%{odds_age_str}

Would bet: {side} {ticker} @ {int(price*100)}c

https://kalshi-edge-finder.onrender.com"""
        else:
            # Devigged fair value comparison
            book_lines = ""
            if per_book:
                for book, prob in sorted(per_book.items()):
                    book_lines += f"\n  {book}: {prob_to_american(prob)}"
            else:
                consensus_prob = edge['fanduel_opposite_prob'] / 100.0
                book_lines = f"\n  Consensus: {prob_to_american(consensus_prob)}"

            consensus_opp_prob = edge['fanduel_opposite_prob'] / 100.0

            message = f"""+EV OPPORTUNITY ({sport} - {market_type}{live_tag})

{edge['game']}

Devigged Fair Lines ({mode}):
  Consensus fair (opposite): {prob_to_american(consensus_opp_prob)}{book_lines}

Kalshi: {kalshi_method} @ ${price:.2f}
Kalshi after fees: {prob_to_american(kalshi_fees_prob)}
Edge: {edge['arbitrage_profit']:.2f}%{odds_age_str}

Would bet: {side} {ticker} @ {int(price*100)}c

https://kalshi-edge-finder.onrender.com"""
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': message}, timeout=10)
    except Exception as e:
        print(f"   Telegram failed: {e}")


def send_order_telegram(order_info: Dict, status: str):
    """Send Telegram notification for order events (PLACED, FILLED, FAILED)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        side = order_info.get('side', '?').upper()
        ticker = order_info.get('ticker', '?')
        contracts = order_info.get('contracts', 0)
        price = order_info.get('price', 0)
        cost = order_info.get('cost', 0)
        potential = order_info.get('potential_profit', 0)
        edge = order_info.get('edge_pct', 0)
        game = order_info.get('game', '?')
        team = order_info.get('team', '?')
        sport = order_info.get('sport', '?')
        mtype = order_info.get('market_type', '?')
        order_status = order_info.get('status', '?')

        emoji = "✅" if status == "PLACED" else "🔴" if status == "FAILED" else "📋"
        message = f"""{emoji} ORDER {status} ({sport} - {mtype})

{game}
{side} {contracts}x {ticker} @ ${price:.2f}

Cost: ${cost:.2f}
Potential profit: ${potential:.2f}
Edge: {edge:.2f}%
Order status: {order_status}

https://kalshi-edge-finder.onrender.com/orders"""
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': message}, timeout=10)
    except Exception as e:
        print(f"   Telegram order notification failed: {e}")


def auto_trade_edge(edge: Dict, kalshi_api) -> Optional[Dict]:
    """Fair value edge auto-trading — DISABLED.
    Only completed props should auto-trade (via auto_trade_completed_prop).
    This function is still called by edge finders but always returns None."""
    return None


def prob_to_american(prob: float) -> str:
    """Convert implied probability to American odds string."""
    if prob <= 0 or prob >= 1:
        return "N/A"
    if prob >= 0.5:
        return f"-{int(round((prob / (1 - prob)) * 100))}"
    else:
        return f"+{int(round(((1 - prob) / prob) * 100))}"


class OddsConverter:
    @staticmethod
    def decimal_to_implied_prob(odds: float) -> float:
        return 1 / odds


def devig_two_way(prob_a: float, prob_b: float) -> tuple:
    """Multiplicative devigging for a 2-way market.
    Takes raw implied probs (which sum > 1.0 due to vig) and returns fair probs that sum to 1.0.
    Example: implied 0.54 + 0.52 = 1.06 → fair 0.509 + 0.491 = 1.0"""
    total = prob_a + prob_b
    if total <= 0:
        return (0.5, 0.5)
    return (prob_a / total, prob_b / total)


def devig_three_way(prob_a: float, prob_b: float, prob_c: float) -> tuple:
    """Multiplicative devigging for a 3-way market (e.g., soccer home/draw/away)."""
    total = prob_a + prob_b + prob_c
    if total <= 0:
        return (1/3, 1/3, 1/3)
    return (prob_a / total, prob_b / total, prob_c / total)


def consensus_fair_prob(book_probs: list) -> float:
    """Average devigged probabilities across multiple books to get consensus fair line.
    book_probs: list of fair probabilities from different books.
    Returns the mean."""
    if not book_probs:
        return 0.5
    return sum(book_probs) / len(book_probs)


class FanDuelAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.the-odds-api.com/v4"
        self._active_sports_cache = None
        self._active_sports_ts = None

    def get_active_sports(self) -> set:
        """Get currently active sport keys from The Odds API. Cached for 30 min."""
        now = time.time()
        if self._active_sports_cache and self._active_sports_ts and (now - self._active_sports_ts) < 1800:
            return self._active_sports_cache
        try:
            resp = requests.get(f"{self.base_url}/sports",
                               params={'apiKey': self.api_key}, timeout=10)
            resp.raise_for_status()
            active = {s['key'] for s in resp.json() if s.get('active')}
            self._active_sports_cache = active
            self._active_sports_ts = now
            return active
        except Exception as e:
            print(f"   Error fetching active sports: {e}")
            return self._active_sports_cache or set()

    def _fetch(self, sport_key: str, markets: str = 'h2h', bookmakers: str = None) -> list:
        """Fetch odds for today and tomorrow from multiple books.
        If bookmakers is None, pulls from all FAIR_VALUE_BOOKS."""
        try:
            now_utc = datetime.now(timezone.utc)
            start_of_today = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_window = start_of_today + timedelta(days=2)  # Today + tomorrow

            if bookmakers is None:
                bookmakers = ','.join(FAIR_VALUE_BOOKS)

            url = f"{self.base_url}/sports/{sport_key}/odds/"
            params = {
                'apiKey': self.api_key,
                'regions': 'us,us2',
                'markets': markets,
                'bookmakers': bookmakers,
                'oddsFormat': 'decimal',
                'commenceTimeFrom': start_of_today.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'commenceTimeTo': end_of_window.strftime('%Y-%m-%dT%H:%M:%SZ')
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 'unknown'
            print(f"   OddsAPI {sport_key}/{markets}: HTTP {status}")
            return []
        except Exception as e:
            print(f"   OddsAPI {sport_key}/{markets} error: {e}")
            return []

    def get_moneyline(self, sport_key: str) -> Dict:
        """Get h2h moneyline fair probabilities.
        Pre-game: FanDuel + Pinnacle combined devig.
        Live: Pinnacle only devig."""
        data = self._fetch(sport_key, 'h2h')
        games_dict = {}
        # {game_id: [{'book': key, 'outcomes': {name: price}, 'last_update': str}]}
        game_book_snapshots = {}

        for game in data:
            game_id = game.get('id', '')
            home = game.get('home_team', '')
            away = game.get('away_team', '')
            if home and away:
                games_dict[game_id] = {'home': home, 'away': away, 'commence_time': game.get('commence_time', '')}
            if game_id not in game_book_snapshots:
                game_book_snapshots[game_id] = []
            for bm in game.get('bookmakers', []):
                book_key = bm['key']
                bm_last_update = bm.get('last_update', '')
                for mkt in bm.get('markets', []):
                    if mkt['key'] == 'h2h':
                        mkt_last_update = mkt.get('last_update', '') or bm_last_update
                        book_outcomes = {}
                        for o in mkt.get('outcomes', []):
                            book_outcomes[o['name']] = o['price']
                        if len(book_outcomes) >= 2:
                            game_book_snapshots[game_id].append({
                                'book': book_key,
                                'outcomes': book_outcomes,
                                'last_update': mkt_last_update,
                            })

        odds_dict = {}
        pregame_count = 0
        live_count = 0
        for game_id, all_snaps in game_book_snapshots.items():
            commence = games_dict.get(game_id, {}).get('commence_time', '')
            game_live = is_game_live(commence)

            if game_live:
                # Live: use Pinnacle only
                pin_snaps = [s for s in all_snaps if s['book'] == LIVE_BOOK]
                if not pin_snaps:
                    continue
                # Check Pinnacle freshness — skip if odds older than 15 min
                pin_update = pin_snaps[0]['last_update']
                if are_odds_stale(commence, pin_update):
                    continue
                snaps_to_use = pin_snaps
                label = 'live/pinnacle'
            else:
                # Pre-game: require both FanDuel AND Pinnacle
                pregame_snaps = [s for s in all_snaps if s['book'] in PREGAME_BOOKS]
                books_present = {s['book'] for s in pregame_snaps}
                if not all(b in books_present for b in PREGAME_BOOKS):
                    continue
                snaps_to_use = pregame_snaps
                label = 'pregame/fd+pin'

            outcome_names = list(snaps_to_use[0]['outcomes'].keys())
            if len(outcome_names) < 2:
                continue

            fair_probs_per_outcome = {name: [] for name in outcome_names}
            # Track per-book devigged probs for telegram detail
            per_book_fair = {name: {} for name in outcome_names}  # {outcome: {book_key: fair_prob}}
            for snap in snaps_to_use:
                outcomes = snap['outcomes']
                if not all(name in outcomes for name in outcome_names):
                    continue
                implied = {name: 1.0 / outcomes[name] for name in outcome_names}
                total_implied = sum(implied.values())
                if total_implied <= 0:
                    continue
                for name in outcome_names:
                    devigged = implied[name] / total_implied
                    fair_probs_per_outcome[name].append(devigged)
                    per_book_fair[name][snap['book']] = devigged

            if not all(len(v) > 0 for v in fair_probs_per_outcome.values()):
                continue

            best_update = max(s['last_update'] for s in snaps_to_use)

            all_valid = True
            game_odds = {}
            for name in outcome_names:
                fair_p = consensus_fair_prob(fair_probs_per_outcome[name])
                n_books = len(fair_probs_per_outcome[name])
                if fair_p <= 0.001:
                    all_valid = False
                    break
                game_odds[name] = {
                    'odds': 1.0 / fair_p,
                    'fair_prob': fair_p,
                    'num_books': n_books,
                    'game_id': game_id,
                    'last_update': best_update,
                    'mode': label,
                    'per_book': per_book_fair[name],  # {book_key: devigged_prob}
                }
            if all_valid:
                odds_dict[game_id] = game_odds
                if game_live:
                    live_count += 1
                else:
                    pregame_count += 1

        total_outcomes = sum(len(v) for v in odds_dict.values())
        print(f"   Fair value {sport_key} moneyline: {total_outcomes} outcomes ({pregame_count} pregame, {live_count} live)")
        return {'odds': odds_dict, 'games': games_dict}

    def get_spreads(self, sport_key: str) -> Dict:
        """Get spread lines with fair probabilities.
        Pre-game: FanDuel + Pinnacle combined. Live: Pinnacle only."""
        data = self._fetch(sport_key, 'spreads')
        spreads = {}
        games_dict = {}
        game_book_spreads = {}  # {game_id: [{'book': key, 'outcomes': {...}, 'last_update': str}]}

        for game in data:
            game_id = game.get('id', '')
            home = game.get('home_team', '')
            away = game.get('away_team', '')
            if home and away:
                games_dict[game_id] = {'home': home, 'away': away, 'commence_time': game.get('commence_time', '')}
            if game_id not in game_book_spreads:
                game_book_spreads[game_id] = []
            for bm in game.get('bookmakers', []):
                book_key = bm['key']
                bm_last_update = bm.get('last_update', '')
                for mkt in bm.get('markets', []):
                    if mkt['key'] == 'spreads':
                        mkt_last_update = mkt.get('last_update', '') or bm_last_update
                        book_snap = {}
                        for o in mkt.get('outcomes', []):
                            book_snap[o['name']] = {'point': o.get('point', 0), 'odds': o['price']}
                        if len(book_snap) >= 2:
                            game_book_spreads[game_id].append({
                                'book': book_key,
                                'outcomes': book_snap,
                                'last_update': mkt_last_update,
                            })

        for game_id, all_snaps in game_book_spreads.items():
            commence = games_dict.get(game_id, {}).get('commence_time', '')
            game_live = is_game_live(commence)

            if game_live:
                pin_snaps = [s for s in all_snaps if s['book'] == LIVE_BOOK]
                if not pin_snaps:
                    continue
                if are_odds_stale(commence, pin_snaps[0]['last_update']):
                    continue
                snaps_to_use = pin_snaps
            else:
                pregame_snaps = [s for s in all_snaps if s['book'] in PREGAME_BOOKS]
                books_present = {s['book'] for s in pregame_snaps}
                if not all(b in books_present for b in PREGAME_BOOKS):
                    continue
                snaps_to_use = pregame_snaps

            team_names = set()
            for s in snaps_to_use:
                team_names.update(s['outcomes'].keys())
            if len(team_names) < 2:
                continue
            team_list = sorted(team_names)

            label = 'live/pin' if game_live else 'pregame/fd+pin'
            fair_probs = {t: [] for t in team_list}
            per_book_fair = {t: {} for t in team_list}
            spread_points = {t: [] for t in team_list}
            for snap in snaps_to_use:
                outcomes = snap['outcomes']
                if not all(t in outcomes for t in team_list):
                    continue
                implied = {t: 1.0 / outcomes[t]['odds'] for t in team_list}
                total = sum(implied.values())
                if total <= 0:
                    continue
                for t in team_list:
                    devigged = implied[t] / total
                    fair_probs[t].append(devigged)
                    per_book_fair[t][snap['book']] = devigged
                    spread_points[t].append(outcomes[t]['point'])

            if not all(len(v) > 0 for v in fair_probs.values()):
                continue

            best_update = max(s['last_update'] for s in snaps_to_use)
            game_spreads = {'_last_update': best_update, '_mode': label}
            skip_game = False
            for t in team_list:
                fair_p = consensus_fair_prob(fair_probs[t])
                if fair_p <= 0.001:
                    skip_game = True
                    break
                pts = sorted(spread_points[t])
                median_point = pts[len(pts) // 2]
                game_spreads[t] = {
                    'point': median_point,
                    'odds': 1.0 / fair_p,
                    'fair_prob': fair_p,
                    'num_books': len(fair_probs[t]),
                    'per_book': per_book_fair[t],
                }
            if not skip_game and len(game_spreads) > 1:
                spreads[game_id] = game_spreads

        print(f"   Fair value {sport_key} spreads: {len(spreads)} games")
        return {'spreads': spreads, 'games': games_dict}

    def get_totals(self, sport_key: str) -> Dict:
        """Get over/under lines with fair probabilities.
        Pre-game: FanDuel + Pinnacle combined. Live: Pinnacle only."""
        data = self._fetch(sport_key, 'totals')
        totals = {}
        games_dict = {}
        game_book_totals = {}  # {game_id: [{'book': key, 'data': {...}, 'last_update': str}]}

        for game in data:
            game_id = game.get('id', '')
            home = game.get('home_team', '')
            away = game.get('away_team', '')
            if home and away:
                games_dict[game_id] = {'home': home, 'away': away, 'commence_time': game.get('commence_time', '')}
            if game_id not in game_book_totals:
                game_book_totals[game_id] = []
            for bm in game.get('bookmakers', []):
                book_key = bm['key']
                bm_last_update = bm.get('last_update', '')
                for mkt in bm.get('markets', []):
                    if mkt['key'] == 'totals':
                        mkt_last_update = mkt.get('last_update', '') or bm_last_update
                        book_total = {}
                        for o in mkt.get('outcomes', []):
                            if o['name'] == 'Over':
                                book_total['over_odds'] = o['price']
                                book_total['point'] = o.get('point', 0)
                            elif o['name'] == 'Under':
                                book_total['under_odds'] = o['price']
                        if 'over_odds' in book_total and 'under_odds' in book_total:
                            game_book_totals[game_id].append({
                                'book': book_key,
                                'data': book_total,
                                'last_update': mkt_last_update,
                            })

        for game_id, all_snaps in game_book_totals.items():
            commence = games_dict.get(game_id, {}).get('commence_time', '')
            game_live = is_game_live(commence)

            if game_live:
                pin_snaps = [s for s in all_snaps if s['book'] == LIVE_BOOK]
                if not pin_snaps:
                    continue
                if are_odds_stale(commence, pin_snaps[0]['last_update']):
                    continue
                snaps_to_use = pin_snaps
            else:
                pregame_snaps = [s for s in all_snaps if s['book'] in PREGAME_BOOKS]
                books_present = {s['book'] for s in pregame_snaps}
                if not all(b in books_present for b in PREGAME_BOOKS):
                    continue
                snaps_to_use = pregame_snaps

            # Use most common total line among selected books
            points = [s['data']['point'] for s in snaps_to_use]
            most_common_point = max(set(points), key=points.count)
            matching = [s for s in snaps_to_use if abs(s['data']['point'] - most_common_point) < 0.01]
            if not matching:
                matching = snaps_to_use

            label = 'live/pin' if game_live else 'pregame/fd+pin'
            over_fair_list = []
            under_fair_list = []
            per_book_over = {}
            per_book_under = {}
            for snap in matching:
                d = snap['data']
                over_imp = 1.0 / d['over_odds']
                under_imp = 1.0 / d['under_odds']
                fair_over, fair_under = devig_two_way(over_imp, under_imp)
                over_fair_list.append(fair_over)
                under_fair_list.append(fair_under)
                per_book_over[snap['book']] = fair_over
                per_book_under[snap['book']] = fair_under

            over_fair = consensus_fair_prob(over_fair_list)
            under_fair = consensus_fair_prob(under_fair_list)
            if over_fair <= 0.001 or under_fair <= 0.001:
                continue

            best_update = max(s['last_update'] for s in snaps_to_use)
            totals[game_id] = {
                'point': most_common_point,
                'over_odds': 1.0 / over_fair,
                'under_odds': 1.0 / under_fair,
                'over_fair_prob': over_fair,
                'under_fair_prob': under_fair,
                'num_books': len(matching),
                '_last_update': best_update,
                '_mode': label,
                'per_book_over': per_book_over,
                'per_book_under': per_book_under,
            }

        print(f"   Fair value {sport_key} totals: {len(totals)} games")
        return {'totals': totals, 'games': games_dict}

    def get_events(self, sport_key: str) -> list:
        """Get event IDs for today and tomorrow (used for per-event prop fetching)."""
        try:
            now_utc = datetime.now(timezone.utc)
            start_of_today = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_window = start_of_today + timedelta(days=2)

            url = f"{self.base_url}/sports/{sport_key}/events/"
            params = {
                'apiKey': self.api_key,
                'commenceTimeFrom': start_of_today.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'commenceTimeTo': end_of_window.strftime('%Y-%m-%dT%H:%M:%SZ')
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"   FanDuel {sport_key} events error: {e}")
            return []

    def get_btts(self, sport_key: str) -> Dict:
        """Get BTTS with fair probabilities.
        Pre-game: FanDuel + Pinnacle combined. Live: Pinnacle only."""
        btts = {}
        games_dict = {}

        events = self.get_events(sport_key)
        if not events:
            print(f"   OddsAPI {sport_key} btts: no events today")
            return {'btts': btts, 'games': games_dict}

        bookmakers_str = ','.join(FAIR_VALUE_BOOKS)
        print(f"   OddsAPI {sport_key}: {len(events)} events, fetching btts...")

        for event in events:
            event_id = event.get('id', '')
            home = event.get('home_team', '')
            away = event.get('away_team', '')
            commence = event.get('commence_time', '')
            if home and away:
                games_dict[event_id] = {'home': home, 'away': away, 'commence_time': commence}

            try:
                url = f"{self.base_url}/sports/{sport_key}/events/{event_id}/odds"
                params = {
                    'apiKey': self.api_key,
                    'regions': 'us,us2',
                    'markets': 'btts',
                    'bookmakers': bookmakers_str,
                    'oddsFormat': 'decimal',
                }
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()

                all_snaps = []
                for bm in data.get('bookmakers', []):
                    book_key = bm['key']
                    bm_last_update = bm.get('last_update', '')
                    for mkt in bm.get('markets', []):
                        if mkt['key'] == 'btts':
                            mkt_last_update = mkt.get('last_update', '') or bm_last_update
                            snap = {}
                            for o in mkt.get('outcomes', []):
                                if o['name'] == 'Yes':
                                    snap['yes_odds'] = o['price']
                                elif o['name'] == 'No':
                                    snap['no_odds'] = o['price']
                            if 'yes_odds' in snap and 'no_odds' in snap:
                                all_snaps.append({'book': book_key, 'data': snap, 'last_update': mkt_last_update})

                game_live = is_game_live(commence)
                if game_live:
                    pin_snaps = [s for s in all_snaps if s['book'] == LIVE_BOOK]
                    if not pin_snaps:
                        continue
                    if are_odds_stale(commence, pin_snaps[0]['last_update']):
                        continue
                    snaps_to_use = pin_snaps
                else:
                    pregame_snaps = [s for s in all_snaps if s['book'] in PREGAME_BOOKS]
                    books_present = {s['book'] for s in pregame_snaps}
                    if not all(b in books_present for b in PREGAME_BOOKS):
                        continue
                    snaps_to_use = pregame_snaps

                label = 'live/pin' if game_live else 'pregame/fd+pin'
                yes_fair_list = []
                no_fair_list = []
                per_book_yes = {}
                per_book_no = {}
                for snap in snaps_to_use:
                    d = snap['data']
                    yes_imp = 1.0 / d['yes_odds']
                    no_imp = 1.0 / d['no_odds']
                    fair_yes, fair_no = devig_two_way(yes_imp, no_imp)
                    yes_fair_list.append(fair_yes)
                    no_fair_list.append(fair_no)
                    per_book_yes[snap['book']] = fair_yes
                    per_book_no[snap['book']] = fair_no

                yes_fair = consensus_fair_prob(yes_fair_list)
                no_fair = consensus_fair_prob(no_fair_list)
                if yes_fair <= 0.001 or no_fair <= 0.001:
                    continue

                best_update = max(s['last_update'] for s in snaps_to_use)
                btts[event_id] = {
                    'yes_odds': 1.0 / yes_fair,
                    'no_odds': 1.0 / no_fair,
                    'num_books': len(snaps_to_use),
                    '_last_update': best_update,
                    '_mode': label,
                    'per_book_yes': per_book_yes,
                    'per_book_no': per_book_no,
                }
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else 'unknown'
                print(f"   OddsAPI {sport_key} event {event_id} btts: HTTP {status}")
            except Exception as e:
                print(f"   OddsAPI {sport_key} event {event_id} btts: {e}")

            time.sleep(0.5)

        print(f"   Fair value {sport_key} btts: {len(btts)} games")
        return {'btts': btts, 'games': games_dict}

    def get_player_props_pregame(self, sport_key: str, market_keys: list) -> Dict:
        """Get FanDuel one-way player prop lines for pre-game events.
        Returns raw FanDuel Over implied probabilities (no devigging, no Pinnacle).
        Fetches all market_keys in one API call per event (saves API quota).

        Returns:
        {
            'props': {
                event_id: [
                    {
                        'player': str,
                        'point': float,            # e.g. 9.5 for "10+ points"
                        'over_odds': float,         # FD decimal odds
                        'fd_implied': float,         # 1/over_odds (raw implied prob)
                        'american_odds': int,        # American odds for display
                        'last_update': str,
                        'market_key': str,
                    },
                    ...
                ],
            },
            'games': {event_id: {'home': str, 'away': str, 'commence_time': str}},
        }
        """
        props = {}
        games_dict = {}

        events = self.get_events(sport_key)
        if not events:
            print(f"   OddsAPI {sport_key} props: no events today")
            return {'props': props, 'games': games_dict}

        # Only pre-game events
        pregame_events = [e for e in events if not is_game_live(e.get('commence_time', ''))]
        live_count = len(events) - len(pregame_events)
        if not pregame_events:
            print(f"   OddsAPI {sport_key} props: no pre-game events ({len(events)} total, {live_count} live)")
            return {'props': props, 'games': games_dict}

        markets_str = ','.join(market_keys)
        print(f"   OddsAPI {sport_key}: {len(pregame_events)} pre-game events ({live_count} live skipped), fetching {markets_str}...")

        for event in pregame_events:
            event_id = event.get('id', '')
            home = event.get('home_team', '')
            away = event.get('away_team', '')
            commence = event.get('commence_time', '')
            if home and away:
                games_dict[event_id] = {'home': home, 'away': away, 'commence_time': commence}

            try:
                url = f"{self.base_url}/sports/{sport_key}/events/{event_id}/odds"
                params = {
                    'apiKey': self.api_key,
                    'regions': 'us,us2',
                    'markets': markets_str,
                    'bookmakers': 'fanduel',
                    'oddsFormat': 'decimal',
                }
                response = requests.get(url, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()

                event_props = []
                for bm in data.get('bookmakers', []):
                    if bm['key'] != 'fanduel':
                        continue
                    bm_last_update = bm.get('last_update', '')
                    for mkt in bm.get('markets', []):
                        mkt_key = mkt['key']
                        if mkt_key not in market_keys:
                            continue
                        mkt_last_update = mkt.get('last_update', '') or bm_last_update
                        for o in mkt.get('outcomes', []):
                            if o.get('name') != 'Over':
                                continue
                            player = o.get('description', '')
                            point = o.get('point')
                            if not player or point is None:
                                continue
                            decimal_odds = o['price']
                            fd_implied = 1.0 / decimal_odds
                            # Convert to American for display
                            if decimal_odds >= 2.0:
                                american = int(round((decimal_odds - 1) * 100))
                            else:
                                american = int(round(-100 / (decimal_odds - 1)))
                            event_props.append({
                                'player': player,
                                'point': point,
                                'over_odds': decimal_odds,
                                'fd_implied': fd_implied,
                                'american_odds': american,
                                'last_update': mkt_last_update,
                                'market_key': mkt_key,
                            })

                if event_props:
                    props[event_id] = event_props

            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else 'unknown'
                print(f"   OddsAPI {sport_key} event {event_id} props: HTTP {status}")
            except Exception as e:
                print(f"   OddsAPI {sport_key} event {event_id} props: {e}")

            time.sleep(0.5)

        total_props = sum(len(v) for v in props.values())
        print(f"   FD pregame props {sport_key}: {total_props} lines in {len(props)} games")
        return {'props': props, 'games': games_dict}

    def get_fd_live_props(self, sport_key: str, market_key: str) -> Dict:
        """Get FanDuel one-way (over) player prop lines for LIVE games only.
        Returns raw FD implied probabilities — no devigging."""
        props = {}
        games_dict = {}

        events = self.get_events(sport_key)
        if not events:
            print(f"   OddsAPI {sport_key} {market_key}: no events today")
            return {'props': props, 'games': games_dict}

        live_events = [e for e in events if is_game_live(e.get('commence_time', ''))]
        if not live_events:
            print(f"   OddsAPI {sport_key} {market_key}: no live events")
            return {'props': props, 'games': games_dict}

        print(f"   OddsAPI {sport_key}: {len(live_events)} live events, fetching FD {market_key}...")

        for event in live_events:
            event_id = event.get('id', '')
            home = event.get('home_team', '')
            away = event.get('away_team', '')
            commence = event.get('commence_time', '')
            if home and away:
                games_dict[event_id] = {'home': home, 'away': away, 'commence_time': commence}

            try:
                url = f"{self.base_url}/sports/{sport_key}/events/{event_id}/odds"
                params = {
                    'apiKey': self.api_key,
                    'regions': 'us,us2',
                    'markets': market_key,
                    'bookmakers': 'fanduel',
                    'oddsFormat': 'decimal',
                }
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()

                game_props = []
                for bm in data.get('bookmakers', []):
                    if bm['key'] != 'fanduel':
                        continue
                    bm_last_update = bm.get('last_update', '')
                    for mkt in bm.get('markets', []):
                        if mkt['key'] == market_key:
                            mkt_last_update = mkt.get('last_update', '') or bm_last_update
                            # Check staleness
                            if are_odds_stale(commence, mkt_last_update):
                                print(f"   FD {market_key} stale for {home} vs {away}, skipping")
                                continue
                            for o in mkt.get('outcomes', []):
                                if o.get('name') == 'Over':
                                    game_props.append({
                                        'player': o.get('description', ''),
                                        'point': o.get('point', 0),
                                        'over_odds': o['price'],
                                        'fd_over_implied': 1.0 / o['price'],
                                        'last_update': mkt_last_update,
                                    })
                if game_props:
                    props[event_id] = game_props
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else 'unknown'
                print(f"   OddsAPI {sport_key} event {event_id} {market_key}: HTTP {status}")
            except Exception as e:
                print(f"   OddsAPI {sport_key} event {event_id} {market_key}: {e}")

            time.sleep(0.5)

        total_props = sum(len(v) for v in props.values())
        print(f"   FD live {sport_key} {market_key}: {total_props} props in {len(props)} games")
        return {'props': props, 'games': games_dict}


class KalshiAPI:
    def __init__(self, api_key_id: str = None, private_key_str: str = None):
        self.BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
        self.api_key_id = api_key_id
        self.private_key = None
        self.session = requests.Session()
        self.session.headers.update({'Accept': 'application/json', 'Content-Type': 'application/json'})

        # Load RSA private key for signed requests
        if private_key_str:
            try:
                # Handle env var newline encoding
                key_str = private_key_str.replace('\\n', '\n')
                self.private_key = serialization.load_pem_private_key(
                    key_str.encode(), password=None
                )
                print("   Kalshi: RSA private key loaded successfully")
            except Exception as e:
                print(f"   Kalshi: Failed to load private key: {e}")

    def _sign_request(self, method: str, path: str) -> Dict[str, str]:
        """Generate RSA-PSS signed auth headers for Kalshi API."""
        timestamp_ms = str(int(time.time() * 1000))
        # Strip query params for signing
        path_only = path.split('?')[0]
        msg = timestamp_ms + method.upper() + path_only
        signature = self.private_key.sign(
            msg.encode('utf-8'),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )
        return {
            'KALSHI-ACCESS-KEY': self.api_key_id,
            'KALSHI-ACCESS-SIGNATURE': base64.b64encode(signature).decode('utf-8'),
            'KALSHI-ACCESS-TIMESTAMP': timestamp_ms,
        }

    def _auth_get(self, path: str, params: Dict = None) -> Optional[Dict]:
        """Authenticated GET request."""
        if not self.private_key:
            return None
        try:
            headers = self._sign_request('GET', path)
            response = requests.get(
                f"https://api.elections.kalshi.com{path}",
                headers={**self.session.headers, **headers},
                params=params, timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"   Kalshi auth GET {path} error: {e}")
            return None

    def _auth_post(self, path: str, body: Dict) -> Optional[Dict]:
        """Authenticated POST request."""
        if not self.private_key:
            return None
        try:
            headers = self._sign_request('POST', path)
            response = requests.post(
                f"https://api.elections.kalshi.com{path}",
                headers={**self.session.headers, **headers},
                json=body, timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 'unknown'
            body_text = e.response.text if e.response is not None else ''
            print(f"   Kalshi order error: HTTP {status} - {body_text}")
            return None
        except Exception as e:
            print(f"   Kalshi auth POST {path} error: {e}")
            return None

    def get_balance(self) -> Optional[Dict]:
        """Get account balance (in cents)."""
        return self._auth_get('/trade-api/v2/portfolio/balance')

    def get_orders(self, status: str = None) -> List[Dict]:
        """Get orders, optionally filtered by status (resting/executed/canceled)."""
        params = {}
        if status:
            params['status'] = status
        result = self._auth_get('/trade-api/v2/portfolio/orders', params=params)
        if result:
            return result.get('orders', [])
        return []

    def get_settlements(self, limit: int = 200) -> List[Dict]:
        """Get settlement history from Kalshi."""
        all_settlements = []
        cursor = None
        try:
            while True:
                params = {'limit': limit}
                if cursor:
                    params['cursor'] = cursor
                result = self._auth_get('/trade-api/v2/portfolio/settlements', params=params)
                if not result:
                    break
                settlements = result.get('settlements', [])
                all_settlements.extend(settlements)
                cursor = result.get('cursor')
                if not cursor:
                    break
            return all_settlements
        except Exception as e:
            print(f"   Kalshi get_settlements error: {e}")
            return all_settlements

    def get_positions(self, limit: int = 200) -> List[Dict]:
        """Get current portfolio positions from Kalshi."""
        all_positions = []
        cursor = None
        try:
            while True:
                params = {'limit': limit}
                if cursor:
                    params['cursor'] = cursor
                result = self._auth_get('/trade-api/v2/portfolio/positions', params=params)
                if not result:
                    break
                settlements = result.get('market_positions', [])
                all_positions.extend(settlements)
                cursor = result.get('cursor')
                if not cursor:
                    break
            return all_positions
        except Exception as e:
            print(f"   Kalshi get_positions error: {e}")
            return all_positions

    def place_order(self, ticker: str, side: str, price_cents: int, count: int,
                    client_order_id: str = None) -> Optional[Dict]:
        """Place a limit order on Kalshi.
        side: 'yes' or 'no'
        price_cents: price in cents (e.g., 52 for $0.52)
        count: number of contracts
        """
        body = {
            'action': 'buy',
            'type': 'limit',
            'side': side,
            'ticker': ticker,
            'count': count,
        }
        if side == 'yes':
            body['yes_price'] = price_cents
        else:
            body['no_price'] = price_cents

        if client_order_id:
            body['client_order_id'] = client_order_id

        print(f"   >>> PLACING ORDER: {side.upper()} {count}x {ticker} @ {price_cents}¢")
        result = self._auth_post('/trade-api/v2/portfolio/orders', body)
        if result:
            order = result.get('order', {})
            status = order.get('status', 'unknown')
            order_id = order.get('order_id', 'unknown')
            print(f"   >>> ORDER {order_id}: {status}")
            return result
        return None

    def get_markets(self, series_ticker: str, limit: int = 200, status: str = 'open') -> List[Dict]:
        all_markets = []
        cursor = None
        try:
            while True:
                params = {'limit': limit, 'status': status, 'series_ticker': series_ticker}
                if cursor:
                    params['cursor'] = cursor
                response = self.session.get(f"{self.BASE_URL}/markets", params=params, timeout=10)
                # Retry up to 3 times on 429 with exponential backoff
                for retry_delay in [5, 10, 20]:
                    if response.status_code != 429:
                        break
                    print(f"   Kalshi 429 on {series_ticker}, backing off {retry_delay}s...")
                    time.sleep(retry_delay)
                    response = self.session.get(f"{self.BASE_URL}/markets", params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                markets = data.get('markets', [])
                all_markets.extend(markets)
                cursor = data.get('cursor')
                if not cursor:
                    break
                time.sleep(1.5)
            print(f"   Kalshi {series_ticker}: {len(all_markets)} markets")
            return all_markets
        except Exception as e:
            print(f"   Kalshi {series_ticker} error: {e}")
            return all_markets

    def get_market(self, ticker: str) -> Optional[Dict]:
        """Get details for a single market by ticker."""
        try:
            response = self.session.get(f"{self.BASE_URL}/markets/{ticker}", timeout=10)
            if response.status_code == 429:
                time.sleep(2.0)
                response = self.session.get(f"{self.BASE_URL}/markets/{ticker}", timeout=10)
            response.raise_for_status()
            return response.json().get('market', response.json())
        except Exception as e:
            return None

    def get_orderbook(self, ticker: str) -> Optional[Dict]:
        try:
            response = self.session.get(f"{self.BASE_URL}/markets/{ticker}/orderbook", timeout=10)
            for retry_delay in [3, 8, 15]:
                if response.status_code != 429:
                    break
                print(f"   Kalshi 429 on {ticker} orderbook, backing off {retry_delay}s...")
                time.sleep(retry_delay)
                response = self.session.get(f"{self.BASE_URL}/markets/{ticker}/orderbook", timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return None


def get_best_yes_price(ob: Dict) -> Optional[float]:
    """Get best YES ask price (what you'd pay to buy YES instantly).
    In Kalshi's binary market: YES ask = 100 - best NO bid."""
    data = ob.get('orderbook', {})
    no_bids = data.get('no', [])
    if not no_bids:
        return None
    best_no_bid = max(no_bids, key=lambda x: x[0])[0]
    return (100 - best_no_bid) / 100


def get_best_no_price(ob: Dict) -> Optional[float]:
    """Get best NO ask price (what you'd pay to buy NO instantly).
    In Kalshi's binary market: NO ask = 100 - best YES bid."""
    data = ob.get('orderbook', {})
    yes_bids = data.get('yes', [])
    if not yes_bids:
        return None
    best_yes_bid = max(yes_bids, key=lambda x: x[0])[0]
    return (100 - best_yes_bid) / 100


# ============================================================
# MONEYLINE EDGE FINDER (existing logic, cleaned up)
# ============================================================

def find_moneyline_edges(kalshi_api, fd_data, series_ticker, sport_name, team_map):
    converter = OddsConverter()
    fanduel_odds = fd_data['odds']
    fanduel_games = fd_data['games']
    edges = []
    date_strs = _get_today_date_strs()

    kalshi_markets = kalshi_api.get_markets(series_ticker)
    today_markets = [m for m in kalshi_markets
                     if any(ds in m.get('ticker', '') for ds in date_strs)]
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
        # Soccer has 3-way markets (Home/Draw/Away), other sports have 2-way
        is_three_way = len(team_markets) == 3
        if len(team_markets) < 2 or len(team_markets) > 3:
            continue

        # Separate draw market from team markets for 3-way
        draw_abbrev = None
        team_abbrevs_list = []
        for a in team_markets:
            if a.upper() in ('DRAW', 'DRW', 'TIE'):
                draw_abbrev = a
            else:
                team_abbrevs_list.append(a)

        if is_three_way and not draw_abbrev:
            continue  # 3 entries but no draw — unexpected format
        if len(team_abbrevs_list) != 2:
            continue

        t1_name = team_map.get(team_abbrevs_list[0], team_abbrevs_list[0])
        t2_name = team_map.get(team_abbrevs_list[1], team_abbrevs_list[1])

        fd_t1, fd_t2, matched_gid = match_kalshi_to_fanduel_game(t1_name, t2_name, fanduel_games)
        if not fd_t1 or not matched_gid or matched_gid not in fanduel_odds:
            continue
        game_odds = fanduel_odds[matched_gid]  # {outcome_name: {odds, fair_prob, ...}}
        if fd_t1 not in game_odds or fd_t2 not in game_odds:
            continue
        commence_str = fanduel_games.get(matched_gid, {}).get('commence_time', '')
        game_live = is_game_live(commence_str)

        # Skip live games — The Odds API live data is unreliable (timestamps fresh but odds stale)
        if game_live:
            continue

        # Fetch orderbooks for team markets
        ob1 = kalshi_api.get_orderbook(team_markets[team_abbrevs_list[0]]['ticker'])
        time.sleep(0.3)
        ob2 = kalshi_api.get_orderbook(team_markets[team_abbrevs_list[1]]['ticker'])
        time.sleep(0.3)
        if not ob1 or not ob2:
            continue

        t1_yes = get_best_yes_price(ob1)
        t1_no = get_best_no_price(ob1)
        t2_yes = get_best_yes_price(ob2)
        t2_no = get_best_no_price(ob2)
        if None in [t1_yes, t1_no, t2_yes, t2_no]:
            continue

        # Build entries with ticker and side info for auto-trading
        entries = []

        # For 3-way soccer: each Kalshi outcome's "opposite" is the sum of the other
        # two FD outcomes' implied probabilities. For 2-way: standard opposite.
        if is_three_way and 'Draw' in game_odds:
            fd_draw_prob = converter.decimal_to_implied_prob(game_odds['Draw']['odds'])
            fd_t1_prob = converter.decimal_to_implied_prob(game_odds[fd_t1]['odds'])
            fd_t2_prob = converter.decimal_to_implied_prob(game_odds[fd_t2]['odds'])

            # Fetch draw orderbook
            ob_draw = kalshi_api.get_orderbook(team_markets[draw_abbrev]['ticker'])
            time.sleep(0.3)
            draw_yes = get_best_yes_price(ob_draw) if ob_draw else None
            draw_no = get_best_no_price(ob_draw) if ob_draw else None

            # Team 1 YES: opposite is P(team2 wins) + P(draw)
            opp_prob_t1 = fd_t2_prob + fd_draw_prob
            fee_t1 = kalshi_fee(t1_yes)
            eff_t1 = t1_yes + fee_t1
            if eff_t1 + opp_prob_t1 < 1.0:
                profit = (1.0 / (eff_t1 + opp_prob_t1) - 1) * 100
                entries.append({
                    'name': t1_name, 'price': t1_yes, 'eff': eff_t1,
                    'method': f"YES on {t1_name}", 'fd_opp_name': f"{fd_t2} + Draw",
                    'fd_opp_prob': opp_prob_t1, 'fd_opp_odds': game_odds[fd_t2]['odds'],
                    'ticker': team_markets[team_abbrevs_list[0]]['ticker'], 'side': 'yes',
                    'profit': profit,
                })

            # Team 2 YES: opposite is P(team1 wins) + P(draw)
            opp_prob_t2 = fd_t1_prob + fd_draw_prob
            fee_t2 = kalshi_fee(t2_yes)
            eff_t2 = t2_yes + fee_t2
            if eff_t2 + opp_prob_t2 < 1.0:
                profit = (1.0 / (eff_t2 + opp_prob_t2) - 1) * 100
                entries.append({
                    'name': t2_name, 'price': t2_yes, 'eff': eff_t2,
                    'method': f"YES on {t2_name}", 'fd_opp_name': f"{fd_t1} + Draw",
                    'fd_opp_prob': opp_prob_t2, 'fd_opp_odds': game_odds[fd_t1]['odds'],
                    'ticker': team_markets[team_abbrevs_list[1]]['ticker'], 'side': 'yes',
                    'profit': profit,
                })

            # Draw YES: opposite is P(team1) + P(team2)
            if draw_yes is not None:
                opp_prob_draw = fd_t1_prob + fd_t2_prob
                fee_draw = kalshi_fee(draw_yes)
                eff_draw = draw_yes + fee_draw
                if eff_draw + opp_prob_draw < 1.0:
                    profit = (1.0 / (eff_draw + opp_prob_draw) - 1) * 100
                    entries.append({
                        'name': 'Draw', 'price': draw_yes, 'eff': eff_draw,
                        'method': f"YES on Draw", 'fd_opp_name': f"{fd_t1} + {fd_t2}",
                        'fd_opp_prob': opp_prob_draw, 'fd_opp_odds': game_odds[fd_t1]['odds'],
                        'ticker': team_markets[draw_abbrev]['ticker'], 'side': 'yes',
                        'profit': profit,
                    })

            # Build per-book opposite probs for 3-way outcomes
            # For "YES on Team1", opposite = P(Team2) + P(Draw) per book
            three_way_per_book = {}
            for e_name, opp_outcomes in [(t1_name, [fd_t2, 'Draw']), (t2_name, [fd_t1, 'Draw']), ('Draw', [fd_t1, fd_t2])]:
                book_opp = {}
                all_books_set = set()
                for oname in opp_outcomes:
                    odata = game_odds.get(oname, {})
                    for bk, bp in odata.get('per_book', {}).items():
                        all_books_set.add(bk)
                for bk in all_books_set:
                    total = 0
                    have_all = True
                    for oname in opp_outcomes:
                        bp = game_odds.get(oname, {}).get('per_book', {}).get(bk)
                        if bp is None:
                            have_all = False
                            break
                        total += bp
                    if have_all:
                        book_opp[bk] = total
                three_way_per_book[e_name] = book_opp

            # Build edge dicts from 3-way entries
            game_edges = []
            for e in entries:
                if e['profit'] < MIN_EDGE_PERCENT:
                    continue
                edge = {
                    'market_type': 'Moneyline',
                    'sport': sport_name,
                    'game': f"{fd_t1} vs {fd_t2}",
                    'team': e['name'],
                    'opposite_team': e['fd_opp_name'],
                    'kalshi_price': e['price'],
                    'kalshi_price_after_fees': e['eff'],
                    'kalshi_prob_after_fees': e['eff'] * 100,
                    'kalshi_method': e['method'],
                    'kalshi_ticker': e['ticker'],
                    'kalshi_side': e['side'],
                    'fanduel_opposite_team': e['fd_opp_name'],
                    'fanduel_opposite_odds': e['fd_opp_odds'],
                    'fanduel_opposite_prob': e['fd_opp_prob'] * 100,
                    'total_implied_prob': (e['eff'] + e['fd_opp_prob']) * 100,
                    'arbitrage_profit': e['profit'],
                    'is_live': game_live,
                    'fair_value_mode': game_odds.get(fd_t1, {}).get('mode', ''),
                    'per_book_detail': three_way_per_book.get(e['name'], {}),
                    'odds_last_update': game_odds.get(fd_t1, {}).get('last_update', ''),
                    'recommendation': f"Buy {e['method']} on Kalshi at ${e['price']:.2f} (Fair value: {e['fd_opp_prob']*100:.1f}%)",
                }
                if books_diverge(edge['per_book_detail']):
                    print(f"   Skipping {edge['game']} 3-way ML: books diverge >10pp")
                    continue
                game_edges.append(edge)

            if game_edges:
                game_edges.sort(key=lambda e: e['arbitrage_profit'], reverse=True)
                best_edge = game_edges[0]
                edges.append(best_edge)
                send_telegram_notification(best_edge)
                auto_trade_edge(best_edge, kalshi_api)
        else:
            # Standard 2-way moneyline (NBA, NHL, etc.)
            if t1_yes <= t2_no:
                entries.append((t1_name, t1_yes, f"YES on {t1_name}", fd_t2,
                               team_markets[team_abbrevs_list[0]]['ticker'], 'yes'))
            else:
                entries.append((t1_name, t2_no, f"NO on {t2_name}", fd_t2,
                               team_markets[team_abbrevs_list[1]]['ticker'], 'no'))
            if t2_yes <= t1_no:
                entries.append((t2_name, t2_yes, f"YES on {t2_name}", fd_t1,
                               team_markets[team_abbrevs_list[1]]['ticker'], 'yes'))
            else:
                entries.append((t2_name, t1_no, f"NO on {t1_name}", fd_t1,
                               team_markets[team_abbrevs_list[0]]['ticker'], 'no'))

            # Evaluate both entries, pick only the best edge per game
            game_edges = []
            for name, best_p, method, fd_opp, trade_ticker, trade_side in entries:
                fee = kalshi_fee(best_p)
                eff = best_p + fee
                fd_prob = converter.decimal_to_implied_prob(game_odds[fd_opp]['odds'])
                total = eff + fd_prob
                if total < 1.0:
                    profit = (1.0 / total - 1) * 100
                    if profit < MIN_EDGE_PERCENT:
                        continue
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
                        'kalshi_ticker': trade_ticker,
                        'kalshi_side': trade_side,
                        'fanduel_opposite_team': fd_opp,
                        'fanduel_opposite_odds': game_odds[fd_opp]['odds'],
                        'fanduel_opposite_prob': fd_prob * 100,
                        'total_implied_prob': total * 100,
                        'arbitrage_profit': profit,
                        'is_live': game_live,
                        'fair_value_mode': game_odds.get(fd_opp, {}).get('mode', ''),
                        'per_book_detail': game_odds.get(fd_opp, {}).get('per_book', {}),
                        'odds_last_update': game_odds.get(fd_opp, {}).get('last_update', ''),
                        'recommendation': f"Buy {method} on Kalshi at ${best_p:.2f} (Fair value: {fd_opp} at {game_odds[fd_opp]['odds']:.2f})",
                    }
                    if books_diverge(edge['per_book_detail']):
                        print(f"   Skipping {edge['game']} 2-way ML: books diverge >10pp")
                        continue
                    game_edges.append(edge)

            # Only trade the best edge per game (don't bet both sides)
            if game_edges:
                game_edges.sort(key=lambda e: e['arbitrage_profit'], reverse=True)
                best_edge = game_edges[0]
                edges.append(best_edge)
                send_telegram_notification(best_edge)
                auto_trade_edge(best_edge, kalshi_api)
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
    date_strs = _get_today_date_strs()

    kalshi_markets = kalshi_api.get_markets(series_ticker)
    today_markets = [m for m in kalshi_markets
                     if any(ds in m.get('ticker', '') for ds in date_strs)]
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
        commence_str = fd_games.get(matched_game_id, {}).get('commence_time', '')
        game_live = is_game_live(commence_str)

        # Skip live games — The Odds API live data is unreliable
        if game_live:
            continue

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
            fd_point = fd_spread['point']  # SIGNED: negative = favorite, positive = underdog
            fd_odds = fd_spread['odds']

            # Kalshi spread markets are "Team wins by X+" which means the team is FAVORED.
            # FanDuel returns negative points for favorites (e.g., -1.5) and positive for underdogs (+1.5).
            # Only match if FanDuel spread is negative (team is favorite), matching Kalshi's "wins by X+".
            if fd_point >= 0:
                # FanDuel says this team is underdog (getting points), skip - not comparable to Kalshi "wins by X+"
                continue

            # Compare absolute values: Kalshi floor_strike (always positive) vs FanDuel |spread|
            if abs(floor_strike - abs(fd_point)) > 0.5:
                continue

            # Find the OPPOSITE team's spread to get fair value
            # FD includes vig on both sides, so we use opposite side to derive true probability
            fd_opposite_name = fd_t2 if fd_team_name == fd_t1 else fd_t1
            if fd_opposite_name not in fd_game_spreads:
                continue
            fd_opposite_spread = fd_game_spreads[fd_opposite_name]
            fd_opposite_odds = fd_opposite_spread['odds']
            fd_opposite_prob = converter.decimal_to_implied_prob(fd_opposite_odds)
            # Fair prob for our side = 1 - opposite implied prob (strips vig from our side)
            fd_fair_prob = 1.0 - fd_opposite_prob

            # Get Kalshi orderbook
            ob = kalshi_api.get_orderbook(ticker)
            if not ob:
                continue
            time.sleep(0.3)

            yes_price = get_best_yes_price(ob)
            if yes_price is None:
                continue

            fee = kalshi_fee(yes_price)
            eff = yes_price + fee

            # +EV if Kalshi price after fees < FanDuel fair value for this side
            # Using opposite side: total_implied = kalshi_eff + fd_opposite_prob
            # If < 1.0, there's an edge
            total_implied = eff + fd_opposite_prob
            if total_implied < 1.0:
                profit = (1.0 / total_implied - 1) * 100
                if profit < MIN_EDGE_PERCENT:
                    continue
                game_name = f"{fd_games[matched_game_id]['away']} at {fd_games[matched_game_id]['home']}"
                edge = {
                    'market_type': 'Spread',
                    'sport': sport_name,
                    'game': game_name,
                    'team': f"{team_name} -{floor_strike}",
                    'opposite_team': fd_opposite_name,
                    'kalshi_price': yes_price,
                    'kalshi_price_after_fees': eff,
                    'kalshi_prob_after_fees': eff * 100,
                    'kalshi_method': f"YES on {team_name} -{floor_strike}",
                    'kalshi_ticker': ticker,
                    'kalshi_side': 'yes',
                    'fanduel_opposite_team': f"{fd_opposite_name} {fd_opposite_spread['point']}",
                    'fanduel_opposite_odds': fd_opposite_odds,
                    'fanduel_opposite_prob': fd_opposite_prob * 100,
                    'total_implied_prob': total_implied * 100,
                    'arbitrage_profit': profit,
                    'is_live': game_live,
                    'fair_value_mode': fd_game_spreads.get('_mode', ''),
                    'per_book_detail': fd_opposite_spread.get('per_book', {}),
                    'odds_last_update': fd_game_spreads.get('_last_update', ''),
                    'recommendation': f"Buy YES {team_name} -{floor_strike} on Kalshi at ${yes_price:.2f} (Fair value: {fd_opposite_name} {fd_opposite_spread['point']} at {fd_opposite_odds:.2f})",
                }
                if books_diverge(edge['per_book_detail']):
                    print(f"   Skipping {edge['game']} spread: books diverge >10pp")
                    continue
                edges.append(edge)
                send_telegram_notification(edge)
                auto_trade_edge(edge, kalshi_api)

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
    date_strs = _get_today_date_strs()

    kalshi_markets = kalshi_api.get_markets(series_ticker)
    today_markets = [m for m in kalshi_markets
                     if any(ds in m.get('ticker', '') for ds in date_strs)]
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
        commence_str = fd_games.get(matched_game_id, {}).get('commence_time', '')
        game_live = is_game_live(commence_str)

        # Skip live games — The Odds API live data is unreliable
        if game_live:
            continue

        # Step 3: For each total market in this game, compare to fair value
        for mk in group['markets']:
            floor_strike = mk['floor_strike']
            ticker = mk['ticker']

            # Only compare EXACT matching lines (within 0.5 points)
            if abs(floor_strike - fd_line) > 0.5:
                continue

            ob = kalshi_api.get_orderbook(ticker)
            if not ob:
                continue
            time.sleep(0.3)

            yes_price = get_best_yes_price(ob)  # YES = Over
            no_price = get_best_no_price(ob)    # NO = Under

            # Use OPPOSITE side FanDuel odds to derive fair value (strips vig from our side)
            # For Over: fair value = 1 - FD_Under_implied_prob
            # For Under: fair value = 1 - FD_Over_implied_prob
            fd_over_prob = converter.decimal_to_implied_prob(fd_total['over_odds'])
            fd_under_prob = converter.decimal_to_implied_prob(fd_total['under_odds'])

            # Check Over: Kalshi YES price vs FanDuel Under (opposite side)
            if yes_price is not None:
                fee = kalshi_fee(yes_price)
                eff = yes_price + fee
                # total_implied = kalshi_over_eff + fd_under_prob; if < 1.0 -> edge
                total_implied = eff + fd_under_prob
                if total_implied < 1.0:
                    profit = (1.0 / total_implied - 1) * 100
                    if profit < MIN_EDGE_PERCENT:
                        continue
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
                        'kalshi_ticker': ticker,
                        'kalshi_side': 'yes',
                        'fanduel_opposite_team': f"Under {fd_line}",
                        'fanduel_opposite_odds': fd_total['under_odds'],
                        'fanduel_opposite_prob': fd_under_prob * 100,
                        'total_implied_prob': total_implied * 100,
                        'arbitrage_profit': profit,
                        'is_live': game_live,
                        'fair_value_mode': fd_total.get('_mode', ''),
                        'per_book_detail': fd_total.get('per_book_under', {}),
                        'odds_last_update': fd_total.get('_last_update', ''),
                        'recommendation': f"Buy YES Over {floor_strike} on Kalshi at ${yes_price:.2f} (FanDuel Under {fd_line} at {fd_total['under_odds']:.2f})",
                    }
                    if books_diverge(edge['per_book_detail']):
                        print(f"   Skipping {edge['game']} Over total: books diverge >10pp")
                        continue
                    edges.append(edge)
                    send_telegram_notification(edge)
                    auto_trade_edge(edge, kalshi_api)

            # Check Under: Kalshi NO price vs FanDuel Over (opposite side)
            if no_price is not None:
                under_cost = no_price
                fee = kalshi_fee(under_cost)
                eff = under_cost + fee
                # total_implied = kalshi_under_eff + fd_over_prob; if < 1.0 -> edge
                total_implied = eff + fd_over_prob
                if total_implied < 1.0:
                    profit = (1.0 / total_implied - 1) * 100
                    if profit < MIN_EDGE_PERCENT:
                        continue
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
                        'kalshi_ticker': ticker,
                        'kalshi_side': 'no',
                        'fanduel_opposite_team': f"Over {fd_line}",
                        'fanduel_opposite_odds': fd_total['over_odds'],
                        'fanduel_opposite_prob': fd_over_prob * 100,
                        'total_implied_prob': total_implied * 100,
                        'arbitrage_profit': profit,
                        'is_live': game_live,
                        'fair_value_mode': fd_total.get('_mode', ''),
                        'per_book_detail': fd_total.get('per_book_over', {}),
                        'odds_last_update': fd_total.get('_last_update', ''),
                        'recommendation': f"Buy NO (Under {floor_strike}) on Kalshi at ${under_cost:.2f} (FanDuel Over {fd_line} at {fd_total['over_odds']:.2f})",
                    }
                    if books_diverge(edge['per_book_detail']):
                        print(f"   Skipping {edge['game']} Under total: books diverge >10pp")
                        continue
                    edges.append(edge)
                    send_telegram_notification(edge)
                    auto_trade_edge(edge, kalshi_api)

    return edges


# ============================================================
# LIVE PLAYER PROP VALUE — compare FD one-way over vs Kalshi one-way YES
# ============================================================

def find_live_prop_value(kalshi_api, fd_data, series_ticker, sport_name, fd_market_key):
    """
    Compare FanDuel live one-way Over price to Kalshi YES price.
    No devigging — just direct comparison of what each platform charges
    for the same bet. If Kalshi is cheaper, that's value.

    Edge = (fd_over_implied - kalshi_eff) as percentage points.
    """
    fd_props = fd_data['props']
    fd_games = fd_data['games']
    edges = []
    date_strs = _get_today_date_strs()

    kalshi_markets = kalshi_api.get_markets(series_ticker)
    today_markets = [m for m in kalshi_markets
                     if any(ds in m.get('ticker', '') for ds in date_strs)]
    if not today_markets:
        return edges

    # Build FD lookup: {player_name_lower: [{point, over_odds, fd_over_implied, game_id}]}
    fd_lookup = {}
    for game_id, props in fd_props.items():
        for prop in props:
            player = prop['player'].lower().strip()
            if player not in fd_lookup:
                fd_lookup[player] = []
            fd_lookup[player].append({
                'point': prop['point'],
                'over_odds': prop['over_odds'],
                'fd_over_implied': prop['fd_over_implied'],
                'game_id': game_id,
                'last_update': prop.get('last_update', ''),
            })

    # Build team abbrev -> set of FD game_ids for game verification
    prop_team_map = {}
    if 'NBA' in series_ticker:
        prop_team_map = NBA_TEAMS
    elif 'NHL' in series_ticker:
        prop_team_map = NHL_TEAMS
    fd_game_team_abbrs = {}
    for game_id, ginfo in fd_games.items():
        fd_game_team_abbrs[game_id] = set()
        for abbr, full_name in prop_team_map.items():
            if _name_matches(full_name, ginfo.get('home', '')) or _name_matches(full_name, ginfo.get('away', '')):
                fd_game_team_abbrs[game_id].add(abbr)

    for m in today_markets:
        ticker = m.get('ticker', '')
        title = m.get('title', '')
        subtitle = m.get('subtitle', '')

        # Extract game teams from ticker
        ticker_game_abbrs = set()
        ticker_parts = ticker.split('-')
        if len(ticker_parts) >= 2:
            game_part = ticker_parts[1]
            date_stripped = re.sub(r'^\d{2}[A-Z]{3}\d{2}', '', game_part)
            if prop_team_map:
                team_abbr_set = set(prop_team_map.keys())
                for i in range(1, len(date_stripped)):
                    t1, t2 = date_stripped[:i], date_stripped[i:]
                    if t1 in team_abbr_set and t2 in team_abbr_set:
                        ticker_game_abbrs = {t1, t2}
                        break

        # Extract player name and line: "Nikola Jokic: 25+ points"
        prop_match = re.match(r'^(.+?):\s*(\d+\.?\d*)\+', title or subtitle or '')
        if not prop_match:
            continue

        player_name = prop_match.group(1).strip()
        kalshi_line = float(prop_match.group(2))

        # Find matching FD prop
        best_fd_match = None
        best_fd_score = 0

        for fd_player, fd_entries in fd_lookup.items():
            if _match_player_name(player_name, fd_player):
                for entry in fd_entries:
                    if ticker_game_abbrs and entry['game_id'] in fd_game_team_abbrs:
                        game_abbrs = fd_game_team_abbrs[entry['game_id']]
                        if not ticker_game_abbrs.issubset(game_abbrs):
                            continue
                    fd_line = entry['point']
                    line_diff = abs(kalshi_line - (fd_line + 0.5))
                    if line_diff <= 0.5:
                        score = 1.0 - line_diff
                        if score > best_fd_score:
                            best_fd_score = score
                            best_fd_match = entry

        if not best_fd_match:
            continue

        ob = kalshi_api.get_orderbook(ticker)
        if not ob:
            continue
        time.sleep(0.3)

        yes_price = get_best_yes_price(ob)
        if yes_price is None:
            continue

        fee = kalshi_fee(yes_price)
        kalshi_eff = yes_price + fee

        # Direct one-way comparison: FD over implied vs Kalshi effective
        fd_implied = best_fd_match['fd_over_implied']

        # Edge = how much cheaper Kalshi is vs FD (in percentage points)
        edge_pct = (fd_implied - kalshi_eff) * 100

        if edge_pct >= LIVE_PROP_MIN_EDGE:
            game_id = best_fd_match['game_id']
            game_info = fd_games.get(game_id, {})
            game_name = f"{game_info.get('away', '?')} at {game_info.get('home', '?')}"

            edge = {
                'market_type': 'Live Prop',
                'sport': sport_name,
                'game': game_name,
                'team': f"{player_name} {kalshi_line}+",
                'opposite_team': '',
                'kalshi_price': yes_price,
                'kalshi_price_after_fees': kalshi_eff,
                'kalshi_prob_after_fees': kalshi_eff * 100,
                'kalshi_method': f"YES {player_name} {kalshi_line}+",
                'kalshi_ticker': ticker,
                'kalshi_side': 'yes',
                'fanduel_opposite_team': '',
                'fanduel_opposite_odds': best_fd_match['over_odds'],
                'fanduel_opposite_prob': fd_implied * 100,
                'total_implied_prob': 0,
                'arbitrage_profit': edge_pct,
                'is_live': True,
                'fair_value_mode': 'live/fd one-way',
                'per_book_detail': {'fanduel': fd_implied},
                'odds_last_update': best_fd_match.get('last_update', ''),
                'recommendation': f"Buy YES {player_name} {kalshi_line}+ on Kalshi at ${yes_price:.2f} (FD Over at {best_fd_match['over_odds']:.2f})",
            }
            edges.append(edge)
            send_telegram_notification(edge)

    return edges


# ============================================================
# PRE-GAME PLAYER PROP COMPARISON (FD one-way vs Kalshi YES/NO)
# ============================================================

def compare_pregame_props(kalshi_api, fd_data, prop_series_tickers, sport_name):
    """
    Compare FanDuel one-way player prop odds to Kalshi YES/NO prices.
    Returns comparison data for display (not just edges).

    For each matched player/threshold:
    - FD American odds + implied prob (raw, one-way)
    - Kalshi YES ask + NO ask prices
    - Difference between FD implied and Kalshi price

    prop_series_tickers: dict mapping market_key -> series_ticker
    """
    fd_props = fd_data['props']
    fd_games = fd_data['games']
    comparisons = []
    date_strs = _get_today_date_strs()

    # Determine team map for game verification
    first_ticker = next(iter(prop_series_tickers.values()), '')
    if 'NBA' in first_ticker:
        prop_team_map = NBA_TEAMS
    elif 'NHL' in first_ticker:
        prop_team_map = NHL_TEAMS
    else:
        prop_team_map = {}

    # Build team abbrev -> set of FD game_ids
    fd_game_team_abbrs = {}
    for game_id, ginfo in fd_games.items():
        fd_game_team_abbrs[game_id] = set()
        for abbr, full_name in prop_team_map.items():
            if _name_matches(full_name, ginfo.get('home', '')) or _name_matches(full_name, ginfo.get('away', '')):
                fd_game_team_abbrs[game_id].add(abbr)

    # Build FD lookup: {(player_lower, point, market_key): prop_data_with_game_id}
    fd_lookup = {}
    for game_id, event_props in fd_props.items():
        for prop in event_props:
            key = (prop['player'].lower().strip(), prop['point'], prop['market_key'])
            fd_lookup[key] = {**prop, 'game_id': game_id}

    # Process each prop series ticker
    for market_key, series_ticker in prop_series_tickers.items():
        kalshi_markets = kalshi_api.get_markets(series_ticker)
        today_markets = [m for m in kalshi_markets
                         if any(ds in m.get('ticker', '') for ds in date_strs)]
        if not today_markets:
            continue

        stat_label = market_key.replace('player_', '').replace('_', ' ').title()
        print(f"   Kalshi {series_ticker}: {len(today_markets)} {stat_label} markets today")

        for m in today_markets:
            ticker = m.get('ticker', '')
            title = m.get('title', '')
            subtitle = m.get('subtitle', '')

            # Extract game teams from ticker
            ticker_game_abbrs = set()
            ticker_parts = ticker.split('-')
            if len(ticker_parts) >= 2:
                game_part = ticker_parts[1]
                date_stripped = re.sub(r'^\d{2}[A-Z]{3}\d{2}', '', game_part)
                if prop_team_map:
                    team_abbr_set = set(prop_team_map.keys())
                    for i in range(1, len(date_stripped)):
                        t1, t2 = date_stripped[:i], date_stripped[i:]
                        if t1 in team_abbr_set and t2 in team_abbr_set:
                            ticker_game_abbrs = {t1, t2}
                            break

            # Extract player name and threshold: "Nikola Jokic: 25+ points"
            prop_match = re.match(r'^(.+?):\s*(\d+\.?\d*)\+', title or subtitle or '')
            if not prop_match:
                continue

            player_name = prop_match.group(1).strip()
            kalshi_threshold = float(prop_match.group(2))
            fd_point = kalshi_threshold - 0.5  # Kalshi "20+" = FD Over 19.5

            # Find matching FD prop
            best_fd = None
            for (fd_player, fd_pt, fd_mk), fd_entry in fd_lookup.items():
                if fd_mk != market_key:
                    continue
                if abs(fd_pt - fd_point) > 0.5:
                    continue
                if not _match_player_name(player_name, fd_entry['player']):
                    continue
                if ticker_game_abbrs and fd_entry['game_id'] in fd_game_team_abbrs:
                    game_abbrs = fd_game_team_abbrs[fd_entry['game_id']]
                    if not ticker_game_abbrs.issubset(game_abbrs):
                        continue
                best_fd = fd_entry
                break

            # Only fetch orderbook for FD-matched markets (saves ~580 API calls)
            if not best_fd:
                continue

            ob = kalshi_api.get_orderbook(ticker)
            if not ob:
                continue
            time.sleep(0.15)

            yes_price = get_best_yes_price(ob)
            no_price = get_best_no_price(ob)

            game_info = fd_games.get(best_fd['game_id'], {})
            game_name = f"{game_info.get('away', '?')} at {game_info.get('home', '?')}"

            comp = {
                'player': player_name,
                'stat': stat_label,
                'threshold': int(kalshi_threshold) if kalshi_threshold == int(kalshi_threshold) else kalshi_threshold,
                'game': game_name,
                'ticker': ticker,
                # FD side
                'fd_matched': True,
                'fd_american': best_fd['american_odds'],
                'fd_implied': best_fd['fd_implied'] * 100,
                'fd_player': best_fd['player'],
                'fd_point': best_fd['point'],
                # Kalshi side
                'kalshi_yes': yes_price,
                'kalshi_no': no_price,
                'kalshi_yes_pct': yes_price * 100 if yes_price else None,
                'kalshi_no_pct': no_price * 100 if no_price else None,
                # Difference (FD implied - Kalshi YES = how much cheaper Kalshi is)
                'diff_yes': (best_fd['fd_implied'] * 100 - yes_price * 100) if yes_price else None,
                'diff_no': ((1 - best_fd['fd_implied']) * 100 - no_price * 100) if no_price else None,
            }
            comparisons.append(comp)

    return comparisons


# ============================================================
# BTTS (BOTH TEAMS TO SCORE) EDGE FINDER
# ============================================================

def find_btts_edges(kalshi_api, fd_data, series_ticker, sport_name):
    """
    Compare Kalshi BTTS markets against FanDuel BTTS odds.

    Kalshi: "Both Teams To Score: Yes" at some YES/NO price
    FanDuel: BTTS Yes/No at decimal odds

    Uses opposite-side probability for fair value (same as spreads/totals).
    """
    converter = OddsConverter()
    fd_btts = fd_data['btts']
    fd_games = fd_data['games']
    edges = []
    date_strs = _get_today_date_strs()

    kalshi_markets = kalshi_api.get_markets(series_ticker)
    today_markets = [m for m in kalshi_markets
                     if any(ds in m.get('ticker', '') for ds in date_strs)]
    if not today_markets:
        return edges

    # Group Kalshi BTTS markets by game code
    # Ticker format expected: KXEPLBTTS-26JAN31LIVARS or similar
    game_groups = {}
    for m in today_markets:
        ticker = m.get('ticker', '')
        parts = ticker.split('-')
        if len(parts) < 2:
            continue
        game_part = parts[1] if len(parts) >= 2 else ''
        game_code = f"{parts[0]}-{game_part}"

        if game_code not in game_groups:
            game_groups[game_code] = []
        game_groups[game_code].append(m)

    for game_code, markets in game_groups.items():
        # Try to match this Kalshi game to a FanDuel game
        # Extract game_part for fuzzy matching
        parts = game_code.split('-')
        if len(parts) < 2:
            continue
        game_part = parts[1]

        # Try to match by team names in the game_part against FD games
        matched_game_id = None
        for gid, ginfo in fd_games.items():
            home = ginfo['home'].lower()
            away = ginfo['away'].lower()
            gp_lower = game_part.lower()
            # Check if any significant part of team names appears in game_part
            home_words = [w for w in home.split() if len(w) >= 3]
            away_words = [w for w in away.split() if len(w) >= 3]
            home_found = any(w in gp_lower for w in home_words)
            away_found = any(w in gp_lower for w in away_words)
            if home_found and away_found:
                matched_game_id = gid
                break

        if not matched_game_id or matched_game_id not in fd_btts:
            continue

        fd_game_btts = fd_btts[matched_game_id]
        game_info = fd_games.get(matched_game_id, {})
        game_name = f"{game_info.get('away', '?')} at {game_info.get('home', '?')}"
        commence_str = game_info.get('commence_time', '')
        game_live = is_game_live(commence_str)

        # Skip live games — The Odds API live data is unreliable
        if game_live:
            continue

        fd_yes_prob = converter.decimal_to_implied_prob(fd_game_btts['yes_odds'])
        fd_no_prob = converter.decimal_to_implied_prob(fd_game_btts['no_odds'])

        for m in markets:
            ticker = m.get('ticker', '')
            title = (m.get('title', '') or '').lower()
            subtitle = (m.get('subtitle', '') or '').lower()

            ob = kalshi_api.get_orderbook(ticker)
            if not ob:
                continue
            time.sleep(0.3)

            yes_price = get_best_yes_price(ob)
            no_price = get_best_no_price(ob)

            # Check YES (BTTS Yes): use opposite side (FD No) for fair value
            if yes_price is not None:
                fee = kalshi_fee(yes_price)
                eff = yes_price + fee
                total_implied = eff + fd_no_prob
                if total_implied < 1.0:
                    profit = (1.0 / total_implied - 1) * 100
                    if profit < MIN_EDGE_PERCENT:
                        continue
                    edge = {
                        'market_type': 'BTTS',
                        'sport': sport_name,
                        'game': game_name,
                        'team': 'BTTS Yes',
                        'opposite_team': 'BTTS No',
                        'kalshi_price': yes_price,
                        'kalshi_price_after_fees': eff,
                        'kalshi_prob_after_fees': eff * 100,
                        'kalshi_method': 'YES (Both Teams Score)',
                        'kalshi_ticker': ticker,
                        'kalshi_side': 'yes',
                        'fanduel_opposite_team': 'BTTS No',
                        'fanduel_opposite_odds': fd_game_btts['no_odds'],
                        'fanduel_opposite_prob': fd_no_prob * 100,
                        'total_implied_prob': total_implied * 100,
                        'arbitrage_profit': profit,
                        'is_live': game_live,
                        'fair_value_mode': fd_game_btts.get('_mode', ''),
                        'per_book_detail': fd_game_btts.get('per_book_no', {}),
                        'odds_last_update': fd_game_btts.get('_last_update', ''),
                        'recommendation': f"Buy YES BTTS on Kalshi at ${yes_price:.2f} (FanDuel BTTS No at {fd_game_btts['no_odds']:.2f})",
                    }
                    if books_diverge(edge['per_book_detail']):
                        print(f"   Skipping {edge['game']} BTTS YES: books diverge >10pp")
                        continue
                    edges.append(edge)
                    send_telegram_notification(edge)
                    auto_trade_edge(edge, kalshi_api)

            # Check NO (BTTS No): use opposite side (FD Yes) for fair value
            if no_price is not None:
                fee = kalshi_fee(no_price)
                eff = no_price + fee
                total_implied = eff + fd_yes_prob
                if total_implied < 1.0:
                    profit = (1.0 / total_implied - 1) * 100
                    if profit < MIN_EDGE_PERCENT:
                        continue
                    edge = {
                        'market_type': 'BTTS',
                        'sport': sport_name,
                        'game': game_name,
                        'team': 'BTTS No',
                        'opposite_team': 'BTTS Yes',
                        'kalshi_price': no_price,
                        'kalshi_price_after_fees': eff,
                        'kalshi_prob_after_fees': eff * 100,
                        'kalshi_method': 'NO (Both Teams Don\'t Score)',
                        'kalshi_ticker': ticker,
                        'kalshi_side': 'no',
                        'fanduel_opposite_team': 'BTTS Yes',
                        'fanduel_opposite_odds': fd_game_btts['yes_odds'],
                        'fanduel_opposite_prob': fd_yes_prob * 100,
                        'total_implied_prob': total_implied * 100,
                        'arbitrage_profit': profit,
                        'is_live': game_live,
                        'fair_value_mode': fd_game_btts.get('_mode', ''),
                        'per_book_detail': fd_game_btts.get('per_book_yes', {}),
                        'odds_last_update': fd_game_btts.get('_last_update', ''),
                        'recommendation': f"Buy NO BTTS on Kalshi at ${no_price:.2f} (FanDuel BTTS Yes at {fd_game_btts['yes_odds']:.2f})",
                    }
                    if books_diverge(edge['per_book_detail']):
                        print(f"   Skipping {edge['game']} BTTS NO: books diverge >10pp")
                        continue
                    edges.append(edge)
                    send_telegram_notification(edge)
                    auto_trade_edge(edge, kalshi_api)

    return edges


# ============================================================
# TENNIS EDGE FINDER
# ============================================================

def _extract_player_from_title(title: str) -> Optional[str]:
    """Extract player name from Kalshi tennis title.
    e.g. 'Will Matteo Martineau win the Martineau vs Damm Jr : Qualification Round 1 match?'
    -> 'Matteo Martineau'"""
    m = re.match(r'Will (.+?) win the ', title, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _tennis_name_matches(kalshi_name: str, fd_name: str) -> bool:
    """Check if a Kalshi player name matches a FanDuel player name.
    Handles variations: last name match, partial match, etc."""
    k = kalshi_name.lower().strip()
    f = fd_name.lower().strip()
    if k == f:
        return True
    # Last name match (last word)
    k_parts = k.split()
    f_parts = f.split()
    if k_parts and f_parts and k_parts[-1] == f_parts[-1]:
        # Last names match — check first name carefully
        if len(k_parts) == 1 or len(f_parts) == 1:
            return True  # Only last name available
        if k_parts[0] == f_parts[0]:
            return True  # First + last match
        # Require first 3+ chars match (not just initial) to avoid A. Zverev vs Andrey Zverev
        if len(k_parts[0]) >= 3 and len(f_parts[0]) >= 3 and k_parts[0][:3] == f_parts[0][:3]:
            return True  # First 3 chars + last match
        # One side has initial only (1-2 chars): accept if initial matches
        if (len(k_parts[0]) <= 2 or len(f_parts[0]) <= 2) and k_parts[0][0] == f_parts[0][0]:
            return True  # One side is abbreviated, initial match is acceptable
        # Multi-word last names: check last 2 words
        if len(k_parts) >= 2 and len(f_parts) >= 2:
            if k_parts[-2] == f_parts[-2]:
                return True
    # Check if one contains the other (handles middle names, suffixes)
    if k in f or f in k:
        return True
    return False


def find_tennis_edges(kalshi_api, fanduel_api, series_ticker: str, odds_api_keys: list, sport_name: str):
    """Find edges on tennis match-winner markets."""
    converter = OddsConverter()
    edges = []
    date_strs = _get_today_date_strs()

    # Step 1: Fetch Kalshi markets
    kalshi_markets = kalshi_api.get_markets(series_ticker)
    today_markets = [m for m in kalshi_markets
                     if any(ds in m.get('ticker', '') for ds in date_strs)]
    if not today_markets:
        return edges

    # Step 2: Fetch FanDuel odds from active tournament keys only
    active_sports = fanduel_api.get_active_sports()
    active_keys = [k for k in odds_api_keys if k in active_sports]
    if not active_keys:
        print(f"   No active tennis tournaments on The Odds API for {sport_name}")
        return edges
    print(f"   Active tournament keys: {', '.join(active_keys)}")

    all_fd_odds = {}  # player_name -> {odds, game_id, last_update, ...}
    all_fd_games = {}  # game_id -> {home, away, commence_time}
    for odds_key in active_keys:
        try:
            fd = fanduel_api.get_moneyline(odds_key)
            if fd['odds']:
                outcome_count = 0
                for game_id, game_outcomes in fd['odds'].items():
                    for name, data in game_outcomes.items():
                        all_fd_odds[name] = data
                        outcome_count += 1
                all_fd_games.update(fd['games'])
                print(f"   Fair value {odds_key} moneyline: {outcome_count} outcomes across {len(fd['odds'])} games")
            time.sleep(0.3)
        except Exception as e:
            continue

    if not all_fd_odds:
        print(f"   No tennis odds found for {sport_name}")
        return edges

    print(f"   Total tennis fair value odds: {len(all_fd_odds)} players across {len(all_fd_games)} matches")

    # Step 3: Group Kalshi markets by match (event_ticker)
    matches = {}
    for m in today_markets:
        event = m.get('event_ticker', '')
        if not event:
            continue
        if event not in matches:
            matches[event] = []
        matches[event].append(m)

    # Step 4: For each match, find FD odds and check for edges
    for event_ticker, match_markets in matches.items():
        if len(match_markets) != 2:
            continue

        # Extract player names from Kalshi titles
        players = []
        for m in match_markets:
            title = m.get('title', '')
            player = _extract_player_from_title(title)
            if player:
                players.append({'name': player, 'market': m})

        if len(players) != 2:
            continue

        p1, p2 = players[0], players[1]

        # Match to FanDuel odds
        fd_p1_name, fd_p2_name = None, None
        fd_p1_odds, fd_p2_odds = None, None
        for fd_name, fd_data in all_fd_odds.items():
            if _tennis_name_matches(p1['name'], fd_name):
                fd_p1_name = fd_name
                fd_p1_odds = fd_data
            elif _tennis_name_matches(p2['name'], fd_name):
                fd_p2_name = fd_name
                fd_p2_odds = fd_data

        if not fd_p1_odds or not fd_p2_odds:
            continue

        # Staleness check
        game_id = fd_p1_odds.get('game_id', '')
        commence_str = all_fd_games.get(game_id, {}).get('commence_time', '')
        game_live = is_game_live(commence_str)

        # Skip live games — The Odds API live data is unreliable
        if game_live:
            continue

        game_name = f"{p1['name']} vs {p2['name']}"

        # Get orderbooks
        ob1 = kalshi_api.get_orderbook(p1['market']['ticker'])
        time.sleep(0.3)
        ob2 = kalshi_api.get_orderbook(p2['market']['ticker'])
        time.sleep(0.3)
        if not ob1 or not ob2:
            continue

        p1_yes = get_best_yes_price(ob1)
        p1_no = get_best_no_price(ob1)
        p2_yes = get_best_yes_price(ob2)
        p2_no = get_best_no_price(ob2)
        if None in [p1_yes, p1_no, p2_yes, p2_no]:
            continue

        # Build entries: for each player, find cheapest way to bet on them
        # and compare to FD opposite side
        entries = []
        # Bet on player 1: YES on p1 or NO on p2 (whichever is cheaper)
        if p1_yes <= p2_no:
            entries.append((p1['name'], p1_yes, f"YES on {p1['name']}", fd_p2_name,
                           p1['market']['ticker'], 'yes'))
        else:
            entries.append((p1['name'], p2_no, f"NO on {p2['name']}", fd_p2_name,
                           p2['market']['ticker'], 'no'))
        # Bet on player 2: YES on p2 or NO on p1
        if p2_yes <= p1_no:
            entries.append((p2['name'], p2_yes, f"YES on {p2['name']}", fd_p1_name,
                           p2['market']['ticker'], 'yes'))
        else:
            entries.append((p2['name'], p1_no, f"NO on {p1['name']}", fd_p1_name,
                           p1['market']['ticker'], 'no'))

        match_edges = []
        for name, best_p, method, fd_opp_name, trade_ticker, trade_side in entries:
            fee = kalshi_fee(best_p)
            eff = best_p + fee
            fd_opp_data = all_fd_odds.get(fd_opp_name, {})
            if not fd_opp_data.get('odds'):
                continue
            fd_prob = converter.decimal_to_implied_prob(fd_opp_data['odds'])
            total = eff + fd_prob
            if total < 1.0:
                profit = (1.0 / total - 1) * 100
                if profit < MIN_EDGE_PERCENT:
                    continue
                edge = {
                    'market_type': 'Tennis ML',
                    'sport': sport_name,
                    'game': game_name,
                    'team': name,
                    'opposite_team': fd_opp_name,
                    'kalshi_price': best_p,
                    'kalshi_price_after_fees': eff,
                    'kalshi_prob_after_fees': eff * 100,
                    'kalshi_method': method,
                    'kalshi_ticker': trade_ticker,
                    'kalshi_side': trade_side,
                    'fanduel_opposite_team': fd_opp_name,
                    'fanduel_opposite_odds': fd_opp_data['odds'],
                    'fanduel_opposite_prob': fd_prob * 100,
                    'total_implied_prob': total * 100,
                    'arbitrage_profit': profit,
                    'is_live': game_live,
                    'fair_value_mode': fd_opp_data.get('mode', ''),
                    'per_book_detail': fd_opp_data.get('per_book', {}),
                    'odds_last_update': fd_opp_data.get('last_update', ''),
                    'recommendation': f"Buy {method} on Kalshi at ${best_p:.2f} (Fair value: {fd_opp_name} at {fd_opp_data['odds']:.2f})",
                }
                if books_diverge(edge['per_book_detail']):
                    print(f"   Skipping {edge['game']} tennis ML: books diverge >10pp")
                    continue
                match_edges.append(edge)
        # Only trade the best edge per match to avoid betting both sides
        if match_edges:
            match_edges.sort(key=lambda e: e['arbitrage_profit'], reverse=True)
            best_edge = match_edges[0]
            edges.append(best_edge)
            send_telegram_notification(best_edge)
            auto_trade_edge(best_edge, kalshi_api)

    return edges


# ============================================================
# LIVE STAT ARBITRAGE — Buy completed props during live games
# ============================================================

# ============================================================
# ESPN sport configs for live stat arbitrage
# Each sport has: espn_path, stat_labels_key (skater vs goalie), and stat parsers
# ============================================================

# ESPN endpoints by sport
ESPN_SPORTS = {
    'nba': {
        'espn_path': 'basketball/nba',
        'stat_groups': {
            'skater': {
                # Labels: ["MIN","PTS","FG","3PT","FT","REB","AST","TO","STL","BLK","OREB","DREB","PF","+/-"]
                'stats': {
                    'points':   {'index': 1, 'parse': 'int'},
                    'rebounds':  {'index': 5, 'parse': 'int'},
                    'assists':   {'index': 6, 'parse': 'int'},
                    'threes':    {'index': 3, 'parse': 'made'},
                    'steals':    {'index': 8, 'parse': 'int'},
                    'blocks':    {'index': 9, 'parse': 'int'},
                },
                'detect_labels': ['MIN', 'PTS'],
            },
        },
    },
    'ncaab': {
        'espn_path': 'basketball/mens-college-basketball',
        'stat_groups': {
            'skater': {
                # Same as NBA: ["MIN","PTS","FG","3PT","FT","REB","AST","TO","STL","BLK","OREB","DREB","PF"]
                'stats': {
                    'points':   {'index': 1, 'parse': 'int'},
                    'rebounds':  {'index': 5, 'parse': 'int'},
                    'assists':   {'index': 6, 'parse': 'int'},
                    'threes':    {'index': 3, 'parse': 'made'},
                },
                'detect_labels': ['MIN', 'PTS'],
            },
        },
    },
    'nhl': {
        'espn_path': 'hockey/nhl',
        'stat_groups': {
            'skater': {
                # Labels: ['BS','HT','TK','+/-','TOI','PPTOI','SHTOI','ESTOI','SHFT','G','YTDG','A','S','SM','SOG','FW','FL','FO%','GV','PN','PIM']
                'stats': {
                    'points':  {'index': [9, 11], 'parse': 'sum'},  # G + A = points
                    'goals':   {'index': 9, 'parse': 'int'},
                    'assists': {'index': 11, 'parse': 'int'},
                    'shots':   {'index': 14, 'parse': 'int'},  # SOG
                },
                'detect_labels': ['BS', 'HT'],
            },
            'goalie': {
                # Labels: ['GA','SA','SOS','SOSA','SV','SV%','ESSV','PPSV','SHSV','TOI','YTDG','PIM']
                'stats': {
                    'saves': {'index': 4, 'parse': 'int'},
                },
                'detect_labels': ['GA', 'SA'],
            },
        },
    },
}

# Map Kalshi series -> (espn_sport_key, stat_name, display_sport)
# Only include series confirmed to exist on Kalshi
PROP_STAT_MAP = {
    # NBA
    'KXNBAPTS':   {'sport': 'nba', 'stat_name': 'points',   'group': 'skater', 'display': 'NBA'},
    'KXNBAREB':   {'sport': 'nba', 'stat_name': 'rebounds',  'group': 'skater', 'display': 'NBA'},
    'KXNBAAST':   {'sport': 'nba', 'stat_name': 'assists',   'group': 'skater', 'display': 'NBA'},
    'KXNBA3PT':   {'sport': 'nba', 'stat_name': 'threes',    'group': 'skater', 'display': 'NBA'},
    # 'KXNBASTL':   {'sport': 'nba', 'stat_name': 'steals',    'group': 'skater', 'display': 'NBA'},  # DISABLED — paused
    # 'KXNBABLK':   {'sport': 'nba', 'stat_name': 'blocks',    'group': 'skater', 'display': 'NBA'},  # DISABLED — paused
    'KXNBADD':    {'sport': 'nba', 'stat_name': 'double_double', 'group': 'skater', 'display': 'NBA'},
    'KXNBATD':    {'sport': 'nba', 'stat_name': 'triple_double', 'group': 'skater', 'display': 'NBA'},
    # NHL
    'KXNHLPTS':   {'sport': 'nhl', 'stat_name': 'points',  'group': 'skater', 'display': 'NHL'},
    'KXNHLGOALS': {'sport': 'nhl', 'stat_name': 'goals',   'group': 'skater', 'display': 'NHL'},
    'KXNHLAST':   {'sport': 'nhl', 'stat_name': 'assists', 'group': 'skater', 'display': 'NHL'},
    'KXNHLSAVES': {'sport': 'nhl', 'stat_name': 'saves',   'group': 'goalie', 'display': 'NHL'},
}

# Max price to pay for a completed prop — buy anything below $1.00
# Even at $0.99, profit is ~$0.0093/contract after fees (free money is free money)
COMPLETED_PROP_MAX_PRICE = 1.00


def _parse_espn_stat(stat_str: str, parse_type: str, stat_config=None) -> int:
    """Parse ESPN stat string to integer value."""
    try:
        if parse_type == 'made':
            # Format: "2-6" (made-attempted), extract made count
            return int(stat_str.split('-')[0])
        elif parse_type == 'sum':
            # Sum multiple indices (e.g. goals + assists for NHL points)
            return 0  # handled in caller
        else:
            return int(stat_str)
    except (ValueError, IndexError):
        return 0


# ESPN abbreviation → Kalshi abbreviation mapping (only teams that differ)
# NBA: ESPN uses shorter abbrevs (GS, NY, NO, SA) vs Kalshi (GSW, NYK, NOP, SAS)
# NHL: ESPN and Kalshi both use TB, NJ, SJ, LA — no mapping needed
ESPN_TO_KALSHI = {
    'GS': 'GSW', 'NY': 'NYK', 'NO': 'NOP', 'SA': 'SAS',
    'UTAH': 'UTA', 'PHO': 'PHX',
}

# Soccer-specific ESPN→Kalshi mapping (separate to avoid conflicts with NBA/NHL abbrevs)
ESPN_TO_KALSHI_SOCCER = {
    # EPL
    'LIV': 'LFC', 'MAN': 'MUN', 'MNC': 'MCI', 'CHE': 'CFC', 'BHA': 'BRI',
    # Serie A
    'ROMA': 'ROM', 'COMO': 'COM', 'BOL': 'BFC', 'MIL': 'ACM',
    # Ligue 1
    'LILL': 'LIL', 'LYON': 'OL', 'METZ': 'FCM', 'OLM': 'OM',
    'LOR': 'FCL', 'NAN': 'FCN', 'MON': 'ASM', 'TOU': 'TFC',
    # Bundesliga
    'DOR': 'BVB', 'B04': 'LEV',
    # La Liga
    'MLL': 'MAL', 'BET': 'RBB',
}


def _get_live_games(espn_path: str) -> List[Dict]:
    """Get currently live games from ESPN scoreboard for any sport.
    Includes game_date_str to prevent matching yesterday's finals to today's markets."""
    try:
        resp = requests.get(
            f'https://site.api.espn.com/apis/site/v2/sports/{espn_path}/scoreboard',
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        live_games = []
        for event in data.get('events', []):
            status = event.get('status', {}).get('type', {}).get('name', '')
            if status in ('STATUS_IN_PROGRESS', 'STATUS_FINAL', 'STATUS_FULL_TIME',
                          'STATUS_END_PERIOD', 'STATUS_HALFTIME',
                          'STATUS_FIRST_HALF', 'STATUS_SECOND_HALF'):
                game_id = event.get('id', '')
                # Extract game date from ESPN event
                game_date_str = ''
                event_date = event.get('date', '') or ''
                if event_date and len(event_date) >= 10:
                    try:
                        gd = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
                        gd_eastern = gd.astimezone(ZoneInfo('America/New_York'))
                        game_date_str = gd_eastern.strftime('%y%b%d').upper()
                    except Exception:
                        pass
                competitors = event.get('competitions', [{}])[0].get('competitors', [])
                teams = {}
                _is_soccer = espn_path.startswith('soccer/')
                for c in competitors:
                    espn_abbr = c.get('team', {}).get('abbreviation', '')
                    abbr = ESPN_TO_KALSHI.get(espn_abbr, espn_abbr)
                    if _is_soccer:
                        abbr = ESPN_TO_KALSHI_SOCCER.get(espn_abbr, abbr)
                    teams[c.get('homeAway', '')] = abbr
                live_games.append({
                    'game_id': game_id,
                    'home': teams.get('home', ''),
                    'away': teams.get('away', ''),
                    'status': status,
                    'game_date_str': game_date_str,
                })
        return live_games
    except Exception as e:
        print(f"   ESPN scoreboard error ({espn_path}): {e}")
        return []


def _get_box_score(game_id: str, espn_path: str, sport_config: dict,
                   home_abbr: str = '', away_abbr: str = '',
                   game_date_str: str = '') -> Dict[str, Dict]:
    """Fetch box score for a game. Returns {player_name: {stat_name: value, ..., '_team': 'SA', '_game_teams': ('CHA','SA'), '_game_date': '26JAN31'}}."""
    try:
        resp = requests.get(
            f'https://site.api.espn.com/apis/site/v2/sports/{espn_path}/summary?event={game_id}',
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        player_stats = {}
        for team_data in data.get('boxscore', {}).get('players', []):
            espn_team = team_data.get('team', {}).get('abbreviation', '')
            team_abbr = ESPN_TO_KALSHI.get(espn_team, espn_team)
            for stat_group in team_data.get('statistics', []):
                labels = stat_group.get('labels', [])

                # Determine which stat group this is (skater vs goalie) by checking labels
                matched_group = None
                for group_name, group_config in sport_config['stat_groups'].items():
                    detect = group_config['detect_labels']
                    if len(labels) >= len(detect) and all(d in labels for d in detect):
                        # Make sure it's the right group (not a false match)
                        # Check first label matches
                        if labels[0] == detect[0]:
                            matched_group = (group_name, group_config)
                            break

                if not matched_group:
                    continue

                group_name, group_config = matched_group

                for athlete in stat_group.get('athletes', []):
                    name = athlete.get('athlete', {}).get('displayName', '')
                    stats = athlete.get('stats', [])
                    if not name or not stats:
                        continue

                    player_data = player_stats.get(name, {})
                    player_data['_team'] = team_abbr  # Track which team this player is on
                    player_data['_game_teams'] = (home_abbr, away_abbr)  # Both teams in this game
                    player_data['_game_date'] = game_date_str  # Track game date for cross-day verification
                    for stat_name, cfg in group_config['stats'].items():
                        idx = cfg['index']
                        parse = cfg['parse']
                        if parse == 'sum':
                            # Sum multiple indices
                            val = 0
                            for i in idx:
                                if i < len(stats):
                                    try:
                                        val += int(stats[i])
                                    except (ValueError, IndexError):
                                        pass
                            player_data[stat_name] = val
                        else:
                            if isinstance(idx, int) and idx < len(stats):
                                player_data[stat_name] = _parse_espn_stat(stats[idx], parse)
                    player_stats[name] = player_data

        # Compute double-double and triple-double for NBA players
        if 'basketball' in espn_path:
            for name, pdata in player_stats.items():
                cats_with_10 = 0
                for cat in ('points', 'rebounds', 'assists', 'steals', 'blocks'):
                    if pdata.get(cat, 0) >= 10:
                        cats_with_10 += 1
                pdata['double_double'] = 1 if cats_with_10 >= 2 else 0
                pdata['triple_double'] = 1 if cats_with_10 >= 3 else 0

        return player_stats
    except Exception as e:
        print(f"   ESPN box score error for game {game_id}: {e}")
        return {}


def _match_prop_player(kalshi_player: str, box_score: Dict[str, Dict]) -> Optional[str]:
    """Match a Kalshi player name to an ESPN box score name."""
    kp = kalshi_player.lower().strip()
    for espn_name in box_score:
        en = espn_name.lower()
        if kp == en:
            return espn_name
        # Last name match
        kp_parts = kp.split()
        en_parts = en.split()
        if kp_parts and en_parts and kp_parts[-1] == en_parts[-1]:
            if len(kp_parts) == 1 or len(en_parts) == 1:
                return espn_name
            if kp_parts[0] == en_parts[0]:
                return espn_name
            if len(kp_parts[0]) >= 3 and len(en_parts[0]) >= 3 and kp_parts[0][:3] == en_parts[0][:3]:
                return espn_name
        # Substring
        if kp in en or en in kp:
            return espn_name
    return None


def find_completed_props(kalshi_api) -> List[Dict]:
    """Find player prop markets where the target has already been met during live games.
    These are essentially guaranteed wins — buy YES at any price below $1.
    Supports NBA, NCAAB, NHL, and any sport with ESPN box score data."""
    edges = []

    # Group prop series by ESPN sport so we fetch each sport's scoreboard once
    sports_to_scan = {}  # sport_key -> list of (series_ticker, stat_info)
    for series_ticker, stat_info in PROP_STAT_MAP.items():
        sport_key = stat_info['sport']
        if sport_key not in sports_to_scan:
            sports_to_scan[sport_key] = []
        sports_to_scan[sport_key].append((series_ticker, stat_info))

    date_strs = _get_today_date_strs()

    for sport_key, prop_series_list in sports_to_scan.items():
        sport_config = ESPN_SPORTS.get(sport_key)
        if not sport_config:
            continue

        espn_path = sport_config['espn_path']

        # Step 1: Get live games for this sport
        live_games = _get_live_games(espn_path)
        if not live_games:
            continue

        live_game_abbrevs = set()
        for g in live_games:
            live_game_abbrevs.add(g['home'])
            live_game_abbrevs.add(g['away'])
        display_sport = prop_series_list[0][1]['display']
        print(f"   Live {display_sport} games: {len(live_games)} ({', '.join(g['away']+'@'+g['home'] for g in live_games)})")

        # Step 2: Fetch box scores for all live games
        all_player_stats = {}
        for game in live_games:
            box = _get_box_score(game['game_id'], espn_path, sport_config,
                                home_abbr=game['home'], away_abbr=game['away'],
                                game_date_str=game.get('game_date_str', ''))
            all_player_stats.update(box)
            time.sleep(0.3)

        if not all_player_stats:
            continue

        print(f"   {display_sport} box scores loaded: {len(all_player_stats)} players")

        # Step 3: For each prop type in this sport, find Kalshi markets where target is already met
        for series_ticker, stat_info in prop_series_list:
            stat_name = stat_info['stat_name']
            kalshi_markets = kalshi_api.get_markets(series_ticker)
            today_markets = [m for m in kalshi_markets
                             if any(ds in m.get('ticker', '') for ds in date_strs)]

            for m in today_markets:
                ticker = m.get('ticker', '')
                title = m.get('title', '')

                # Extract game teams from ticker for cross-checking
                # Ticker: KXNBAREB-26JAN31SACHA-CHASSCASTLE25-4
                # game_part: 26JAN31SACHA -> date_stripped: SACHA
                ticker_parts = ticker.split('-')
                if len(ticker_parts) < 2:
                    continue
                game_part = ticker_parts[1]
                date_stripped = re.sub(r'^\d{2}[A-Z]{3}\d{2}', '', game_part)

                # Verify at least one live game team is in this ticker's game
                game_is_live = any(abbr in date_stripped for abbr in live_game_abbrevs if len(abbr) >= 2)
                if not game_is_live:
                    continue

                # Parse player name and target from title: "LaMelo Ball: 8+ assists"
                prop_match = re.match(r'^(.+?):\s*(\d+)\+', title)
                if not prop_match:
                    continue

                player_name = prop_match.group(1).strip()
                target = int(prop_match.group(2))

                # Match to box score
                espn_name = _match_prop_player(player_name, all_player_stats)
                if not espn_name:
                    continue

                # CRITICAL: Verify the game date matches the ticker date
                # This prevents matching yesterday's FINAL stats to today's markets
                # (e.g., Bam Adebayo 21pts from Jan 31 MIA@CHI matching Feb 1 MIA@CHI ticker)
                ticker_date_match = re.match(r'^(\d{2}[A-Z]{3}\d{2})', game_part)
                ticker_date_str = ticker_date_match.group(1) if ticker_date_match else ''
                if not ticker_date_str:
                    continue  # Require valid date to prevent stale matching
                player_game_date = all_player_stats[espn_name].get('_game_date', '')
                if player_game_date and ticker_date_str != player_game_date:
                    _skip_key = f"{player_name}:{player_game_date}:{ticker_date_str}"
                    if not hasattr(find_completed_props, '_logged'):
                        find_completed_props._logged = set()
                    if _skip_key not in find_completed_props._logged:
                        find_completed_props._logged.add(_skip_key)
                        print(f"   Skipping {player_name}: game date {player_game_date} != ticker date {ticker_date_str}")
                    continue

                # Verify the player's game teams BOTH appear in this ticker
                # This prevents matching a player's stats from one game against a
                # different game's Kalshi market (e.g., Jan 31 SA@CHA stats vs Feb 1 SA@NYK market)
                player_game_teams = all_player_stats[espn_name].get('_game_teams', ('', ''))
                home_t, away_t = player_game_teams
                if home_t and away_t:
                    # Both teams from the ESPN game must appear in the ticker's game code
                    if home_t not in date_stripped or away_t not in date_stripped:
                        print(f"   Skipping {player_name}: game teams {away_t}@{home_t} don't match ticker {date_stripped}")
                        continue

                current_stat = all_player_stats[espn_name].get(stat_name, 0)

                # Check if target is already met
                if current_stat < target:
                    continue

                # Target met! Get full orderbook to buy everything available
                ob = kalshi_api.get_orderbook(ticker)
                if not ob:
                    continue
                time.sleep(0.2)

                yes_price = get_best_yes_price(ob)
                if yes_price is None or yes_price >= COMPLETED_PROP_MAX_PRICE:
                    continue

                # Calculate profit
                fee = kalshi_fee(yes_price)
                profit_per = 1.0 - yes_price - fee
                if profit_per <= 0:
                    continue

                edge = {
                    'market_type': 'Completed Prop',
                    'sport': display_sport,
                    'game': f"{player_name} - {stat_name}",
                    'team': player_name,
                    'opposite_team': '',
                    'kalshi_price': yes_price,
                    'kalshi_price_after_fees': yes_price + fee,
                    'kalshi_prob_after_fees': (yes_price + fee) * 100,
                    'kalshi_method': f"YES on {player_name} {target}+ {stat_name}",
                    'kalshi_ticker': ticker,
                    'kalshi_side': 'yes',
                    'fanduel_opposite_team': f"Already at {current_stat} {stat_name} (target: {target}+)",
                    'fanduel_opposite_odds': 0,
                    'fanduel_opposite_prob': 0,
                    'total_implied_prob': (yes_price + fee) * 100,
                    'arbitrage_profit': profit_per / (yes_price + fee) * 100,
                    'is_live': True,
                    'is_completed_prop': True,
                    'orderbook': ob,  # Pass full orderbook for max sizing
                    'recommendation': f"BUY {player_name} {target}+ {stat_name} at ${yes_price:.2f} — ALREADY AT {current_stat} (guaranteed)",
                }
                edges.append(edge)
                print(f"   COMPLETED PROP: {player_name} has {current_stat} {stat_name} (target {target}+) — ask ${yes_price:.2f}")
                send_telegram_notification(edge)
                auto_trade_completed_prop(edge, kalshi_api)

    return edges


def find_nhl_tied_game_totals(kalshi_api) -> List[Dict]:
    """Find NHL totals markets that are GUARANTEED due to tied games.

    In NHL, games cannot end in ties (OT/shootout decides winner).
    So if a game is tied X-X, the minimum final total is 2X+1 goals.

    Examples:
    - Tied 1-1 → minimum 3 goals → Over 2.5 GUARANTEED
    - Tied 2-2 → minimum 5 goals → Over 4.5 GUARANTEED
    - Tied 3-3 → minimum 7 goals → Over 6.5 GUARANTEED

    Buy YES on any Over market below the guaranteed threshold at any price < $1.00.
    """
    edges = []

    try:
        # Get live NHL games with scores from ESPN
        resp = requests.get(
            'https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard',
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        tied_games = []  # [(home_abbr, away_abbr, score, guaranteed_total, game_date_str), ...]

        for event in data.get('events', []):
            status = event.get('status', {}).get('type', {}).get('name', '')
            # Only look at games in progress (not finished)
            if status not in ('STATUS_IN_PROGRESS', 'STATUS_END_PERIOD', 'STATUS_HALFTIME'):
                continue

            # Extract game date for ticker matching
            game_date_str = ''
            event_date = event.get('date', '') or ''
            if event_date and len(event_date) >= 10:
                try:
                    gd = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
                    gd_eastern = gd.astimezone(ZoneInfo('America/New_York'))
                    game_date_str = gd_eastern.strftime('%y%b%d').upper()
                except Exception:
                    pass

            competitors = event.get('competitions', [{}])[0].get('competitors', [])
            home_score = away_score = 0
            home_abbr = away_abbr = ''

            for c in competitors:
                espn_abbr = c.get('team', {}).get('abbreviation', '')
                abbr = ESPN_TO_KALSHI.get(espn_abbr, espn_abbr)
                score = int(c.get('score', 0) or 0)
                if c.get('homeAway') == 'home':
                    home_score = score
                    home_abbr = abbr
                else:
                    away_score = score
                    away_abbr = abbr

            # Check if tied
            if home_score == away_score and home_score > 0:
                # Minimum final total = 2 * tie_score + 1 (someone must win)
                guaranteed_total = 2 * home_score + 1
                tied_games.append((home_abbr, away_abbr, home_score, guaranteed_total, game_date_str))
                print(f"   NHL tied game: {away_abbr}@{home_abbr} {home_score}-{away_score} → Over {guaranteed_total - 0.5} guaranteed")

        if not tied_games:
            return edges

        # Fetch NHL total markets from Kalshi
        markets = kalshi_api.get_markets('KXNHLTOTAL')
        if not markets:
            return edges

        for mkt in markets:
            ticker = mkt.get('ticker', '')
            title = mkt.get('title', '')
            status = mkt.get('status', '')

            if status != 'active':
                continue

            # Ticker format: KXNHLTOTAL-26FEB03DETBOS-55 (Over 5.5)
            # Extract teams and line from ticker
            parts = ticker.split('-')
            if len(parts) < 3:
                continue

            game_part = parts[1]  # e.g., 26FEB03DETBOS
            line_part = parts[2]  # e.g., 5 (means Over 5.5)

            # Extract date and teams from game_part
            ticker_date = game_part[:7] if len(game_part) >= 7 else ''  # 26FEB03
            teams_part = game_part[7:] if len(game_part) > 7 else ''  # DETBOS

            # Get the line from floor_strike field (preferred) or parse from ticker
            # Kalshi format: ticker ending in "5" = Over 5.5, "6" = Over 6.5, etc.
            floor_strike = mkt.get('floor_strike')
            if floor_strike is not None:
                line = float(floor_strike)
            else:
                try:
                    line = float(line_part) + 0.5  # "5" -> 5.5
                except ValueError:
                    continue

            # Check if this market matches any tied game
            for home_abbr, away_abbr, tie_score, guaranteed_total, game_date_str in tied_games:
                # Match teams (either order since it's a total)
                if not (home_abbr in teams_part and away_abbr in teams_part):
                    continue

                # Match date
                if ticker_date and game_date_str and ticker_date != game_date_str:
                    continue

                # Check if this is THE EXACT guaranteed line
                # Tied X-X → guaranteed_total = 2X+1 → target_line = 2X+0.5
                # 1-1 → 3 → Over 2.5 ONLY
                # 2-2 → 5 → Over 4.5 ONLY
                # 3-3 → 7 → Over 6.5 ONLY
                # 4-4 → 9 → Over 8.5 ONLY
                # 5-5 → 11 → Over 10.5 ONLY
                # 6-6 → 13 → Over 12.5 ONLY
                target_line = guaranteed_total - 0.5
                print(f"      Checking {ticker}: line={line}, target_line={target_line}, tied={tie_score}-{tie_score}")
                if abs(line - target_line) < 0.01:  # Only exact match
                    # This is a guaranteed win! Get the orderbook
                    time.sleep(0.2)
                    ob = kalshi_api.get_orderbook(ticker)
                    if not ob:
                        continue

                    ob_data = ob.get('orderbook', {})
                    no_bids = ob_data.get('no', [])  # YES ask = 100 - no_bid

                    # Find best YES ask price
                    yes_price = None
                    if no_bids:
                        best_no_bid = max(no_bids, key=lambda x: x[0])
                        yes_price = (100 - best_no_bid[0]) / 100.0

                    if yes_price is None or yes_price >= COMPLETED_PROP_MAX_PRICE:
                        continue

                    edge = {
                        'market_type': 'NHL Total (Tied)',
                        'sport': 'NHL',
                        'game': f"{away_abbr} @ {home_abbr}",
                        'team': f"Over {line}",
                        'kalshi_price': yes_price,
                        'kalshi_price_after_fees': yes_price + kalshi_fee(yes_price),
                        'kalshi_prob_after_fees': (yes_price + kalshi_fee(yes_price)) * 100,
                        'kalshi_ticker': ticker,
                        'kalshi_side': 'yes',
                        'fanduel_opposite_team': f"Game tied {tie_score}-{tie_score}",
                        'fanduel_opposite_odds': 0,
                        'fanduel_opposite_prob': 100.0,  # 100% certain
                        'total_implied_prob': yes_price * 100,
                        'arbitrage_profit': ((1.0 / yes_price) - 1) * 100,
                        'is_live': True,
                        'recommendation': f"BUY YES on Over {line} — game tied {tie_score}-{tie_score}, minimum {guaranteed_total} goals",
                        'orderbook': ob,
                    }
                    edges.append(edge)
                    print(f"   GUARANTEED NHL TOTAL: {away_abbr}@{home_abbr} Over {line} @ ${yes_price:.2f} (tied {tie_score}-{tie_score})")
                    send_telegram_notification(edge)
                    auto_trade_completed_prop(edge, kalshi_api)
                    break  # Only one match per market

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"   NHL tied game totals error: {e}")

    return edges


def find_basketball_analytically_final(kalshi_api) -> List[Dict]:
    """Find basketball moneyline markets that are GUARANTEED using Haslametrics formula.

    The #AnalyticallyFinal formula: Lead Safe = (Current Lead - 5)²

    This gives seconds remaining when a lead becomes statistically insurmountable.
    Examples:
    - Lead of 10 → safe at 25 seconds left ((10-5)² = 25)
    - Lead of 15 → safe at 100 seconds left (1:40)
    - Lead of 20 → safe at 225 seconds left (3:45)
    - Lead of 25 → safe at 400 seconds left (6:40)

    If seconds_remaining < (lead - 5)², the game is analytically final.
    Buy YES on the leading team's moneyline at any price < $1.00.
    """
    edges = []

    # ALL basketball leagues from Kalshi with correct game formats
    # Game format research:
    # - NBA: 4 x 12 min quarters = 48 min
    # - NCAAB Men: 2 x 20 min halves = 40 min
    # - NCAAB Women: 4 x 10 min quarters = 40 min (changed in 2015)
    # - WNBA: 4 x 10 min quarters = 40 min
    # - All FIBA/International: 4 x 10 min quarters = 40 min
    basketball_configs = [
        # === US Pro ===
        {
            'espn_path': 'basketball/nba',
            'kalshi_series': 'KXNBAGAME',
            'sport_name': 'NBA',
            'quarters': 4,
            'period_minutes': 12,  # 4x12 = 48 min total
        },
        {
            'espn_path': 'basketball/wnba',
            'kalshi_series': 'KXWNBAGAME',
            'sport_name': 'WNBA',
            'quarters': 4,
            'period_minutes': 10,  # 4x10 = 40 min total
        },
        # === US College ===
        {
            'espn_path': 'basketball/mens-college-basketball',
            'kalshi_series': 'KXNCAAMBGAME',
            'sport_name': 'NCAAB (M)',
            'quarters': 2,  # 2 halves
            'period_minutes': 20,  # 2x20 = 40 min total
        },
        {
            'espn_path': 'basketball/womens-college-basketball',
            'kalshi_series': 'KXNCAAWBGAME',
            'sport_name': 'NCAAB (W)',
            'quarters': 4,
            'period_minutes': 10,  # 4x10 = 40 min total
        },
        # === European Pro ===
        {
            'espn_path': 'basketball/euroleague',  # ESPN may not have this
            'kalshi_series': 'KXEUROLEAGUEGAME',
            'sport_name': 'Euroleague',
            'quarters': 4,
            'period_minutes': 10,  # FIBA rules: 4x10 = 40 min
        },
        {
            'espn_path': 'basketball/eurocup',  # ESPN may not have this
            'kalshi_series': 'KXEUROCUPGAME',
            'sport_name': 'EuroCup',
            'quarters': 4,
            'period_minutes': 10,  # FIBA rules: 4x10 = 40 min
        },
        # === FIBA Competitions ===
        {
            'espn_path': 'basketball/fiba-champions-league',  # ESPN may not have this
            'kalshi_series': 'KXFIBACHLGAME',
            'sport_name': 'FIBA Champions League',
            'quarters': 4,
            'period_minutes': 10,  # FIBA rules
        },
        {
            'espn_path': 'basketball/fiba-europe-cup',  # ESPN may not have this
            'kalshi_series': 'KXFIBAEUCGAME',
            'sport_name': 'FIBA Europe Cup',
            'quarters': 4,
            'period_minutes': 10,  # FIBA rules
        },
        # === International Leagues ===
        {
            'espn_path': 'basketball/nbl-australia',  # ESPN may not have this
            'kalshi_series': 'KXNBLGAME',
            'sport_name': 'NBL Australia',
            'quarters': 4,
            'period_minutes': 10,  # FIBA rules
        },
        {
            'espn_path': 'basketball/japan-b-league',  # ESPN may not have this
            'kalshi_series': 'KXBLEAGUEGAME',
            'sport_name': 'Japan B League',
            'quarters': 4,
            'period_minutes': 10,  # FIBA rules
        },
        {
            'espn_path': 'basketball/korea-kbl',  # ESPN may not have this
            'kalshi_series': 'KXKBLGAME',
            'sport_name': 'South Korea KBL',
            'quarters': 4,
            'period_minutes': 10,  # FIBA rules
        },
        {
            'espn_path': 'basketball/france-lnb',  # ESPN may not have this
            'kalshi_series': 'KXLNBGAME',
            'sport_name': 'LNB Elite (France)',
            'quarters': 4,
            'period_minutes': 10,  # FIBA rules
        },
        {
            'espn_path': 'basketball/argentina-liga-nacional',  # ESPN may not have this
            'kalshi_series': 'KXLNBARGAME',
            'sport_name': 'Liga Nacional (Argentina)',
            'quarters': 4,
            'period_minutes': 10,  # FIBA rules
        },
        # === New Leagues ===
        {
            'espn_path': 'basketball/unrivaled',  # New women's league
            'kalshi_series': 'KXUNRIVALEDGAME',
            'sport_name': 'Unrivaled',
            'quarters': 4,
            'period_minutes': 10,  # Uses FIBA-style quarters
        },
    ]

    for config in basketball_configs:
        try:
            # Get live games with scores and time from ESPN
            # Note: Many international leagues may not have ESPN coverage - that's OK, we silently skip them
            resp = requests.get(
                f"https://site.api.espn.com/apis/site/v2/sports/{config['espn_path']}/scoreboard",
                timeout=5
            )
            if resp.status_code == 404:
                # ESPN doesn't have this league - silently continue
                continue
            resp.raise_for_status()
            data = resp.json()

            analytically_final_games = []
            close_games = []  # Games that are CLOSE to analytically final (for logging)

            for event in data.get('events', []):
                status_obj = event.get('status', {})
                status = status_obj.get('type', {}).get('name', '')

                # Only look at games in progress
                if status not in ('STATUS_IN_PROGRESS', 'STATUS_END_PERIOD', 'STATUS_HALFTIME'):
                    continue

                # Get current period and clock
                period = status_obj.get('period', 0)
                clock_str = status_obj.get('displayClock', '0:00')

                # Parse clock (MM:SS or M:SS)
                try:
                    parts = clock_str.split(':')
                    if len(parts) == 2:
                        clock_minutes = int(parts[0])
                        clock_seconds = int(parts[1])
                    else:
                        clock_minutes = 0
                        clock_seconds = int(parts[0]) if parts[0].isdigit() else 0
                except:
                    clock_minutes = 0
                    clock_seconds = 0

                # Calculate total seconds remaining in game
                seconds_in_period = clock_minutes * 60 + clock_seconds

                # CRITICAL: Handle overtime correctly
                # In OT, period > quarters, so periods_remaining would be negative
                # OT periods are 5 minutes for ALL basketball leagues (NBA, NCAAB, FIBA)
                # In OT we only know the current period's remaining time
                if period > config['quarters']:
                    # Overtime — only the current period clock matters
                    seconds_remaining = seconds_in_period
                else:
                    periods_remaining = config['quarters'] - period
                    seconds_remaining = seconds_in_period + (periods_remaining * config['period_minutes'] * 60)

                # Extract game date for ticker matching
                game_date_str = ''
                event_date = event.get('date', '') or ''
                if event_date and len(event_date) >= 10:
                    try:
                        gd = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
                        gd_eastern = gd.astimezone(ZoneInfo('America/New_York'))
                        game_date_str = gd_eastern.strftime('%y%b%d').upper()
                    except:
                        pass

                # Get scores and teams
                competitors = event.get('competitions', [{}])[0].get('competitors', [])
                home_score = away_score = 0
                home_abbr = away_abbr = ''
                home_name = away_name = ''

                for c in competitors:
                    espn_abbr = c.get('team', {}).get('abbreviation', '')
                    abbr = ESPN_TO_KALSHI.get(espn_abbr, espn_abbr)
                    score = int(c.get('score', 0) or 0)
                    name = c.get('team', {}).get('shortDisplayName', espn_abbr)
                    if c.get('homeAway') == 'home':
                        home_score = score
                        home_abbr = abbr
                        home_name = name
                    else:
                        away_score = score
                        away_abbr = abbr
                        away_name = name

                # Calculate lead
                lead = abs(home_score - away_score)

                # Determine leading team for logging
                if home_score > away_score:
                    leading_abbr = home_abbr
                    leading_name = home_name
                else:
                    leading_abbr = away_abbr
                    leading_name = away_name

                mins_left = seconds_remaining // 60
                secs_left = seconds_remaining % 60

                if lead <= 5:
                    # Log close games even if not analytically final
                    print(f"   {config['sport_name']} game: {away_abbr}@{home_abbr} {away_score}-{home_score}, lead {lead} (need >5)")
                    continue  # Formula only works for leads > 5

                # Haslametrics formula: safe_seconds = (lead - 5)²
                safe_seconds = (lead - 5) ** 2

                # Check if game is analytically final
                if seconds_remaining < safe_seconds:
                    analytically_final_games.append({
                        'home_abbr': home_abbr,
                        'away_abbr': away_abbr,
                        'leading_abbr': leading_abbr,
                        'leading_name': leading_name,
                        'lead': lead,
                        'score': f"{away_score}-{home_score}",
                        'seconds_remaining': seconds_remaining,
                        'safe_seconds': safe_seconds,
                        'game_date_str': game_date_str,
                    })
                    print(f"   {config['sport_name']} ANALYTICALLY FINAL: {away_abbr}@{home_abbr} {away_score}-{home_score}, "
                          f"lead {lead}, {mins_left}:{secs_left:02d} left (safe at {safe_seconds}s)")
                else:
                    # Track games that are CLOSE to analytically final (within 3x safe time)
                    if seconds_remaining < safe_seconds * 3:
                        close_games.append({
                            'game': f"{away_abbr}@{home_abbr}",
                            'score': f"{away_score}-{home_score}",
                            'lead': lead,
                            'seconds_remaining': seconds_remaining,
                            'safe_seconds': safe_seconds,
                            'leading': leading_name,
                        })
                        print(f"   {config['sport_name']} CLOSE: {away_abbr}@{home_abbr} {away_score}-{home_score}, "
                              f"lead {lead}, {mins_left}:{secs_left:02d} left (need <{safe_seconds}s)")
                    else:
                        print(f"   {config['sport_name']} game: {away_abbr}@{home_abbr} {away_score}-{home_score}, "
                              f"lead {lead}, {mins_left}:{secs_left:02d} left (need <{safe_seconds}s, has {seconds_remaining}s)")

            # Log summary for this sport
            print(f"   {config['sport_name']} summary: {len(analytically_final_games)} final, {len(close_games)} close")

            if not analytically_final_games:
                continue

            # Fetch moneyline markets from Kalshi
            markets = kalshi_api.get_markets(config['kalshi_series'])
            if not markets:
                print(f"   {config['sport_name']}: NO KALSHI MARKETS found for {config['kalshi_series']}")
                continue

            print(f"   {config['sport_name']}: Found {len(markets)} Kalshi markets, checking for matches...")

            for mkt in markets:
                ticker = mkt.get('ticker', '')
                title = mkt.get('title', '')
                mkt_status = mkt.get('status', '')

                if mkt_status != 'active':
                    continue

                # Ticker format: KXNBAGAME-26FEB03BOSLAL-BOS
                parts = ticker.split('-')
                if len(parts) < 3:
                    continue

                game_part = parts[1]  # e.g., 26FEB03BOSLAL
                team_part = parts[2]  # e.g., BOS (the team this contract is for)

                ticker_date = game_part[:7] if len(game_part) >= 7 else ''
                teams_part = game_part[7:] if len(game_part) > 7 else ''

                # Check if this market matches any analytically final game
                for game in analytically_final_games:
                    # Match teams
                    if not (game['home_abbr'] in teams_part and game['away_abbr'] in teams_part):
                        continue

                    # Match date
                    if ticker_date and game['game_date_str'] and ticker_date != game['game_date_str']:
                        continue

                    # Check if this contract is for the LEADING team
                    if team_part != game['leading_abbr']:
                        continue

                    # Found a match! Get the orderbook
                    print(f"   MATCH: {ticker} for {game['leading_name']} (up {game['lead']})")
                    time.sleep(0.2)
                    ob = kalshi_api.get_orderbook(ticker)
                    if not ob:
                        print(f"   SKIP: {ticker} - no orderbook data")
                        continue

                    ob_data = ob.get('orderbook', {})
                    no_bids = ob_data.get('no', [])

                    # Find best YES ask price
                    yes_price = None
                    if no_bids:
                        best_no_bid = max(no_bids, key=lambda x: x[0])
                        yes_price = (100 - best_no_bid[0]) / 100.0

                    if yes_price is None:
                        print(f"   SKIP: {ticker} - no liquidity (no asks)")
                        continue

                    if yes_price >= COMPLETED_PROP_MAX_PRICE:
                        print(f"   SKIP: {ticker} - price ${yes_price:.2f} >= ${COMPLETED_PROP_MAX_PRICE:.2f}")
                        continue

                    mins_left = game['seconds_remaining'] // 60
                    secs_left = game['seconds_remaining'] % 60

                    edge = {
                        'market_type': f"{config['sport_name']} ML (Final)",
                        'sport': config['sport_name'],
                        'game': f"{game['away_abbr']} @ {game['home_abbr']}",
                        'team': game['leading_name'],
                        'kalshi_price': yes_price,
                        'kalshi_price_after_fees': yes_price + kalshi_fee(yes_price),
                        'kalshi_prob_after_fees': (yes_price + kalshi_fee(yes_price)) * 100,
                        'kalshi_ticker': ticker,
                        'kalshi_side': 'yes',
                        'fanduel_opposite_team': f"Lead {game['lead']}, {mins_left}:{secs_left:02d} left",
                        'fanduel_opposite_odds': 0,
                        'fanduel_opposite_prob': 100.0,
                        'total_implied_prob': yes_price * 100,
                        'arbitrage_profit': ((1.0 / yes_price) - 1) * 100,
                        'is_live': True,
                        'recommendation': f"BUY YES {game['leading_name']} — up {game['lead']} with {mins_left}:{secs_left:02d} left (analytically final)",
                        'orderbook': ob,
                    }
                    edges.append(edge)
                    print(f"   ANALYTICALLY FINAL: {game['away_abbr']}@{game['home_abbr']} {game['leading_name']} @ ${yes_price:.2f}")
                    send_telegram_notification(edge)
                    auto_trade_completed_prop(edge, kalshi_api)
                    break

        except requests.exceptions.HTTPError as e:
            # Silently skip leagues that ESPN doesn't support (404, etc.)
            if e.response is not None and e.response.status_code in (404, 400):
                continue
            print(f"   Basketball analytically final HTTP error ({config['sport_name']}): {e}")
        except requests.exceptions.RequestException:
            # Network errors - silently continue to next league
            continue
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"   Basketball analytically final error ({config['sport_name']}): {e}")

    return edges


def auto_trade_completed_prop(edge: Dict, kalshi_api) -> Optional[Dict]:
    """Auto-trade a completed prop. Buy MAX contracts since it's guaranteed money.
    Sweeps the entire ask side of the orderbook up to account balance."""
    global _order_tracker

    if not AUTO_TRADE_ENABLED:
        return None

    ticker = edge.get('kalshi_ticker')
    if not ticker:
        return None

    # NOTE: Intentionally NOT checking has_position for completed props.
    # These are GUARANTEED wins (player already hit the threshold), so we
    # should keep buying as long as there's liquidity below $0.99.
    # The orderbook sweep logic handles position sizing naturally.

    if not _order_tracker.can_trade():
        return None

    price = edge['kalshi_price']

    # Get account balance to determine max spend
    balance = kalshi_api.get_balance()
    avail = 0
    if balance:
        avail = balance.get('balance', 0) / 100  # cents to dollars

    if avail <= 0:
        print(f"   >>> No balance available for completed prop {ticker}")
        return None

    # Sweep the ask side: buy at the best ask price, as many as we can afford
    # The orderbook has no_bids — YES ask = 100 - no_bid price
    # We want to buy at every price level below $0.99
    ob = edge.get('orderbook') or kalshi_api.get_orderbook(ticker)
    if not ob:
        return None

    ob_data = ob.get('orderbook', {})
    no_bids = ob_data.get('no', [])  # Each is [price_cents, quantity]

    if not no_bids:
        return None

    # Sort no bids descending by price (highest no bid = cheapest YES ask)
    no_bids_sorted = sorted(no_bids, key=lambda x: x[0], reverse=True)

    # Completed props are GUARANTEED — player already hit the threshold.
    # Buy as much as the orderbook and balance allow (no artificial caps).
    remaining_balance = min(avail, 5000.00)  # Up to $5000 (balance is real cap)
    remaining_profit_target = 999.00  # Effectively uncapped
    total_contracts = 0
    total_cost = 0
    best_price = None

    for bid_price_cents, qty in no_bids_sorted:
        yes_price = (100 - bid_price_cents) / 100.0
        if yes_price >= COMPLETED_PROP_MAX_PRICE:
            continue

        fee_per = kalshi_fee(yes_price)
        cost_per = yes_price + fee_per
        profit_per = 1.0 - cost_per

        if profit_per <= 0:
            continue

        if best_price is None:
            best_price = yes_price

        # How many can we buy at this level?
        can_afford = int(remaining_balance / cost_per) if cost_per > 0 else 0
        # Cap by remaining profit target
        max_by_profit = int(remaining_profit_target / profit_per) if profit_per > 0 else 0
        buy_qty = min(qty, can_afford, max(1, max_by_profit))

        if buy_qty <= 0:
            break

        level_fee = math.ceil(0.07 * buy_qty * yes_price * (1 - yes_price) * 100) / 100
        level_cost = (yes_price * buy_qty) + level_fee
        level_profit = (1.0 * buy_qty) - level_cost

        total_contracts += buy_qty
        total_cost += level_cost
        remaining_balance -= level_cost
        remaining_profit_target -= level_profit

        # Stop if we've hit our profit target
        if remaining_profit_target <= 0:
            break

    if total_contracts <= 0 or best_price is None:
        return None

    total_profit = (1.0 * total_contracts) - total_cost

    if total_profit <= 0:
        return None

    # Final safety check (generous for guaranteed props)
    if total_cost > 5000.00:
        print(f"   >>> SAFETY BLOCK: {ticker} cost ${total_cost:.2f} exceeds $5000 limit")
        return None

    # Place the order at the best ask price for the total contracts
    # Kalshi will fill at best available prices up to our limit price
    # Use the worst (highest) YES price we're willing to pay as limit
    worst_yes_cents = 99  # max $0.99
    for bid_price_cents, qty in no_bids_sorted:
        yes_price = (100 - bid_price_cents) / 100.0
        if yes_price >= COMPLETED_PROP_MAX_PRICE:
            continue
        fee_per = kalshi_fee(yes_price)
        if (1.0 - yes_price - fee_per) > 0:
            worst_yes_cents = int(round(yes_price * 100))

    # Place at best price — Kalshi limit orders fill at best available
    price_cents = int(round(best_price * 100))

    print(f"   >>> COMPLETED PROP MAX TRADE: {ticker} YES {total_contracts}x @ ${best_price:.2f} = ${total_cost:.2f} (guaranteed profit ${total_profit:.2f})")

    order = kalshi_api.place_order(ticker, 'yes', price_cents, total_contracts)
    if order:
        fee_total = math.ceil(0.07 * total_contracts * best_price * (1 - best_price) * 100) / 100
        order_info = {
            'ticker': ticker,
            'side': 'yes',
            'price': best_price,
            'fee': fee_total,
            'contracts': total_contracts,
            'cost': total_cost,
            'potential_profit': total_profit,
            'edge_pct': edge['arbitrage_profit'],
            'sport': edge.get('sport', 'NBA'),
            'market_type': 'Completed Prop',
            'game': edge.get('game', ''),
            'team': edge.get('team', ''),
            'recommendation': edge.get('recommendation', ''),
            'timestamp': datetime.utcnow().isoformat(),
            'order_id': order.get('order_id', ''),
            'status': order.get('status', 'unknown'),
        }
        _order_tracker.add_order(ticker, order_info)
        send_order_telegram(order_info, 'COMPLETED PROP')
        return order_info

    return None


# ============================================================
# RESOLVED MARKET FINDER — REMOVED
# Was auto-buying Kalshi markets it thought had known outcomes (game results,
# crypto prices, economic data, stock indices). Caused ~$900 in losses due to
# incorrect NCAAB game matching. All resolved market code has been deleted.
# Only completed props sniper should auto-trade.
# ============================================================


# ============================================================
# COMPLETED PROPS SNIPER — dedicated fast-scan thread
# ============================================================

COMPLETED_PROPS_SCAN_INTERVAL = 15  # Scan every 15 seconds — guaranteed markets only, faster for analytically final

def _completed_props_sniper_loop():
    """Dedicated thread that scans completed player props more frequently.

    The main scan loop takes minutes due to moneyline/spread/total checks.
    Completed props are free money — a player has ALREADY hit the stat threshold
    but cheap YES contracts are still available. We need to find and buy these
    as fast as possible before the market catches up.

    This thread runs independently every 60 seconds, checking only prop markets
    against live ESPN box scores.
    """
    # Wait for initial startup
    time.sleep(30)
    print("Completed props sniper thread started")

    while True:
        try:
            kalshi = KalshiAPI(KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY)
            print(f"\n--- Completed Props Sniper Scan ---")

            all_guaranteed = []

            # 1. Completed player props (stat already hit)
            completed = find_completed_props(kalshi)
            all_guaranteed.extend(completed)

            # 2. NHL tied game totals (guaranteed by no-tie rule)
            nhl_tied = find_nhl_tied_game_totals(kalshi)
            all_guaranteed.extend(nhl_tied)

            if all_guaranteed:
                with _scan_lock:
                    # Merge into cached edges (avoid duplicates by ticker)
                    existing_tickers = {e.get('kalshi_ticker') for e in _scan_cache['edges']}
                    for edge in all_guaranteed:
                        if edge.get('kalshi_ticker') not in existing_tickers:
                            _scan_cache['edges'].append(edge)
                print(f"   Props sniper: {len(completed)} props, {len(nhl_tied)} NHL tied")
            else:
                print(f"   Props sniper: no guaranteed opportunities")

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Completed props sniper error: {e}")

        time.sleep(COMPLETED_PROPS_SCAN_INTERVAL)


def start_completed_props_sniper():
    """Start the completed props sniper thread (called once on app boot)."""
    t = threading.Thread(target=_completed_props_sniper_loop, daemon=True)
    t.start()
    print("Completed props sniper thread launched")



# ============================================================
# MAIN SCANNER
# ============================================================

def scan_all_sports(kalshi_api, fanduel_api):
    all_edges = []
    sports_scanned = []
    sports_with_games = []

    # Sync positions from Kalshi API at start of each scan
    _order_tracker.refresh_from_api(kalshi_api)

    # 1. Pre-game player prop comparison (FD one-way vs Kalshi YES/NO)
    # Run FIRST so /props page populates quickly after deploy
    all_prop_comparisons = []
    prop_sport_groups = {}  # sport_key -> {market_key: series_ticker, 'name': display_name}
    for series_ticker, (sport_key, market_key, display_name) in PLAYER_PROP_SPORTS.items():
        if sport_key not in prop_sport_groups:
            prop_sport_groups[sport_key] = {'tickers': {}, 'name': display_name.split()[0]}  # 'NBA', 'NHL'
        prop_sport_groups[sport_key]['tickers'][market_key] = series_ticker

    for sport_key, group in prop_sport_groups.items():
        group_name = f"{group['name']} Props"
        print(f"\n--- {group_name} (pregame) ---")
        market_keys = list(group['tickers'].keys())
        fd = fanduel_api.get_player_props_pregame(sport_key, market_keys)
        sports_scanned.append(group_name)
        if not fd['props']:
            continue
        sports_with_games.append(group_name)
        comps = compare_pregame_props(kalshi_api, fd, group['tickers'], group_name)
        all_prop_comparisons.extend(comps)
        print(f"   {group_name}: {len(comps)} FD-matched props compared")
        time.sleep(1.0)

    # Store prop comparisons immediately so /props page has data ASAP
    with _scan_lock:
        _scan_cache['prop_comparisons'] = all_prop_comparisons
    print(f"   Prop comparisons cached: {len(all_prop_comparisons)} total")

    # 2. Moneyline markets
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

    # 3. Spread markets
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

    # 4. Total markets
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

    # 5. BTTS markets
    for kalshi_series, (odds_key, name) in BTTS_SPORTS.items():
        print(f"\n--- {name} ({kalshi_series}) ---")
        fd = fanduel_api.get_btts(odds_key)
        sports_scanned.append(name)
        if not fd['btts']:
            continue
        sports_with_games.append(name)
        edges = find_btts_edges(kalshi_api, fd, kalshi_series, name)
        all_edges.extend(edges)
        print(f"   {name}: {len(edges)} edges")
        time.sleep(1.0)

    # 6. Tennis match-winner markets
    for kalshi_series, (odds_keys, name) in TENNIS_SPORTS.items():
        print(f"\n--- {name} ({kalshi_series}) ---")
        sports_scanned.append(name)
        edges = find_tennis_edges(kalshi_api, fanduel_api, kalshi_series, odds_keys, name)
        if edges:
            sports_with_games.append(name)
        all_edges.extend(edges)
        print(f"   {name}: {len(edges)} edges")
        time.sleep(1.0)

    # 7. Live stat arbitrage — buy completed player props
    print(f"\n--- Completed Props (Live Stat Arb) ---")
    sports_scanned.append('Live Props')
    completed = find_completed_props(kalshi_api)
    all_edges.extend(completed)
    print(f"   Completed props: {len(completed)} opportunities")

    # 7b. NHL tied game totals — guaranteed by no-tie rule
    print(f"\n--- NHL Tied Game Totals (Guaranteed) ---")
    nhl_tied = find_nhl_tied_game_totals(kalshi_api)
    all_edges.extend(nhl_tied)
    print(f"   NHL tied totals: {len(nhl_tied)} opportunities")

    # 7c. Basketball analytically final — DISABLED (not working reliably)
    # print(f"\n--- Basketball Analytically Final (Haslametrics) ---")
    # bball_final = find_basketball_analytically_final(kalshi_api)
    # all_edges.extend(bball_final)
    # print(f"   Basketball final: {len(bball_final)} opportunities")

    if completed or nhl_tied:
        sports_with_games.append('Live Props')

    # Filter out edges below minimum threshold before returning
    before_count = len(all_edges)
    all_edges = [e for e in all_edges if e.get('arbitrage_profit', 0) >= MIN_EDGE_PERCENT]

    print(f"\n{'='*60}")
    print(f"SCAN COMPLETE")
    print(f"Markets checked: {', '.join(sports_scanned)}")
    print(f"Active today: {', '.join(sports_with_games) if sports_with_games else 'None'}")
    print(f"Total edges >= {MIN_EDGE_PERCENT}%: {len(all_edges)} (filtered {before_count - len(all_edges)} sub-threshold)")
    print(f"{'='*60}\n")

    return all_edges, sports_scanned, sports_with_games


# ============================================================
# BACKGROUND SCANNER
# ============================================================

def _background_scan_loop():
    """Runs continuously in a background thread. Scans, rests 30s, repeats."""
    global _scan_cache
    print("Background scanner started")
    while True:
        try:
            with _scan_lock:
                _scan_cache['is_scanning'] = True

            kalshi = KalshiAPI(KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY)
            fanduel = FanDuelAPI(ODDS_API_KEY)
            all_edges, scanned, active = scan_all_sports(kalshi, fanduel)

            with _scan_lock:
                _scan_cache['edges'] = all_edges
                _scan_cache['sports_scanned'] = scanned
                _scan_cache['sports_with_games'] = active
                _scan_cache['timestamp'] = datetime.utcnow().isoformat()
                _scan_cache['scan_count'] += 1
                _scan_cache['is_scanning'] = False

            print(f"Background scan #{_scan_cache['scan_count']} complete: {len(all_edges)} edges. Resting {SCAN_REST_SECONDS}s...")

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Background scan error: {e}")
            with _scan_lock:
                _scan_cache['is_scanning'] = False

        time.sleep(SCAN_REST_SECONDS)


def start_background_scanner():
    """Start the background scanner thread (called once on app boot)."""
    t = threading.Thread(target=_background_scan_loop, daemon=True)
    t.start()
    print("Background scanner thread launched")


# Start scanner when module loads (gunicorn will call this)
start_background_scanner()  # Multi-book fair value scanner (notifications only, no trading)
start_completed_props_sniper()  # Guaranteed markets: completed props, NHL tied totals (auto-trades)


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
        'moneyline_sports': list(MONEYLINE_SPORTS.keys()),
        'spread_sports': list(SPREAD_SPORTS.keys()),
        'total_sports': list(TOTAL_SPORTS.keys()),
        'player_prop_sports': list(PLAYER_PROP_SPORTS.keys()),
        'btts_sports': list(BTTS_SPORTS.keys()),
        'tennis_sports': list(TENNIS_SPORTS.keys()),
    })


@app.route('/api/edges')
def get_edges():
    with _scan_lock:
        cache = dict(_scan_cache)
    return jsonify({
        'edges': cache['edges'],
        'total_count': len(cache['edges']),
        'sports_scanned': cache['sports_scanned'],
        'sports_with_games': cache['sports_with_games'],
        'timestamp': cache['timestamp'],
        'scan_count': cache['scan_count'],
        'is_scanning': cache['is_scanning'],
    })


@app.route('/debug')
def debug_view():
    try:
        with _scan_lock:
            all_edges = list(_scan_cache['edges'])
            scanned = list(_scan_cache['sports_scanned'])
            active = list(_scan_cache['sports_with_games'])
            scan_ts = _scan_cache['timestamp']
            scan_count = _scan_cache['scan_count']
            is_scanning = _scan_cache['is_scanning']

        type_colors = {
            'Moneyline': '#e74c3c', 'Spread': '#3498db',
            'Total': '#e67e22', 'Player Prop': '#9b59b6',
            'BTTS': '#2ecc71',
        }

        html = f"""<!DOCTYPE html>
<html><head>
<title>Kalshi Edge Finder</title>
<meta http-equiv="refresh" content="30">
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
<div class="sub">Background Scanner: Scan #{scan_count} {'🔄 SCANNING...' if is_scanning else '✓ idle'} | Last: {scan_ts[:19] if scan_ts else 'waiting...'} | <a href="/props" style="color:#9b59b6">Props</a> | <a href="/orders" style="color:#3498db">Orders ({_order_tracker.get_open_count()})</a> | <a href="/history" style="color:#e67e22">History</a></div>
<div class="info">Scanning: {', '.join(scanned)} | Active: {', '.join(active) if active else 'None'}</div>
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
                live_badge = '<span class="badge" style="background:#e74c3c">LIVE</span>' if e.get('is_live') else ''
                html += f"""<div class="edge">
<div class="game">{e['game']}<span class="badge" style="background:{bc}">{mt}</span><span class="badge" style="background:#444">{e['sport']}</span>{live_badge}</div>
<div class="team">{e['team']}</div>
<div class="row"><span class="label">Kalshi:</span><span class="value">${e['kalshi_price']:.2f} -> ${e['kalshi_price_after_fees']:.4f} after fees ({e['kalshi_prob_after_fees']:.1f}%)</span></div>
<div class="row"><span class="label">Fair Value:</span><span class="value">{e['fanduel_opposite_team']} at {e['fanduel_opposite_odds']:.2f} ({e['fanduel_opposite_prob']:.1f}%)</span></div>
<div class="row"><span class="label">Edge:</span><span class="pos">{e['arbitrage_profit']:.2f}% +EV</span></div>
<div class="method">{e['recommendation']}</div></div>"""
        else:
            html += '<div class="no-edge"><p>Markets efficient right now</p><p style="color:#666;font-size:0.9em">Best times: live games, breaking news, early morning</p></div>'

        html += "</div></body></html>"
        return html

    except Exception as e:
        return f"<h1 style='color:red'>Error</h1><pre>{e}</pre>", 500


@app.route('/props')
def props_view():
    """Display FanDuel vs Kalshi player prop comparison table."""
    try:
        with _scan_lock:
            comparisons = list(_scan_cache.get('prop_comparisons', []))
            scan_ts = _scan_cache['timestamp']
            scan_count = _scan_cache['scan_count']
            cache_keys = list(_scan_cache.keys())

        print(f"PROPS ROUTE: {len(comparisons)} comparisons, scan #{scan_count}, cache keys={cache_keys}, cache id={id(_scan_cache)}")

        # Group by stat type for tab-like display
        stat_types = sorted(set(c['stat'] for c in comparisons)) if comparisons else []

        html = f"""<!DOCTYPE html>
<html><head>
<title>Player Props - FD vs Kalshi</title>
<meta http-equiv="refresh" content="60">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 20px; background: linear-gradient(135deg, #1a1a2e, #16213e); color: #eee; min-height: 100vh; }}
.container {{ max-width: 1400px; margin: 0 auto; }}
h1 {{ color: #00ff88; text-align: center; font-size: 2em; margin-bottom: 5px; }}
.sub {{ text-align: center; color: #aaa; margin-bottom: 20px; }}
.nav {{ text-align: center; margin-bottom: 15px; }}
.nav a {{ color: #3498db; text-decoration: none; margin: 0 12px; font-size: 0.95em; }}
.nav a:hover {{ color: #00ff88; }}
.tabs {{ display: flex; gap: 8px; margin-bottom: 15px; flex-wrap: wrap; }}
.tab {{ padding: 8px 16px; border-radius: 6px; cursor: pointer; background: #0f3460; color: #aaa; border: 1px solid #2a2a3e; font-size: 0.9em; }}
.tab.active {{ background: #00ff88; color: #1a1a2e; font-weight: bold; border-color: #00ff88; }}
.tab:hover {{ border-color: #00ff88; }}
.summary {{ text-align: center; padding: 10px; background: #0f3460; border-radius: 8px; margin-bottom: 15px; font-size: 0.95em; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.85em; }}
th {{ background: #0f3460; padding: 10px 8px; text-align: left; border-bottom: 2px solid #00ff88; white-space: nowrap; position: sticky; top: 0; }}
td {{ padding: 8px; border-bottom: 1px solid #2a2a3e; }}
tr:hover {{ background: rgba(0,255,136,0.05); }}
.pos {{ color: #00ff88; font-weight: bold; }}
.neg {{ color: #ff6b6b; }}
.neutral {{ color: #888; }}
.no-match {{ color: #666; font-style: italic; }}
.game-header {{ background: #0a1628; padding: 10px; font-weight: bold; color: #3498db; border-bottom: 2px solid #3498db; }}
.stat-section {{ display: none; }}
.stat-section.active {{ display: block; }}
</style>
</head><body><div class="container">
<h1>Player Props: FD vs Kalshi</h1>
<div class="sub">Scan #{scan_count} | Last: {scan_ts[:19] if scan_ts else 'waiting...'}</div>
<div class="nav"><a href="/debug">Edges</a> | <a href="/props"><strong>Props</strong></a> | <a href="/orders">Orders</a> | <a href="/history">History</a></div>
"""

        if not comparisons:
            html += '<div class="summary">No prop data yet. Waiting for background scan...</div>'
        else:
            matched = sum(1 for c in comparisons if c['fd_matched'])
            html += f'<div class="summary"><strong>{len(comparisons)}</strong> FD-matched props compared</div>'

            # Stat type tabs
            html += '<div class="tabs">'
            html += '<div class="tab active" onclick="showStat(\'all\')">All</div>'
            for st in stat_types:
                html += f'<div class="tab" onclick="showStat(\'{st}\')">{st}</div>'
            html += '</div>'

            # Sort by YES diff descending
            sorted_comps = sorted(
                comparisons,
                key=lambda c: c.get('diff_yes') or -999, reverse=True
            )

            # Build table
            html += '<table>'
            html += '<tr><th>Player</th><th>Stat</th><th>Threshold</th><th>Game</th>'
            html += '<th>FD Odds</th><th>FD Implied%</th>'
            html += '<th>Kalshi YES</th><th>Kalshi NO</th>'
            html += '<th>YES Diff</th><th>NO Diff</th></tr>'

            for c in sorted_comps:
                stat_class = f'stat-{c["stat"]}'
                fd_odds_str = f"{c['fd_american']:+d}" if c['fd_american'] else '—'
                fd_pct = f"{c['fd_implied']:.1f}%" if c['fd_implied'] else '—'
                k_yes = f"${c['kalshi_yes']:.2f} ({c['kalshi_yes_pct']:.0f}%)" if c['kalshi_yes'] else '—'
                k_no = f"${c['kalshi_no']:.2f} ({c['kalshi_no_pct']:.0f}%)" if c['kalshi_no'] else '—'

                # YES diff: positive = FD thinks more likely than Kalshi price (potential YES buy)
                if c['diff_yes'] is not None:
                    d = c['diff_yes']
                    cls = 'pos' if d > 2 else ('neg' if d < -2 else 'neutral')
                    yes_diff = f'<span class="{cls}">{d:+.1f}pp</span>'
                else:
                    yes_diff = '—'

                # NO diff: positive = FD thinks less likely than Kalshi implies (potential NO buy)
                if c['diff_no'] is not None:
                    d = c['diff_no']
                    cls = 'pos' if d > 2 else ('neg' if d < -2 else 'neutral')
                    no_diff = f'<span class="{cls}">{d:+.1f}pp</span>'
                else:
                    no_diff = '—'

                threshold_str = f"{c['threshold']}+"
                html += f'<tr class="stat-row {stat_class}" data-stat="{c["stat"]}">'
                html += f'<td><strong>{c["player"]}</strong></td>'
                html += f'<td>{c["stat"]}</td><td>{threshold_str}</td><td>{c["game"]}</td>'
                html += f'<td>{fd_odds_str}</td><td>{fd_pct}</td>'
                html += f'<td>{k_yes}</td><td>{k_no}</td>'
                html += f'<td>{yes_diff}</td><td>{no_diff}</td></tr>'

            html += '</table>'

        html += """
<script>
function showStat(stat) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    document.querySelectorAll('.stat-row').forEach(row => {
        if (stat === 'all' || row.dataset.stat === stat) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}
</script>"""
        html += "</div></body></html>"
        return Response(html, mimetype='text/html', headers={'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'})

    except Exception as e:
        import traceback
        return f"<h1 style='color:red'>Error</h1><pre>{traceback.format_exc()}</pre>", 500


def _lookup_team_name(abbrev: str, series_prefix: str = '') -> Optional[str]:
    """Look up full team name from abbreviation.
    Uses series_prefix (e.g. 'KXNHL', 'KXNBA') to search ONLY the correct sport's map,
    avoiding cross-sport collisions like PHI (76ers vs Flyers) or VAN (Canucks vs Vanderbilt).
    Only falls back to all maps if no series_prefix is provided."""
    if series_prefix:
        # ONLY search the matching sport's team map — do NOT fall back
        for sports_map in [MONEYLINE_SPORTS, SPREAD_SPORTS]:
            for series_key, v in sports_map.items():
                if series_key.startswith(series_prefix):
                    tmap = v[2] if len(v) > 2 else {}
                    if abbrev in tmap:
                        return tmap[abbrev]
        return None
    # No prefix: search all maps (used when sport is unknown)
    for sports_map in [MONEYLINE_SPORTS, SPREAD_SPORTS]:
        for _, v in sports_map.items():
            tmap = v[2] if len(v) > 2 else {}
            if abbrev in tmap:
                return tmap[abbrev]
    return None


def _get_sport_prefix(ticker: str) -> str:
    """Extract sport prefix from ticker for sport-aware team lookup.
    e.g. KXNHLGAME-... -> 'KXNHL', KXNCAAMBGAME-... -> 'KXNCAAMB'"""
    series_part = ticker.split('-')[0] if '-' in ticker else ticker
    for suffix in ['CHALLENGERMATCH', 'MATCH', 'BGAME', 'GAME', 'SPREAD', 'TOTALSETS', 'TOTAL', 'BTTS', 'PTS', 'REB', 'AST', '3PT', 'SAVES', 'SETWINNER', 'ANYSET']:
        if series_part.endswith(suffix):
            return series_part[:-len(suffix)]
    return series_part


def _parse_ticker_teams(ticker: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse ticker to extract team abbreviation, opponent abbreviation, and game name.
    e.g. KXNCAAMBGAME-26JAN31BALLTOL-TOL -> ('TOL', 'BALL', 'Ball St. at Toledo')
    Returns (team_abbrev, opp_abbrev, game_display) or (None, None, None)."""
    parts = ticker.split('-')
    if len(parts) < 3:
        return None, None, None

    sport_prefix = _get_sport_prefix(ticker)
    team_abbrev = parts[-1]
    game_part = parts[1]

    date_match = re.match(r'\d{2}[A-Z]{3}\d{2}', game_part)
    if not date_match:
        return team_abbrev, None, None

    teams_str = game_part[len(date_match.group(0)):]
    opp_abbrev = teams_str.replace(team_abbrev, '', 1).strip()
    if not opp_abbrev:
        return team_abbrev, None, None

    team_name = _lookup_team_name(team_abbrev, sport_prefix) or team_abbrev
    opp_name = _lookup_team_name(opp_abbrev, sport_prefix) or opp_abbrev

    return team_abbrev, opp_abbrev, f"{opp_name} at {team_name}"


def _describe_position(market_info: Optional[Dict], ticker: str, side: str) -> Tuple[str, str, str]:
    """Build human-readable bet description from market info and side.
    Returns (bet_description, market_type_tag, game_subtitle)."""
    if not market_info:
        return f"{side} · {ticker}", '', ''

    title = market_info.get('title', '') or ''
    subtitle = market_info.get('subtitle', '') or ''
    series_ticker = (market_info.get('series_ticker', '') or ticker).upper()

    # Determine market type from series ticker
    if 'MATCH' in series_ticker or 'CHALLENGERMATCH' in series_ticker:
        mtype = 'Tennis ML'
    elif 'SPREAD' in series_ticker:
        mtype = 'Spread'
    elif 'TOTAL' in series_ticker:
        mtype = 'Total'
    elif 'BTTS' in series_ticker:
        mtype = 'BTTS'
    elif 'GAME' in series_ticker or 'BGAME' in series_ticker:
        mtype = 'Moneyline'
    else:
        mtype = 'Prop' if ':' in title else 'Market'

    # Parse teams from ticker for moneyline/total/spread
    sport_prefix = _get_sport_prefix(ticker)
    team_abbrev, opp_abbrev, game_display = _parse_ticker_teams(ticker)

    if mtype == 'Tennis ML':
        # Tennis title: "Will Matteo Martineau win the Martineau vs Damm Jr : Qualification Round 1 match?"
        player = _extract_player_from_title(title)
        # Extract match name from title: "Martineau vs Damm Jr : Qualification Round 1"
        match_info = ''
        m = re.search(r'win the (.+?)(?:\s+match)?\?', title, re.IGNORECASE)
        if m:
            match_info = m.group(1).strip()
        if side == 'YES':
            return f"{player or title} ML", mtype, match_info
        else:
            # NO = opponent wins. Try to extract opponent from match info
            if match_info and ' vs ' in match_info:
                parts = match_info.split(' vs ')
                p1_last = parts[0].strip().split(':')[0].strip()
                p2_last = parts[1].strip().split(':')[0].strip()
                # Figure out which is ours
                if player and p1_last.lower() in player.lower():
                    return f"{p2_last} ML", mtype, match_info
                else:
                    return f"{p1_last} ML", mtype, match_info
            return f"NOT {player or title} ML", mtype, match_info

    elif mtype == 'Moneyline':
        # Kalshi API structure varies by sport:
        # - NBA/NHL: title = team name (e.g. "Boston Celtics"), subtitle = event (e.g. "Boston at Miami Winner?")
        # - NCAAMB/soccer: title = event question (e.g. "Marquette at Seton Hall Winner?"), subtitle = empty
        # Detect which case we're in by checking if title contains team separators
        title_has_teams = any(sep in (title or '') for sep in [' at ', ' vs ', ' vs. '])

        if subtitle:
            # subtitle has event name, title has team name
            event_source = subtitle
            contract_team_title = title
        elif title_has_teams:
            # title IS the event name (NCAAMB/soccer pattern), no separate team name
            event_source = title
            contract_team_title = None
        else:
            event_source = ''
            contract_team_title = title

        event_name = event_source.replace(' Winner?', '').replace(' winner?', '') if event_source else ''
        game_line = event_name or game_display

        # Parse event name into two teams for name resolution
        event_teams = []
        for sep in [' at ', ' vs ', ' vs. ']:
            if sep in event_name:
                event_teams = [t.strip() for t in event_name.split(sep)]
                break

        def _match_abbrev_to_team(abbrev: str, teams: list) -> Optional[str]:
            """Match a ticker abbreviation to one of the event team names.
            Uses multiple strategies: initials, prefix, word-start, consonant matching."""
            if not abbrev or not teams:
                return None
            ab = abbrev.lower()
            best_match = None
            best_score = 0
            for t in teams:
                tl = t.lower()
                words = tl.split()
                initials = ''.join(w[0] for w in words if w)
                score = 0
                # Exact initials match (e.g. SH -> Seton Hall)
                if ab == initials:
                    score = 10
                # Prefix of full name (e.g. MARQ -> Marquette, TOL -> Toledo)
                elif len(ab) >= 3 and tl.replace(' ', '').startswith(ab):
                    score = 9
                # Prefix of first word (e.g. VAN -> Vanderbilt)
                elif len(ab) >= 3 and words and words[0].startswith(ab):
                    score = 8
                # Abbreviation starts with initials (e.g. SHU -> Seton Hall University)
                elif len(ab) > len(initials) and ab.startswith(initials):
                    score = 7
                # First word starts with abbreviation letters
                elif len(ab) >= 2 and any(w.startswith(ab) for w in words):
                    score = 6
                if score > best_score:
                    best_score = score
                    best_match = t
            return best_match

        if side == 'YES':
            # YES on this contract = betting this team wins
            team_name = _lookup_team_name(team_abbrev, sport_prefix) if team_abbrev else None
            if not team_name and event_teams and team_abbrev:
                # No team map — match ticker abbreviation to event team
                team_name = _match_abbrev_to_team(team_abbrev, event_teams)
                if not team_name and contract_team_title:
                    # Fall back to matching contract title against event teams
                    ctl = contract_team_title.lower()
                    for et in event_teams:
                        if et.lower() in ctl or ctl in et.lower():
                            team_name = et
                            break
            bet_name = team_name or contract_team_title or title or team_abbrev or ticker
            bet_name = bet_name.replace(' Winner?', '').replace(' winner?', '')
            return f"{bet_name} ML", mtype, game_line

        elif side == 'NO':
            # NO on this contract = opponent wins. Try to resolve opponent name.
            opp_name = _lookup_team_name(opp_abbrev, sport_prefix) if opp_abbrev else None
            if opp_name:
                return f"{opp_name} ML", mtype, game_line
            # No team map — figure out which team the contract is for, then pick the other
            if event_teams and len(event_teams) == 2:
                contract_team = _match_abbrev_to_team(team_abbrev, event_teams)
                if contract_team:
                    opp = event_teams[1] if contract_team == event_teams[0] else event_teams[0]
                    return f"{opp} ML", mtype, game_line
                # Last resort: try matching contract_team_title
                if contract_team_title:
                    ctl = contract_team_title.lower()
                    t0_match = event_teams[0].lower() in ctl or ctl in event_teams[0].lower()
                    opp = event_teams[1] if t0_match else event_teams[0]
                    return f"{opp} ML", mtype, game_line
                # If we still can't figure it out, use opp_abbrev from ticker
                if opp_abbrev:
                    opp = _match_abbrev_to_team(opp_abbrev, event_teams) or opp_abbrev
                    return f"{opp} ML", mtype, game_line
            return f"NOT {title} ML" if title else f"NO · {ticker}", mtype, game_line

    elif mtype == 'Spread':
        # title from Kalshi is usually like "Team wins by X+"
        if side == 'YES':
            return title or f"YES · {ticker}", mtype, game_display or subtitle
        else:
            return f"NOT {title}" if title else f"NO · {ticker}", mtype, game_display or subtitle

    elif mtype == 'Total':
        # Extract line from ticker: KXNBATOTAL-26JAN31SASCHA-231 -> 231 -> 231.5
        parts = ticker.split('-')
        line_str = parts[-1] if len(parts) >= 3 else ''
        try:
            line = float(line_str) + 0.5
            line_display = f"{line:g}"
        except ValueError:
            line_display = subtitle or title

        # Build game name from ticker teams
        if len(parts) >= 3:
            gp = parts[1]
            dm = re.match(r'\d{2}[A-Z]{3}\d{2}', gp)
            if dm:
                teams_str = gp[len(dm.group(0)):]
                # For totals, teams_str is like "SASCHA" - split into two team abbrevs
                # Try all known abbrevs to split
                game_name = None
                for length in range(2, len(teams_str) - 1):
                    t1 = teams_str[:length]
                    t2 = teams_str[length:]
                    n1 = _lookup_team_name(t1, sport_prefix)
                    n2 = _lookup_team_name(t2, sport_prefix)
                    if n1 and n2:
                        game_name = f"{n1} at {n2}"
                        break
                if not game_name:
                    game_name = game_display or subtitle
            else:
                game_name = subtitle
        else:
            game_name = subtitle

        if side == 'YES':
            return f"Over {line_display}", mtype, game_name or ''
        else:
            return f"Under {line_display}", mtype, game_name or ''

    elif mtype == 'BTTS':
        if side == 'YES':
            return "Both Teams Score", mtype, game_display or subtitle or title
        else:
            return "Both Teams Don't Score", mtype, game_display or subtitle or title

    elif ':' in title:
        # Player prop like "Stephon Castle: 8+"
        if side == 'YES':
            return title, 'Prop', game_display or subtitle
        else:
            return f"NOT {title}", 'Prop', game_display or subtitle

    # Fallback
    return f"{side} · {title or ticker}", mtype, subtitle


@app.route('/orders')
def orders_view():
    try:
        kalshi = KalshiAPI(KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY)
        balance_data = kalshi.get_balance()
        balance_dollars = balance_data.get('balance', 0) / 100 if balance_data else 0
        portfolio_value = balance_data.get('portfolio_value', 0) / 100 if balance_data else 0

        # Pull live positions from Kalshi API
        positions = kalshi.get_positions()
        active_positions = [p for p in positions if p.get('position', 0) != 0]

        # Fetch market details for each position (for human-readable names)
        market_cache = {}
        for pos in active_positions:
            ticker = pos.get('ticker', '')
            if ticker and ticker not in market_cache:
                market_cache[ticker] = kalshi.get_market(ticker)
                time.sleep(0.2)

        html = f"""<!DOCTYPE html>
<html><head>
<title>Kalshi Orders</title>
<meta http-equiv="refresh" content="30">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 20px; background: linear-gradient(135deg, #1a1a2e, #16213e); color: #eee; min-height: 100vh; }}
.container {{ max-width: 1200px; margin: 0 auto; }}
h1 {{ color: #00ff88; text-align: center; font-size: 2em; margin-bottom: 5px; }}
.nav {{ text-align: center; margin-bottom: 15px; }}
.nav a {{ color: #00ff88; text-decoration: none; margin: 0 15px; }}
.balance {{ text-align: center; padding: 15px; background: #0f3460; border-radius: 8px; margin-bottom: 20px; }}
.balance span {{ margin: 0 20px; }}
.order {{ background: #16213e; padding: 15px; margin: 10px 0; border-radius: 10px; border-left: 4px solid #3498db; }}
.bet-name {{ font-weight: bold; color: #00ff88; font-size: 1.2em; margin-bottom: 4px; }}
.bet-sub {{ font-size: 0.85em; color: #888; margin-bottom: 8px; }}
.badge {{ display: inline-block; padding: 3px 8px; border-radius: 3px; font-size: 0.7em; font-weight: bold; color: white; margin-left: 6px; vertical-align: middle; }}
.row {{ display: flex; justify-content: space-between; margin: 4px 0; padding: 4px 0; border-bottom: 1px solid #2a2a3e; }}
.label {{ color: #aaa; }} .value {{ font-weight: 600; }}
.pos {{ color: #00ff88; }} .neg {{ color: #e74c3c; }}
.no-orders {{ text-align: center; padding: 50px 20px; color: #888; }}
.summary {{ text-align: center; padding: 15px; background: #0f3460; border-radius: 8px; margin-top: 15px; }}
.summary span {{ margin: 0 20px; }}
</style></head><body><div class="container">
<h1>Kalshi Orders</h1>
<div class="nav"><a href="/debug">Edge Scanner</a> | <a href="/orders">Orders</a> | <a href="/history">History</a></div>
<div class="balance">
<span>Balance: <strong style="color:#00ff88">${balance_dollars:.2f}</strong></span>
<span>Portfolio: <strong style="color:#3498db">${portfolio_value:.2f}</strong></span>
<span>Positions: <strong>{len(active_positions)}</strong> / {MAX_POSITIONS}</span>
<span>Auto-trade: <strong style="color:{'#00ff88' if AUTO_TRADE_ENABLED else '#e74c3c'}">{'ON' if AUTO_TRADE_ENABLED else 'OFF'}</strong></span>
</div>"""

        type_colors = {
            'Moneyline': '#e74c3c', 'Spread': '#3498db', 'Total': '#e67e22',
            'Prop': '#9b59b6', 'BTTS': '#2ecc71', 'Tennis ML': '#1abc9c', 'Completed Prop': '#f39c12', 'Market': '#95a5a6',
        }

        if active_positions:
            total_cost = 0
            total_pnl = 0
            for pos in active_positions:
                ticker = pos.get('ticker', '?')
                position = pos.get('position', 0)
                side = 'YES' if position > 0 else 'NO'
                contracts = abs(position)
                market_exposure = pos.get('market_exposure', 0)

                if contracts > 0:
                    avg_price = abs(market_exposure) / contracts / 100 if market_exposure else 0
                else:
                    avg_price = 0

                cost_dollars = abs(market_exposure) / 100 if market_exposure else 0
                payout = contracts
                potential_profit = payout - cost_dollars
                american = prob_to_american(avg_price) if 0 < avg_price < 1 else 'N/A'
                pnl_class = 'pos' if potential_profit >= 0 else 'neg'

                total_cost += cost_dollars
                total_pnl += potential_profit

                # Get human-readable description
                market_info = market_cache.get(ticker)
                bet_desc, mtype, bet_sub = _describe_position(market_info, ticker, side)
                mtype_color = type_colors.get(mtype, '#95a5a6')
                sub_line = (bet_sub + ' · ') if bet_sub else ''

                html += f'<div class="order">'
                html += f'<div class="bet-name">{bet_desc}<span class="badge" style="background:{mtype_color}">{mtype}</span></div>'
                html += f'<div class="bet-sub">{sub_line}{ticker}</div>'
                html += f'<div class="row"><span class="label">Contracts:</span><span class="value">{contracts}</span></div>'
                html += f'<div class="row"><span class="label">Avg price:</span><span class="value">{avg_price*100:.1f}¢ ({american})</span></div>'
                html += f'<div class="row"><span class="label">Cost:</span><span class="value">${cost_dollars:.2f}</span></div>'
                html += f'<div class="row"><span class="label">Payout if right:</span><span class="value">${payout:.2f}</span></div>'
                html += f'<div class="row"><span class="label">Potential profit:</span><span class="{pnl_class}">${potential_profit:.2f}</span></div>'
                html += '</div>'

            pnl_cls = 'pos' if total_pnl >= 0 else 'neg'
            html += f'<div class="summary">'
            html += f'<span>Total cost: <strong>${total_cost:.2f}</strong></span>'
            html += f'<span>Total payout: <strong>${total_cost + total_pnl:.2f}</strong></span>'
            html += f'<span>Potential P&L: <strong class="{pnl_cls}">${total_pnl:.2f}</strong></span>'
            html += '</div>'
        else:
            html += '<div class="no-orders"><p>No open positions</p><p style="color:#666;font-size:0.9em">Positions from your Kalshi portfolio will appear here</p></div>'

        html += "</div></body></html>"
        return html

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"<h1 style='color:red'>Error</h1><pre>{e}</pre>", 500


@app.route('/history')
def history_page():
    """Show settled bets history with P&L and ROI."""
    try:
        kalshi = KalshiAPI(KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY)
        balance_data = kalshi.get_balance()
        balance_dollars = balance_data.get('balance', 0) / 100 if balance_data else 0

        settlements = kalshi.get_settlements()

        # Only show settlements from Jan 31, 2026 onwards (when bot started)
        bot_start = '2026-01-31T00:00:00Z'
        settlements = [s for s in settlements if (s.get('settled_time', '') or '') >= bot_start]

        # Fetch market details for readable names (batch, with caching)
        market_cache = {}
        for s in settlements[:100]:  # Limit API calls
            ticker = s.get('ticker', '')
            if ticker and ticker not in market_cache:
                market_cache[ticker] = kalshi.get_market(ticker)
                time.sleep(0.15)

        type_colors = {
            'Moneyline': '#e74c3c', 'Spread': '#3498db', 'Total': '#e67e22',
            'Prop': '#9b59b6', 'BTTS': '#2ecc71', 'Tennis ML': '#1abc9c', 'Completed Prop': '#f39c12', 'Market': '#95a5a6',
        }

        # Process settlements
        rows = []
        total_cost = 0
        total_revenue = 0
        total_fees = 0
        wins = 0
        losses = 0

        for s in settlements:
            ticker = s.get('ticker', '')
            result = s.get('market_result', '')
            yes_count = s.get('yes_count', 0)
            no_count = s.get('no_count', 0)
            yes_cost = s.get('yes_total_cost', 0) / 100  # cents -> dollars
            no_cost = s.get('no_total_cost', 0) / 100
            revenue = s.get('revenue', 0) / 100
            fee = float(s.get('fee_cost', '0') or '0')
            settled_time = s.get('settled_time', '')

            cost = yes_cost + no_cost
            profit = revenue - cost
            total_cost += cost
            total_revenue += revenue
            total_fees += fee

            if profit > 0:
                wins += 1
            elif profit < 0:
                losses += 1

            # Determine which side we held
            if yes_count > 0 and no_count == 0:
                side = 'YES'
                contracts = yes_count
            elif no_count > 0 and yes_count == 0:
                side = 'NO'
                contracts = no_count
            else:
                side = 'YES' if yes_cost >= no_cost else 'NO'
                contracts = max(yes_count, no_count)

            # Did we win?
            won = (side == 'YES' and result == 'yes') or (side == 'NO' and result == 'no')

            # Human-readable name
            market_info = market_cache.get(ticker)
            bet_desc, mtype, bet_sub = _describe_position(market_info, ticker, side)
            mtype_color = type_colors.get(mtype, '#95a5a6')

            # Parse settled time
            try:
                st = datetime.fromisoformat(settled_time.replace('Z', '+00:00'))
                time_display = st.strftime('%b %d %I:%M %p')
            except Exception:
                time_display = settled_time[:16] if settled_time else '?'

            rows.append({
                'bet_desc': bet_desc, 'mtype': mtype, 'mtype_color': mtype_color,
                'bet_sub': bet_sub, 'ticker': ticker, 'contracts': contracts,
                'cost': cost, 'revenue': revenue, 'profit': profit, 'fee': fee,
                'won': won, 'result': result, 'time_display': time_display,
            })

        total_profit = total_revenue - total_cost
        roi = (total_profit / total_cost * 100) if total_cost > 0 else 0
        total_bets = wins + losses

        html = f"""<!DOCTYPE html>
<html><head>
<title>Kalshi History</title>
<meta http-equiv="refresh" content="60">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 20px; background: linear-gradient(135deg, #1a1a2e, #16213e); color: #eee; min-height: 100vh; }}
.container {{ max-width: 1200px; margin: 0 auto; }}
h1 {{ color: #00ff88; text-align: center; font-size: 2em; margin-bottom: 5px; }}
.nav {{ text-align: center; margin-bottom: 15px; }}
.nav a {{ color: #00ff88; text-decoration: none; margin: 0 15px; }}
.stats {{ display: flex; justify-content: center; gap: 15px; flex-wrap: wrap; padding: 15px; background: #0f3460; border-radius: 8px; margin-bottom: 20px; }}
.stat {{ text-align: center; padding: 0 15px; }}
.stat-val {{ font-size: 1.4em; font-weight: bold; }}
.stat-label {{ font-size: 0.75em; color: #888; margin-top: 2px; }}
.row {{ background: #16213e; padding: 12px 15px; margin: 6px 0; border-radius: 8px; display: flex; align-items: center; gap: 15px; }}
.row-win {{ border-left: 4px solid #00ff88; }}
.row-loss {{ border-left: 4px solid #e74c3c; }}
.row-void {{ border-left: 4px solid #666; }}
.bet-info {{ flex: 1; min-width: 0; }}
.bet-name {{ font-weight: bold; font-size: 1.05em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.bet-sub {{ font-size: 0.8em; color: #888; margin-top: 2px; }}
.badge {{ display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 0.65em; font-weight: bold; color: white; margin-left: 6px; vertical-align: middle; }}
.nums {{ text-align: right; white-space: nowrap; }}
.profit {{ font-weight: bold; font-size: 1.1em; }}
.pos {{ color: #00ff88; }} .neg {{ color: #e74c3c; }}
.detail {{ font-size: 0.8em; color: #888; }}
.time {{ font-size: 0.75em; color: #666; min-width: 100px; text-align: right; }}
.empty {{ text-align: center; padding: 50px 20px; color: #888; }}
</style></head><body><div class="container">
<h1>Bet History</h1>
<div class="nav"><a href="/debug">Edge Scanner</a> | <a href="/orders">Orders</a> | <a href="/history">History</a></div>

<div class="stats">
<div class="stat"><div class="stat-val {'pos' if total_profit >= 0 else 'neg'}">${total_profit:+.2f}</div><div class="stat-label">Total P&L</div></div>
<div class="stat"><div class="stat-val {'pos' if roi >= 0 else 'neg'}">{roi:+.1f}%</div><div class="stat-label">ROI</div></div>
<div class="stat"><div class="stat-val">{total_bets}</div><div class="stat-label">Settled Bets</div></div>
<div class="stat"><div class="stat-val pos">{wins}</div><div class="stat-label">Wins</div></div>
<div class="stat"><div class="stat-val neg">{losses}</div><div class="stat-label">Losses</div></div>
<div class="stat"><div class="stat-val">{wins}/{total_bets if total_bets else 1}</div><div class="stat-label">Win Rate</div></div>
<div class="stat"><div class="stat-val">${total_cost:.2f}</div><div class="stat-label">Total Wagered</div></div>
<div class="stat"><div class="stat-val">${total_fees:.2f}</div><div class="stat-label">Total Fees</div></div>
<div class="stat"><div class="stat-val">${balance_dollars:.2f}</div><div class="stat-label">Balance</div></div>
</div>
"""

        if rows:
            for r in rows:
                result_class = 'row-win' if r['won'] else ('row-void' if r['result'] == 'void' else 'row-loss')
                result_icon = '+' if r['won'] else ('-' if r['result'] != 'void' else '~')
                pnl_class = 'pos' if r['profit'] >= 0 else 'neg'
                sub_line = (r['bet_sub'] + ' &middot; ') if r['bet_sub'] else ''

                html += f"""<div class="row {result_class}">
<div class="bet-info">
<div class="bet-name">{r['bet_desc']}<span class="badge" style="background:{r['mtype_color']}">{r['mtype']}</span></div>
<div class="bet-sub">{sub_line}{r['ticker']}</div>
</div>
<div class="nums">
<div class="profit {pnl_class}">{result_icon}${abs(r['profit']):.2f}</div>
<div class="detail">{r['contracts']}x &middot; cost ${r['cost']:.2f} &middot; paid ${r['revenue']:.2f}</div>
</div>
<div class="time">{r['time_display']}</div>
</div>"""
        else:
            html += '<div class="empty"><p>No settled bets yet</p><p style="color:#666;font-size:0.9em">Settled positions will appear here</p></div>'

        html += "</div></body></html>"
        return html

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"<h1 style='color:red'>Error</h1><pre>{e}</pre>", 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
