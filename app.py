"""
Kalshi Edge Finder Web Application - ENHANCED DEBUG VERSION
Shows detailed logging of what's being scanned
"""

from flask import Flask, render_template, jsonify, request
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
debug_info = {}  # NEW: Store debug information


class OddsConverter:
    """Convert between different odds formats"""
    
    @staticmethod
    def american_to_implied_prob(american_odds: int) -> float:
        """Convert American odds to implied probability"""
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
    """Wrapper for Kalshi API"""
    
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
        
    def get_markets(self, limit: int = 100, status: str = "open") -> List[Dict]:
        """Fetch active markets from Kalshi"""
        try:
            url = f"{self.base_url}/markets"
            params = {'limit': limit, 'status': status}
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('markets', [])
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
            print(f"Error fetching orderbook for {ticker}: {e}")
            return None
    
    def get_sports_markets(self) -> List[Dict]:
        """Get sports-related markets"""
        all_markets = self.get_markets(limit=200)
        sports_keywords = ['nba', 'nfl', 'nhl', 'mlb', 'ncaa', 'soccer', 
                          'championship', 'super bowl', 'finals', 'playoff',
                          'game', 'match', 'win', 'team', 'player']
        
        sports_markets = []
        for market in all_markets:
            title = market.get('title', '').lower()
            subtitle = market.get('subtitle', '').lower()
            if any(keyword in title or keyword in subtitle for keyword in sports_keywords):
                sports_markets.append(market)
        
        return sports_markets


class TheOddsAPI:
    """Wrapper for The Odds API"""
    
    BASE_URL = "https://api.the-odds-api.com/v4"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.session = requests.Session()
    
    def get_odds(self, sport: str = "basketball_nba") -> List[Dict]:
        """Get odds for a specific sport"""
        if not self.api_key:
            return []
        
        url = f"{self.BASE_URL}/sports/{sport}/odds"
        params = {
            'apiKey': self.api_key,
            'regions': 'us',
            'markets': 'h2h',
            'bookmakers': 'fanduel',
            'oddsFormat': 'american'
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching odds for {sport}: {e}")
            return []
    
    def get_fanduel_odds_all_sports(self) -> Dict[str, float]:
        """Get FanDuel odds across multiple sports"""
        if not self.api_key:
            # Return mock data for demo
            return {
                "Lakers": -150, "Lakers Win": -150,
                "Celtics": +130, "Celtics Win": +130,
                "Warriors": -200, "Warriors Win": -200,
                "Heat": +180, "Heat Win": +180,
                "76ers": -110, "76ers Win": -110,
                "Bucks": -175, "Bucks Win": -175,
            }
        
        sports = ['basketball_nba', 'americanfootball_nfl', 'icehockey_nhl', 'baseball_mlb']
        all_odds = {}
        
        for sport in sports:
            odds_data = self.get_odds(sport=sport)
            
            for game in odds_data:
                home_team = game.get('home_team', '')
                away_team = game.get('away_team', '')
                
                bookmakers = game.get('bookmakers', [])
                for book in bookmakers:
                    if book.get('key') == 'fanduel':
                        markets = book.get('markets', [])
                        for market in markets:
                            if market.get('key') == 'h2h':
                                outcomes = market.get('outcomes', [])
                                for outcome in outcomes:
                                    team = outcome.get('name')
                                    odds = outcome.get('price')
                                    all_odds[team] = odds
                                    all_odds[f"{team} Win"] = odds
                                    all_odds[f"{team} to win"] = odds
            
            time.sleep(0.5)
        
        return all_odds


def find_edges() -> tuple[List[Dict], Dict]:
    """Find all betting edges - NOW RETURNS DEBUG INFO TOO"""
    global scan_in_progress
    
    scan_in_progress = True
    edges = []
    debug = {
        'kalshi_markets_total': 0,
        'kalshi_markets_sports': 0,
        'kalshi_markets_list': [],
        'fanduel_odds_total': 0,
        'fanduel_teams': [],
        'matches_found': 0,
        'match_details': [],
        'edges_below_threshold': [],
        'errors': []
    }
    
    try:
        converter = OddsConverter()
        kalshi = KalshiAPI(api_key=KALSHI_API_KEY)
        odds_api = TheOddsAPI(api_key=ODDS_API_KEY)
        
        # Get FanDuel data
        fanduel_odds = odds_api.get_fanduel_odds_all_sports()
        debug['fanduel_odds_total'] = len(fanduel_odds)
        debug['fanduel_teams'] = list(fanduel_odds.keys())[:20]  # First 20
        
        # Get Kalshi data
        all_markets = kalshi.get_markets(limit=200)
        debug['kalshi_markets_total'] = len(all_markets)
        
        markets = kalshi.get_sports_markets()
        debug['kalshi_markets_sports'] = len(markets)
        debug['kalshi_markets_list'] = [m.get('title', 'Unknown') for m in markets[:20]]
        
        for market in markets:
            ticker = market.get('ticker', '')
            title = market.get('title', '')
            
            # Get orderbook
            orderbook = kalshi.get_orderbook(ticker)
            if not orderbook:
                continue
            
            orderbook_data = orderbook.get('orderbook', {})
            yes_asks = orderbook_data.get('yes', [])
            
            if not yes_asks:
                continue
            
            # Best price
            best_ask = min(yes_asks, key=lambda x: x[0])
            kalshi_price = best_ask[0] / 100
            kalshi_prob = kalshi_price
            
            # Match with FanDuel
            matched_odds = match_event(title, fanduel_odds)
            
            if matched_odds is not None:
                debug['matches_found'] += 1
                
                fanduel_prob = converter.american_to_implied_prob(matched_odds)
                edge = converter.calculate_edge(fanduel_prob, kalshi_prob)
                
                match_info = {
                    'kalshi_title': title,
                    'kalshi_price': kalshi_price,
                    'fanduel_odds': matched_odds,
                    'edge': round(edge, 2)
                }
                debug['match_details'].append(match_info)
                
                if edge >= MIN_EDGE:
                    payout_if_win = 1.0 - kalshi_price
                    ev = fanduel_prob * payout_if_win - (1 - fanduel_prob) * kalshi_price
                    ev_dollars = ev * BET_AMOUNT
                    
                    edges.append({
                        'event_name': title,
                        'kalshi_market': ticker,
                        'kalshi_price': round(kalshi_price, 2),
                        'kalshi_prob': round(kalshi_prob * 100, 1),
                        'fanduel_odds': int(matched_odds),
                        'fanduel_prob': round(fanduel_prob * 100, 1),
                        'edge': round(edge, 1),
                        'ev': round(ev_dollars, 2),
                        'bet_amount': BET_AMOUNT,
                        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'kalshi_url': f"https://kalshi.com/markets/{ticker}"
                    })
                else:
                    # Track near-misses
                    if edge > 0:
                        debug['edges_below_threshold'].append(match_info)
    
    except Exception as e:
        debug['errors'].append(str(e))
    
    finally:
        scan_in_progress = False
    
    return edges, debug


def match_event(kalshi_title: str, fanduel_odds: Dict) -> Optional[float]:
    """Match Kalshi event with FanDuel odds"""
    if kalshi_title in fanduel_odds:
        return fanduel_odds[kalshi_title]
    
    kalshi_lower = kalshi_title.lower()
    for fd_event, odds in fanduel_odds.items():
        fd_lower = fd_event.lower()
        kalshi_words = set(kalshi_lower.split())
        fd_words = set(fd_lower.split())
        overlap = kalshi_words & fd_words
        
        if len(overlap) >= 2:
            return odds
    
    return None


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
        'debug': debug_info  # NEW: Include debug info
    })


@app.route('/api/debug')
def get_debug():
    """Get debug information"""
    return jsonify(debug_info)


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
        'scanning': scan_in_progress
    })


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
