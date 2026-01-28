"""
Kalshi Edge Finder - CATEGORY-BASED VERSION
Uses Kalshi's series/category filters to find NBA markets
"""

from flask import Flask, render_template, jsonify
import requests
import os
from datetime import datetime
from typing import Dict, List, Optional
import threading
import time

app = Flask(__name__)

# Configuration
ODDS_API_KEY = os.getenv('ODDS_API_KEY')
KALSHI_API_KEY = os.getenv('KALSHI_API_KEY')
MIN_EDGE = float(os.getenv('MIN_EDGE', '10.0'))
BET_AMOUNT = float(os.getenv('BET_AMOUNT', '10.0'))

# Global storage
current_edges = []
last_scan_time = None
scan_in_progress = False
debug_info = {}


class OddsConverter:
    """Convert between different odds formats"""
    
    @staticmethod
    def american_to_implied_prob(american_odds: int or float) -> float:
        """Convert American odds to implied probability"""
        american_odds = float(american_odds)
        if american_odds > 0:
            return 100 / (american_odds + 100)
        else:
            return abs(american_odds) / (abs(american_odds) + 100)
    
    @staticmethod
    def calculate_edge(true_prob: float, market_price: float) -> float:
        """Calculate edge percentage"""
        if market_price == 0:
            return 0
        return (true_prob / market_price - 1) * 100


class KalshiAPI:
    """Wrapper for Kalshi API with category/series support"""
    
    BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
    DEMO_URL = "https://demo-api.kalshi.co/trade-api/v2"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.base_url = self.DEMO_URL if not api_key else self.BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
    def check_exchange_status(self) -> bool:
        """Check if Kalshi exchange is open for trading"""
        try:
            url = f"{self.base_url}/exchange/status"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            trading_active = data.get('trading_active', False)
            print(f"Kalshi exchange trading_active: {trading_active}")
            return trading_active
        except Exception as e:
            print(f"Could not check exchange status: {e}")
            return True  # Assume it's open if we can't check
        
    def get_series(self) -> List[Dict]:
        """Get all available series/categories"""
        try:
            url = f"{self.base_url}/series"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('series', [])
        except Exception as e:
            print(f"Error fetching series: {e}")
            return []
    
    def get_markets_by_series(self, series_ticker: str, limit: int = 100) -> List[Dict]:
        """Get markets filtered by series/category"""
        try:
            url = f"{self.base_url}/markets"
            params = {
                'series_ticker': series_ticker,
                'limit': limit,
                'status': 'open'
            }
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('markets', [])
        except Exception as e:
            print(f"Error fetching markets for series {series_ticker}: {e}")
            return []
    
    def get_markets(self, limit: int = 200, status: str = "open") -> List[Dict]:
        """Fetch active markets from Kalshi - only returns tradeable markets"""
        try:
            url = f"{self.base_url}/markets"
            params = {
                'limit': limit,
                'status': status,
                'with_nested_markets': 'false'
            }
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            markets = data.get('markets', [])
            
            # Filter to only markets where trading is actually active
            tradeable_markets = []
            for market in markets:
                # Check if market can be traded right now
                if market.get('status') == 'open' and market.get('can_close_early', True):
                    # Additional check: has the close_time passed?
                    close_time = market.get('close_time')
                    if close_time:
                        try:
                            from datetime import datetime
                            close_dt = datetime.fromisoformat(close_time.replace('Z', '+00:00'))
                            now = datetime.now(close_dt.tzinfo)
                            if close_dt > now:  # Market hasn't closed yet
                                tradeable_markets.append(market)
                        except:
                            # If we can't parse time, include it
                            tradeable_markets.append(market)
                    else:
                        tradeable_markets.append(market)
            
            return tradeable_markets
        except Exception as e:
            print(f"Error fetching Kalshi markets: {e}")
            return []
    
    def get_orderbook(self, ticker: str) -> Optional[Dict]:
        """Get orderbook for a specific market"""
        try:
            url = f"{self.base_url}/markets/{ticker}/orderbook"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return None
    
    def find_basketball_series(self) -> List[str]:
        """Find all basketball-related series"""
        all_series = self.get_series()
        basketball_series = []
        
        basketball_keywords = ['basketball', 'nba', 'ncaa', 'college basketball', 
                               'pro basketball', 'hoops']
        
        for series in all_series:
            title = series.get('title', '').lower()
            ticker = series.get('ticker', '')
            
            if any(keyword in title for keyword in basketball_keywords):
                basketball_series.append(ticker)
                print(f"Found basketball series: {series.get('title')} ({ticker})")
        
        return basketball_series
    
    def get_all_basketball_markets(self) -> List[Dict]:
        """Get all basketball markets using series filters"""
        basketball_series = self.find_basketball_series()
        
        all_markets = []
        for series_ticker in basketball_series:
            markets = self.get_markets_by_series(series_ticker, limit=100)
            all_markets.extend(markets)
            print(f"Found {len(markets)} markets in series {series_ticker}")
        
        # Also try keyword search as backup
        keyword_markets = self.get_markets(limit=200)
        basketball_keywords = ['lakers', 'warriors', 'celtics', 'nba', 'basketball',
                              'bulls', 'heat', 'knicks', 'nets', 'sixers', '76ers']
        
        for market in keyword_markets:
            title = market.get('title', '').lower()
            if any(keyword in title for keyword in basketball_keywords):
                # Avoid duplicates
                if not any(m.get('ticker') == market.get('ticker') for m in all_markets):
                    all_markets.append(market)
        
        return all_markets


class TheOddsAPI:
    """Wrapper for The Odds API - NBA + NCAA"""
    
    BASE_URL = "https://api.the-odds-api.com/v4"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.session = requests.Session()
    
    def get_basketball_odds(self) -> Dict[str, Dict]:
        """Get NBA + NCAA basketball odds"""
        if not self.api_key:
            return self._get_mock_odds()
        
        all_odds = {}
        
        # Get NBA
        print("Fetching NBA odds...")
        nba_odds = self._get_sport_odds('basketball_nba')
        all_odds.update(nba_odds)
        
        # Get NCAA Basketball
        print("Fetching NCAA Basketball odds...")
        ncaa_odds = self._get_sport_odds('basketball_ncaab')
        all_odds.update(ncaa_odds)
        
        return all_odds
    
    def _get_sport_odds(self, sport: str) -> Dict[str, Dict]:
        """Get odds for a specific sport"""
        sport_odds = {}
        
        # Get different market types
        market_types = ['h2h', 'spreads', 'totals']
        
        for market_type in market_types:
            url = f"{self.BASE_URL}/sports/{sport}/odds"
            params = {
                'apiKey': self.api_key,
                'regions': 'us',
                'markets': market_type,
                'bookmakers': 'fanduel',
                'oddsFormat': 'american'
            }
            
            try:
                response = self.session.get(url, params=params, timeout=10)
                response.raise_for_status()
                games = response.json()
                
                print(f"  {sport} {market_type}: {len(games)} games")
                
                for game in games:
                    home = game.get('home_team', '')
                    away = game.get('away_team', '')
                    
                    bookmakers = game.get('bookmakers', [])
                    for book in bookmakers:
                        if book.get('key') != 'fanduel':
                            continue
                        
                        markets = book.get('markets', [])
                        for market in markets:
                            outcomes = market.get('outcomes', [])
                            
                            for outcome in outcomes:
                                team = outcome.get('name', '')
                                price = outcome.get('price')
                                point = outcome.get('point')
                                
                                # Create searchable keys
                                keys = self._generate_keys(team, home, away, market_type, point)
                                
                                for key in keys:
                                    sport_odds[key] = {
                                        'odds': price,
                                        'type': market_type,
                                        'team': team,
                                        'home': home,
                                        'away': away,
                                        'matchup': f"{away} @ {home}",
                                        'point': point
                                    }
                
                time.sleep(0.3)  # Rate limiting
                
            except Exception as e:
                print(f"Error fetching {sport} {market_type}: {e}")
        
        return sport_odds
    
    def _generate_keys(self, team: str, home: str, away: str, market_type: str, point) -> List[str]:
        """Generate multiple key variations for matching"""
        keys = [
            team,
            team.lower(),
            f"{team} Win",
            f"{team} to win",
        ]
        
        # Add matchup variations
        if team == home:
            keys.extend([
                f"{away} at {home}",
                f"{away} @ {home}",
                f"{home} vs {away}",
            ])
        else:
            keys.extend([
                f"{home} at {away}",
                f"{home} @ {away}",
                f"{away} vs {home}",
            ])
        
        # Add spread/total specific keys
        if point:
            keys.extend([
                f"{team} {point:+.1f}",
                f"{team} spread {point:+.1f}",
                f"{team} {abs(point)}"
            ])
        
        return keys
    
    def _get_mock_odds(self) -> Dict[str, Dict]:
        """Mock odds for testing"""
        return {
            "Lakers": {'odds': -150, 'type': 'h2h', 'team': 'Lakers', 'matchup': 'Celtics @ Lakers'},
            "Celtics": {'odds': +130, 'type': 'h2h', 'team': 'Celtics', 'matchup': 'Celtics @ Lakers'},
        }


def match_events(kalshi_title: str, fanduel_odds: Dict) -> Optional[Dict]:
    """Match Kalshi event with FanDuel odds using fuzzy matching"""
    
    kalshi_lower = kalshi_title.lower()
    
    # Direct match first
    for fd_key, fd_data in fanduel_odds.items():
        if fd_key.lower() in kalshi_lower or kalshi_lower in fd_key.lower():
            return fd_data
    
    # Extract team names and match
    kalshi_words = set(kalshi_lower.split())
    
    best_match = None
    best_overlap = 0
    
    for fd_key, fd_data in fanduel_odds.items():
        fd_words = set(fd_key.lower().split())
        overlap = len(kalshi_words & fd_words)
        
        if overlap > best_overlap and overlap >= 2:
            best_overlap = overlap
            best_match = fd_data
    
    return best_match


def find_edges() -> tuple[List[Dict], Dict]:
    """Find basketball betting edges"""
    global scan_in_progress
    
    scan_in_progress = True
    edges = []
    debug = {
        'kalshi_total_markets': 0,
        'kalshi_basketball_markets': 0,
        'kalshi_series_found': [],
        'kalshi_sample_markets': [],
        'fanduel_total_odds': 0,
        'fanduel_sample_matchups': [],
        'matches_found': 0,
        'match_details': [],
        'errors': []
    }
    
    try:
        converter = OddsConverter()
        kalshi = KalshiAPI(api_key=KALSHI_API_KEY)
        odds_api = TheOddsAPI(api_key=ODDS_API_KEY)
        
        # Check if exchange is even open
        kalshi.check_exchange_status()
        
        # Get FanDuel basketball odds
        print("\n=== FETCHING FANDUEL ODDS ===")
        fanduel_odds = odds_api.get_basketball_odds()
        debug['fanduel_total_odds'] = len(fanduel_odds)
        
        # Get unique matchups for debug
        matchups = list(set([v.get('matchup', '') for v in fanduel_odds.values() if v.get('matchup')]))
        debug['fanduel_sample_matchups'] = matchups[:15]
        
        # Get Kalshi basketball markets using series
        print("\n=== FETCHING KALSHI MARKETS ===")
        basketball_series = kalshi.find_basketball_series()
        debug['kalshi_series_found'] = basketball_series
        
        markets = kalshi.get_all_basketball_markets()
        debug['kalshi_basketball_markets'] = len(markets)
        
        # Filter to only open markets
        open_markets = [m for m in markets if m.get('status') == 'open']
        debug['kalshi_open_markets'] = len(open_markets)
        debug['kalshi_sample_markets'] = [m.get('title', '') for m in open_markets[:15]]
        
        print(f"\nFound {len(markets)} Kalshi basketball markets")
        print(f"Found {len(open_markets)} OPEN markets")
        print(f"Found {len(fanduel_odds)} FanDuel odds\n")
        
        # Match and find edges
        for market in open_markets:
            ticker = market.get('ticker', '')
            title = market.get('title', '')
            close_time = market.get('close_time', '')
            
            # Get orderbook
            orderbook = kalshi.get_orderbook(ticker)
            if not orderbook:
                continue
            
            orderbook_data = orderbook.get('orderbook', {})
            yes_asks = orderbook_data.get('yes', [])
            no_asks = orderbook_data.get('no', [])
            
            # DEBUG: Log what we got
            is_bulls_pacers = 'chicago' in title.lower() and 'indiana' in title.lower()
            
            if title and (is_bulls_pacers or 'austin peay' in title.lower() or 'kansas state' in title.lower() or 'bucknell' in title.lower()):
                print(f"\n🔍 DEBUG MARKET: {title}")
                print(f"   Ticker: {ticker}")
                print(f"   Close time: {close_time}")
                print(f"   YES asks: {yes_asks[:3] if yes_asks else 'None'}")
                print(f"   NO asks: {no_asks[:3] if no_asks else 'None'}")
            
            # Need either YES asks or NO bids to get YES probability
            if not yes_asks and not no_asks:
                continue
            
            # Get best YES price (what it costs to buy YES)
            kalshi_price = None
            
            if yes_asks:
                # Best ask on YES side (lowest price to buy YES)
                try:
                    # Orderbook format might be: [[price_cents, quantity], ...]
                    best_yes_ask = min(yes_asks, key=lambda x: x[0])
                    price_cents = best_yes_ask[0]
                    kalshi_price = price_cents / 100  # Convert cents to dollars
                    
                    if title and ('austin peay' in title.lower() or 'kansas state' in title.lower()):
                        print(f"   ✓ YES price: {price_cents} cents = ${kalshi_price}")
                except Exception as e:
                    print(f"   ❌ Error parsing YES asks: {e}")
                    continue
                    
            elif no_asks:
                # If no YES asks, infer from NO side
                try:
                    best_no_ask = min(no_asks, key=lambda x: x[0])
                    no_price_cents = best_no_ask[0]
                    kalshi_price = 1.0 - (no_price_cents / 100)
                    
                    if title and ('austin peay' in title.lower() or 'kansas state' in title.lower()):
                        print(f"   ✓ NO price: {no_price_cents} cents, YES inferred: ${kalshi_price}")
                except Exception as e:
                    print(f"   ❌ Error parsing NO asks: {e}")
                    continue
            
            if not kalshi_price:
                continue
                
            # Filter unrealistic prices but log them
            if kalshi_price <= 0.01 or kalshi_price >= 0.99:
                if is_bulls_pacers or (title and ('austin peay' in title.lower() or 'kansas state' in title.lower())):
                    print(f"   ⚠️ SKIPPED: Price ${kalshi_price} too extreme (no liquidity?)")
                continue
            
            kalshi_prob = kalshi_price
            
            # Match with FanDuel
            matched = match_events(title, fanduel_odds)
            
            if matched:
                debug['matches_found'] += 1
                
                fanduel_odds_value = matched['odds']
                fanduel_prob = converter.american_to_implied_prob(fanduel_odds_value)
                edge = converter.calculate_edge(fanduel_prob, kalshi_prob)
                
                match_info = {
                    'kalshi_title': title,
                    'kalshi_price': round(kalshi_price, 2),
                    'fanduel_odds': fanduel_odds_value,
                    'fanduel_matchup': matched.get('matchup', ''),
                    'market_type': matched.get('type', 'unknown'),
                    'edge': round(edge, 2)
                }
                debug['match_details'].append(match_info)
                
                print(f"✓ MATCH: {title[:50]}... | Edge: {edge:.1f}%")
                
                if edge >= MIN_EDGE:
                    payout_if_win = 1.0 - kalshi_price
                    ev = fanduel_prob * payout_if_win - (1 - fanduel_prob) * kalshi_price
                    ev_dollars = ev * BET_AMOUNT
                    
                    edges.append({
                        'event_name': title,
                        'kalshi_market': ticker,
                        'kalshi_price': round(kalshi_price, 2),
                        'kalshi_prob': round(kalshi_prob * 100, 1),
                        'fanduel_odds': int(fanduel_odds_value),
                        'fanduel_prob': round(fanduel_prob * 100, 1),
                        'fanduel_matchup': matched.get('matchup', ''),
                        'market_type': matched.get('type', 'unknown'),
                        'edge': round(edge, 1),
                        'ev': round(ev_dollars, 2),
                        'bet_amount': BET_AMOUNT,
                        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'kalshi_url': f"https://kalshi.com/markets/{ticker}"
                    })
    
    except Exception as e:
        debug['errors'].append(str(e))
        print(f"ERROR: {e}")
    
    finally:
        scan_in_progress = False
    
    return edges, debug


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html', 
                         min_edge=MIN_EDGE,
                         bet_amount=BET_AMOUNT,
                         has_odds_api=bool(ODDS_API_KEY))


@app.route('/api/scan', methods=['POST'])
def scan():
    """Trigger a new scan"""
    global current_edges, last_scan_time, debug_info
    
    if scan_in_progress:
        return jsonify({'status': 'error', 'message': 'Scan already in progress'})
    
    def background_scan():
        global current_edges, last_scan_time, debug_info
        edges, debug = find_edges()
        current_edges = edges
        debug_info = debug
        last_scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    thread = threading.Thread(target=background_scan)
    thread.start()
    
    return jsonify({'status': 'scanning', 'message': 'Scan started'})


@app.route('/api/edges')
def get_edges():
    """Get current edges"""
    return jsonify({
        'edges': current_edges,
        'last_scan': last_scan_time,
        'scanning': scan_in_progress,
        'min_edge': MIN_EDGE,
        'bet_amount': BET_AMOUNT,
        'debug': debug_info
    })


@app.route('/api/status')
def status():
    """Get app status"""
    return jsonify({
        'status': 'running',
        'has_odds_api': bool(ODDS_API_KEY),
        'has_kalshi_api': bool(KALSHI_API_KEY),
        'min_edge': MIN_EDGE,
        'bet_amount': BET_AMOUNT,
        'edges_found': len(current_edges),
        'last_scan': last_scan_time,
        'scanning': scan_in_progress,
        'mode': 'CATEGORY_BASED_BASKETBALL'
    })


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
