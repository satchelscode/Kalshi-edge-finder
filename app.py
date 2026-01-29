"""
Kalshi Edge Finder - CORRECT API Key Implementation
Based on Kalshi API v2 documentation
"""

import os
import requests
import time
import hmac
import hashlib
import base64
from datetime import datetime
from typing import Dict, List, Optional
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Environment variables
ODDS_API_KEY = os.getenv('ODDS_API_KEY', '')
KALSHI_API_KEY_ID = os.getenv('KALSHI_API_KEY_ID', '')
KALSHI_PRIVATE_KEY = os.getenv('KALSHI_PRIVATE_KEY', '')


class OddsConverter:
    @staticmethod
    def american_to_implied_prob(odds: int) -> float:
        """Convert American odds to implied probability"""
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)


class KalshiAPI:
    """
    Kalshi API client using API Key authentication
    Docs: https://trading-api.readme.io/reference/getting-started
    """
    
    BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
    
    def __init__(self, api_key_id: str = None, private_key: str = None):
        self.api_key_id = api_key_id
        self.private_key = private_key
        self.session = requests.Session()
        
        # Setup headers
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        # Add API key if provided
        if api_key_id:
            headers['KALSHI-ACCESS-KEY'] = api_key_id
            print(f"✅ Kalshi API configured with key: {api_key_id[:12]}...")
        else:
            print("⚠️  Using Kalshi public API (no authentication)")
        
        self.session.headers.update(headers)
    
    def get_markets(self, series_ticker: str = None, limit: int = 200, status: str = 'open') -> List[Dict]:
        """
        Get markets with pagination support
        GET /markets
        """
        all_markets = []
        cursor = None
        
        try:
            while True:
                url = f"{self.BASE_URL}/markets"
                params = {
                    'limit': limit,
                    'status': status
                }
                
                if series_ticker:
                    params['series_ticker'] = series_ticker
                
                if cursor:
                    params['cursor'] = cursor
                
                response = self.session.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                markets = data.get('markets', [])
                all_markets.extend(markets)
                
                # Check if there's more data
                cursor = data.get('cursor')
                if not cursor:
                    break  # No more pages
                
                print(f"   Fetched {len(markets)} markets (total: {len(all_markets)})...")
            
            series_info = f" from {series_ticker}" if series_ticker else ""
            print(f"   ✅ Total: {len(all_markets)} markets{series_info}")
            return all_markets
            
        except requests.exceptions.HTTPError as e:
            print(f"   HTTP Error {e.response.status_code}: {e}")
            return all_markets  # Return what we have so far
        except Exception as e:
            print(f"   Error fetching markets: {e}")
            return all_markets
    
    def get_orderbook(self, ticker: str) -> Optional[Dict]:
        """
        Get orderbook for a market
        GET /markets/{ticker}/orderbook
        """
        try:
            url = f"{self.BASE_URL}/markets/{ticker}/orderbook"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return None
    
    def get_market(self, ticker: str) -> Optional[Dict]:
        """
        Get single market details
        GET /markets/{ticker}
        """
        try:
            url = f"{self.BASE_URL}/markets/{ticker}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('market')
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
            print(f"   Error fetching FanDuel odds: {e}")
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
    'los angeles': 'Los Angeles Lakers',
    'la': 'Los Angeles Lakers',
}


def match_kalshi_to_fanduel(kalshi_title: str, fanduel_odds: Dict) -> Optional[Dict]:
    """Match Kalshi market title to FanDuel team"""
    title_lower = kalshi_title.lower()
    
    # Debug first 3 matches
    print(f"   Matching: '{kalshi_title[:50]}'")
    
    # Try to find city name in title
    for city, team_name in NBA_TEAMS.items():
        if city in title_lower:
            # Check if this team exists in FanDuel
            if team_name in fanduel_odds:
                print(f"      ✅ Matched: {city} → {team_name}")
                return fanduel_odds[team_name]
    
    print(f"      ❌ No match found")
    return None


def find_edges(kalshi_api: KalshiAPI, fanduel_odds: Dict, min_edge: float = 0.005) -> List[Dict]:
    """Find arbitrage edges"""
    edges = []
    converter = OddsConverter()
    
    print("\n🔍 FINDING EDGES")
    
    # Get NBA game markets from Kalshi
    kalshi_markets = kalshi_api.get_markets(series_ticker='KXNBAGAME', limit=200)
    
    print(f"   Kalshi markets: {len(kalshi_markets)}")
    print(f"   FanDuel odds: {len(fanduel_odds)}")
    
    # DEBUG: Show ALL market titles
    print(f"\n📋 ALL KALSHI MARKETS:")
    for i, market in enumerate(kalshi_markets[:20], 1):
        title = market.get('title', '')
        ticker = market.get('ticker', '')
        print(f"   {i}. {title} ({ticker})")
    
    print()
    
    matches_found = 0
    markets_checked = 0
    
    # Filter for TODAY's games only (26JAN29)
    today_markets = [m for m in kalshi_markets if '26JAN29' in m.get('ticker', '')]
    print(f"\n🗓️  TODAY's markets (26JAN29): {len(today_markets)}")
    
    for market in today_markets[:20]:  # Check first 20 TODAY's games
        title = market.get('title', '')
        ticker = market.get('ticker', '')
        markets_checked += 1
        
        print(f"\n📊 Market #{markets_checked}: {title}")
        
        # Get orderbook for this market
        orderbook = kalshi_api.get_orderbook(ticker)
        if not orderbook:
            print(f"   ❌ No orderbook data")
            continue
        
        # Extract YES price from orderbook (using BIDS, not asks!)
        orderbook_data = orderbook.get('orderbook', {})
        yes_bids = orderbook_data.get('yes', [])
        
        if not yes_bids:
            print(f"   ❌ No YES bids in orderbook")
            continue
        
        # Get best YES bid price (highest price someone will pay)
        # Format: [[price_cents, quantity], ...]
        best_yes_bid = max(yes_bids, key=lambda x: x[0])
        kalshi_price = best_yes_bid[0] / 100  # Convert cents to dollars
        print(f"   Kalshi price: ${kalshi_price:.2f} (from YES bid: {best_yes_bid[0]}¢)")
        
        # Skip illiquid markets
        if kalshi_price <= 0.01 or kalshi_price >= 0.99:
            print(f"   ⚠️  Illiquid (price too extreme)")
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
        
        edge = (fd_prob / kalshi_prob) - 1
        
        print(f"   FanDuel odds: {fd_odds} ({fd_prob*100:.1f}%)")
        print(f"   Edge: {edge*100:.2f}%")
        
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
    
    print(f"\n✅ RESULTS:")
    print(f"   Markets checked: {markets_checked}")
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
        'kalshi_configured': bool(KALSHI_API_KEY_ID),
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
        
        # Initialize APIs (Kalshi works with or without API key)
        print("\n=== INITIALIZING KALSHI API ===")
        kalshi = KalshiAPI(KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY)
        
        print("\n=== FETCHING FANDUEL ODDS ===")
        fanduel = FanDuelAPI(ODDS_API_KEY)
        fanduel_odds = fanduel.get_nba_odds()
        
        if not fanduel_odds:
            return jsonify({'error': 'Could not fetch FanDuel odds'}), 500
        
        # DEBUG: Show FanDuel games
        print(f"\n📋 FANDUEL GAMES:")
        for team, data in list(fanduel_odds.items())[:10]:
            print(f"   - {team}: {data['odds']}")
        print()
        
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
