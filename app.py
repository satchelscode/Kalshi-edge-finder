"""
Kalshi Edge Finder - Using Authenticated Kalshi API
Matches Kalshi markets directly with FanDuel odds from The Odds API
"""

import os
import requests
import time
from datetime import datetime
from typing import Dict, List, Optional
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Environment variables
ODDS_API_KEY = os.getenv('ODDS_API_KEY', '')
KALSHI_EMAIL = os.getenv('KALSHI_EMAIL', '')
KALSHI_PASSWORD = os.getenv('KALSHI_PASSWORD', '')


class OddsConverter:
    @staticmethod
    def american_to_implied_prob(odds: int) -> float:
        """Convert American odds to implied probability"""
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)


class KalshiAuthAPI:
    """Authenticated Kalshi API client"""
    
    BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
    
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.token = None
        self.member_id = None
        self.session = requests.Session()
        
        if email and password:
            self._login()
    
    def _login(self):
        """Authenticate with Kalshi"""
        try:
            url = f"{self.BASE_URL}/login"
            payload = {
                "email": self.email,
                "password": self.password
            }
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            self.token = data.get('token')
            self.member_id = data.get('member_id')
            
            # Set authorization header
            self.session.headers.update({
                'Authorization': f'Bearer {self.token}',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            })
            
            print(f"✅ Kalshi authenticated: {self.email}")
            return True
            
        except Exception as e:
            print(f"❌ Kalshi authentication failed: {e}")
            return False
    
    def get_markets(self, series_ticker: str = None, limit: int = 200, status: str = 'open') -> List[Dict]:
        """Get markets (optionally filtered by series)"""
        try:
            url = f"{self.BASE_URL}/markets"
            params = {
                'limit': limit,
                'status': status
            }
            
            if series_ticker:
                params['series_ticker'] = series_ticker
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            markets = data.get('markets', [])
            print(f"   Fetched {len(markets)} markets" + (f" from {series_ticker}" if series_ticker else ""))
            return markets
            
        except Exception as e:
            print(f"Error fetching markets: {e}")
            return []
    
    def get_orderbook(self, ticker: str) -> Optional[Dict]:
        """Get orderbook for a specific market"""
        try:
            url = f"{self.BASE_URL}/markets/{ticker}/orderbook"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return None


class FanDuelAPI:
    """Fetch odds from The Odds API for FanDuel"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.the-odds-api.com/v4"
    
    def get_nba_odds(self) -> Dict:
        """Get NBA odds from FanDuel"""
        all_odds = {}
        
        try:
            url = f"{self.base_url}/sports/basketball_nba/odds"
            params = {
                'apiKey': self.api_key,
                'regions': 'us',
                'markets': 'h2h',
                'bookmakers': 'fanduel'
            }
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            games = response.json()
            
            for game in games:
                for bookmaker in game.get('bookmakers', []):
                    if bookmaker.get('key') == 'fanduel':
                        for market in bookmaker.get('markets', []):
                            if market.get('key') == 'h2h':
                                for outcome in market.get('outcomes', []):
                                    team_name = outcome.get('name')
                                    odds = outcome.get('price')
                                    
                                    all_odds[team_name] = {
                                        'team': team_name,
                                        'odds': odds,
                                        'game_id': game.get('id'),
                                        'commence_time': game.get('commence_time')
                                    }
            
            print(f"   Fetched {len(all_odds)} FanDuel NBA odds")
            return all_odds
            
        except Exception as e:
            print(f"Error fetching FanDuel odds: {e}")
            return {}


# NBA team city to full name mapping
NBA_TEAMS = {
    'atlanta': 'Atlanta Hawks',
    'boston': 'Boston Celtics',
    'brooklyn': 'Brooklyn Nets',
    'charlotte': 'Charlotte Hornets',
    'chicago': 'Chicago Bulls',
    'cleveland': 'Cleveland Cavaliers',
    'dallas': 'Dallas Mavericks',
    'denver': 'Denver Nuggets',
    'detroit': 'Detroit Pistons',
    'golden state': 'Golden State Warriors',
    'houston': 'Houston Rockets',
    'indiana': 'Indiana Pacers',
    'memphis': 'Memphis Grizzlies',
    'miami': 'Miami Heat',
    'milwaukee': 'Milwaukee Bucks',
    'minnesota': 'Minnesota Timberwolves',
    'new orleans': 'New Orleans Pelicans',
    'new york': 'New York Knicks',
    'oklahoma city': 'Oklahoma City Thunder',
    'orlando': 'Orlando Magic',
    'philadelphia': 'Philadelphia 76ers',
    'phoenix': 'Phoenix Suns',
    'portland': 'Portland Trail Blazers',
    'sacramento': 'Sacramento Kings',
    'san antonio': 'San Antonio Spurs',
    'toronto': 'Toronto Raptors',
    'utah': 'Utah Jazz',
    'washington': 'Washington Wizards',
    # Handle LA teams
    'los angeles': 'Los Angeles Lakers',  # Default to Lakers
    'la clippers': 'LA Clippers',
    'la lakers': 'Los Angeles Lakers',
}


def match_kalshi_to_fanduel(kalshi_title: str, fanduel_odds: Dict) -> Optional[Dict]:
    """Match Kalshi market title to FanDuel team"""
    title_lower = kalshi_title.lower()
    
    # Try to find city name in title
    for city, team_name in NBA_TEAMS.items():
        if city in title_lower:
            # Check if this team exists in FanDuel
            if team_name in fanduel_odds:
                return fanduel_odds[team_name]
    
    return None


def find_edges(kalshi_api: KalshiAuthAPI, fanduel_odds: Dict, min_edge: float = 0.005) -> List[Dict]:
    """Find arbitrage edges"""
    edges = []
    converter = OddsConverter()
    
    print("\n🔍 Finding edges...")
    
    # Get NBA game markets from Kalshi
    kalshi_markets = kalshi_api.get_markets(series_ticker='KXNBAGAME', limit=200)
    
    print(f"   Kalshi markets: {len(kalshi_markets)}")
    print(f"   FanDuel odds: {len(fanduel_odds)}")
    
    matches_found = 0
    
    for market in kalshi_markets:
        title = market.get('title', '')
        ticker = market.get('ticker', '')
        
        # Get orderbook for this market
        orderbook = kalshi_api.get_orderbook(ticker)
        if not orderbook:
            continue
        
        # Extract YES price from orderbook
        orderbook_data = orderbook.get('orderbook', {})
        yes_asks = orderbook_data.get('yes', [])
        
        if not yes_asks:
            continue
        
        # Get best YES ask price (lowest price to buy YES)
        best_yes_ask = min(yes_asks, key=lambda x: x[0])
        kalshi_price = best_yes_ask[0] / 100  # Convert cents to dollars
        
        # Skip illiquid markets
        if kalshi_price <= 0.01 or kalshi_price >= 0.99:
            continue
        
        # Match with FanDuel
        fd_match = match_kalshi_to_fanduel(title, fanduel_odds)
        
        if not fd_match:
            continue
        
        matches_found += 1
        
        # Calculate edge
        fd_odds = fd_match['odds']
        kalshi_prob = kalshi_price
        fd_prob = converter.american_to_implied_prob(fd_odds)
        
        # Edge calculation
        edge = (fd_prob / kalshi_prob) - 1
        
        if edge >= min_edge:
            edges.append({
                'kalshi_market': title,
                'kalshi_ticker': ticker,
                'kalshi_price': kalshi_price,
                'kalshi_prob': kalshi_prob * 100,
                'fanduel_team': fd_match['team'],
                'fanduel_odds': fd_odds,
                'fanduel_prob': fd_prob * 100,
                'edge': edge * 100,
                'recommendation': f"Buy YES on Kalshi at ${kalshi_price:.2f}"
            })
    
    print(f"   Matches found: {matches_found}")
    print(f"   Edges found: {len(edges)}")
    
    # Sort by edge
    edges.sort(key=lambda x: x['edge'], reverse=True)
    
    return edges


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/status')
def status():
    return jsonify({
        'status': 'running',
        'odds_api_configured': bool(ODDS_API_KEY),
        'kalshi_configured': bool(KALSHI_EMAIL and KALSHI_PASSWORD),
        'timestamp': datetime.utcnow().isoformat()
    })


@app.route('/api/scan', methods=['POST'])
def start_scan():
    return jsonify({'status': 'scanning'})


@app.route('/api/edges')
def get_edges():
    """Main endpoint - fetch and return edges"""
    try:
        min_edge = float(request.args.get('min_edge', 0.005))
        
        print("\n" + "="*60)
        print("STARTING EDGE SCAN")
        print("="*60)
        
        # Check configuration
        if not ODDS_API_KEY:
            return jsonify({'error': 'ODDS_API_KEY not configured'}), 500
        
        if not (KALSHI_EMAIL and KALSHI_PASSWORD):
            return jsonify({'error': 'Kalshi credentials not configured'}), 500
        
        # Initialize APIs
        print("\n=== AUTHENTICATING ===")
        kalshi = KalshiAuthAPI(KALSHI_EMAIL, KALSHI_PASSWORD)
        
        if not kalshi.token:
            return jsonify({'error': 'Kalshi authentication failed'}), 500
        
        print("\n=== FETCHING FANDUEL ODDS ===")
        fanduel = FanDuelAPI(ODDS_API_KEY)
        fanduel_odds = fanduel.get_nba_odds()
        
        if not fanduel_odds:
            return jsonify({'error': 'Could not fetch FanDuel odds'}), 500
        
        print("\n=== FINDING EDGES ===")
        edges = find_edges(kalshi, fanduel_odds, min_edge)
        
        return jsonify({
            'edges': edges,
            'timestamp': datetime.utcnow().isoformat(),
            'min_edge': min_edge
        })
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
