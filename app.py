# Copy the entire app_kalshi_correct.py content first, then replace the find_edges function

import os
import requests
from flask import Flask, render_template, jsonify, request
from datetime import datetime
from typing import Dict, List, Optional
import json

app = Flask(__name__)

# Configuration
ODDS_API_KEY = os.environ.get('ODDS_API_KEY')
KALSHI_API_KEY_ID = os.environ.get('KALSHI_API_KEY_ID')
KALSHI_PRIVATE_KEY = os.environ.get('KALSHI_PRIVATE_KEY')


class OddsConverter:
    @staticmethod
    def american_to_implied_prob(odds: int) -> float:
        """Convert American odds to implied probability"""
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)
    
    @staticmethod
    def decimal_to_implied_prob(odds: float) -> float:
        """Convert decimal odds to implied probability"""
        return 1 / odds
    
    @staticmethod
    def prob_to_american(prob: float) -> int:
        """Convert probability to American odds"""
        if prob >= 0.5:
            return int(-100 * prob / (1 - prob))
        else:
            return int(100 * (1 - prob) / prob)


class FanDuelAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.the-odds-api.com/v4"
    
    def get_nba_odds(self) -> Dict:
        """Fetch NBA odds from FanDuel via The Odds API"""
        try:
            url = f"{self.base_url}/sports/basketball_nba/odds/"
            params = {
                'apiKey': self.api_key,
                'regions': 'us',
                'markets': 'h2h',
                'bookmakers': 'fanduel',
                'oddsFormat': 'decimal'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            odds_dict = {}
            for game in data:
                for bookmaker in game.get('bookmakers', []):
                    if bookmaker['key'] == 'fanduel':
                        for market in bookmaker.get('markets', []):
                            if market['key'] == 'h2h':
                                for outcome in market.get('outcomes', []):
                                    team_name = outcome['name']
                                    odds = outcome['price']
                                    odds_dict[team_name] = {
                                        'odds': odds,
                                        'team': team_name
                                    }
            
            print(f"   Fetched {len(odds_dict)} FanDuel NBA odds")
            return odds_dict
            
        except Exception as e:
            print(f"   Error fetching FanDuel odds: {e}")
            return {}


class KalshiAPI:
    def __init__(self, api_key_id: str = None, private_key: str = None):
        self.BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
        self.api_key_id = api_key_id
        self.private_key = private_key
        self.session = requests.Session()
        
        # Setup headers (works without authentication for public endpoints)
        headers = {
            'Accept': 'application/json'
        }
        
        if api_key_id:
            headers['KALSHI-ACCESS-KEY'] = api_key_id
            print("   ✅ Using authenticated Kalshi API")
        else:
            print("   ⚠️  Using Kalshi public API (no authentication)")
        
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
        Get orderbook for a specific market
        GET /markets/{ticker}/orderbook
        """
        try:
            url = f"{self.BASE_URL}/markets/{ticker}/orderbook"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return None


def find_edges(kalshi_api, fanduel_odds, min_edge=0.005):
    """
    OPTIMIZED: Find arbitrage opportunities by checking BOTH ways to bet on each outcome.
    
    For each team winning, we can either:
    1. Buy YES on that team
    2. Buy NO on their opponent
    
    We pick the CHEAPER option and compare against FanDuel.
    """
    converter = OddsConverter()
    edges = []
    
    # Team abbreviation mapping
    TEAM_MAP = {
        'MIA': 'Miami Heat', 'CHI': 'Chicago Bulls', 'MIL': 'Milwaukee Bucks',
        'WAS': 'Washington Wizards', 'PHI': 'Philadelphia 76ers', 'SAC': 'Sacramento Kings',
        'ATL': 'Atlanta Hawks', 'HOU': 'Houston Rockets', 'DAL': 'Dallas Mavericks',
        'CHA': 'Charlotte Hornets', 'DET': 'Detroit Pistons', 'PHX': 'Phoenix Suns',
        'BKN': 'Brooklyn Nets', 'DEN': 'Denver Nuggets', 'MIN': 'Minnesota Timberwolves',
        'OKC': 'Oklahoma City Thunder', 'BOS': 'Boston Celtics', 'NYK': 'New York Knicks',
        'POR': 'Portland Trail Blazers', 'LAL': 'Los Angeles Lakers', 'LAC': 'LA Clippers',
        'GSW': 'Golden State Warriors', 'UTA': 'Utah Jazz', 'MEM': 'Memphis Grizzlies',
        'NOP': 'New Orleans Pelicans', 'ORL': 'Orlando Magic', 'TOR': 'Toronto Raptors',
        'CLE': 'Cleveland Cavaliers',
    }
    
    print("\n🔍 FINDING EDGES (OPTIMIZED)")
    
    # Get all NBA markets
    kalshi_markets = kalshi_api.get_markets(series_ticker='KXNBAGAME', limit=200)
    
    # Filter for TODAY only
    today_markets = [m for m in kalshi_markets if '26JAN29' in m.get('ticker', '')]
    print(f"\n🗓️  TODAY's markets: {len(today_markets)}")
    
    # Group markets by game
    games = {}
    for market in today_markets:
        ticker = market.get('ticker', '')
        parts = ticker.split('-')
        if len(parts) < 3:
            continue
        
        game_code = parts[1][7:]  # Extract game identifier
        team_abbrev = parts[2]
        
        if game_code not in games:
            games[game_code] = {}
        games[game_code][team_abbrev] = market
    
    print(f"🏀 Found {len(games)} unique games\n")
    
    # Process each game
    for game_code, team_markets in games.items():
        if len(team_markets) != 2:
            continue
        
        team_abbrevs = list(team_markets.keys())
        team1_abbrev, team2_abbrev = team_abbrevs[0], team_abbrevs[1]
        team1_name = TEAM_MAP.get(team1_abbrev, team1_abbrev)
        team2_name = TEAM_MAP.get(team2_abbrev, team2_abbrev)
        
        print(f"{'='*60}")
        print(f"🏀 {team1_name} vs {team2_name}")
        
        # Get orderbooks
        ob1 = kalshi_api.get_orderbook(team_markets[team1_abbrev]['ticker'])
        ob2 = kalshi_api.get_orderbook(team_markets[team2_abbrev]['ticker'])
        
        if not ob1 or not ob2:
            print(f"   ❌ Missing orderbook\n")
            continue
        
        # Extract prices
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
            print(f"   ❌ Incomplete prices\n")
            continue
        
        print(f"   {team1_name}: YES={team1_yes:.2f}, NO={team1_no:.2f}")
        print(f"   {team2_name}: YES={team2_yes:.2f}, NO={team2_no:.2f}")
        
        # Find BEST price for each outcome
        # Team1 winning: buy Team1 YES OR Team2 NO (pick cheaper)
        team1_best_price = min(team1_yes, team2_no)
        team1_method = f"YES on {team1_name}" if team1_yes <= team2_no else f"NO on {team2_name}"
        
        # Team2 winning: buy Team2 YES OR Team1 NO (pick cheaper)
        team2_best_price = min(team2_yes, team1_no)
        team2_method = f"YES on {team2_name}" if team2_yes <= team1_no else f"NO on {team1_name}"
        
        print(f"\n   💰 BEST PRICES:")
        print(f"   {team1_name} wins: ${team1_best_price:.2f} ({team1_method})")
        print(f"   {team2_name} wins: ${team2_best_price:.2f} ({team2_method})")
        
        # Check edges
        for team_name, best_price, method in [
            (team1_name, team1_best_price, team1_method),
            (team2_name, team2_best_price, team2_method)
        ]:
            if team_name not in fanduel_odds:
                continue
            
            fd_odds = fanduel_odds[team_name]['odds']
            
            # Calculate Kalshi fees using the correct formula:
            # Fee = round_up(0.07 × C × P × (1-P))
            # Where C = contracts, P = price
            # We'll calculate per-contract effective price
            
            P = best_price  # Price per contract (e.g., 0.18)
            C = 100  # Calculate for 100 contracts as baseline
            
            # Kalshi fee formula
            import math
            fee_total = math.ceil(0.07 * C * P * (1 - P) * 100) / 100  # Round up to nearest cent
            fee_per_contract = fee_total / C
            
            # Effective cost per contract after fees
            effective_cost = P + fee_per_contract
            
            # Calculate probabilities and edge
            kalshi_prob_after_fees = effective_cost
            fd_prob = converter.decimal_to_implied_prob(fd_odds)
            edge = (fd_prob / kalshi_prob_after_fees) - 1
            
            # Edge before fees (for comparison)
            edge_before_fees = (fd_prob / P) - 1
            
            print(f"\n   📊 {team_name}:")
            print(f"      Kalshi: ${P:.2f} ({P*100:.1f}%) - {method}")
            print(f"      Kalshi fee: ${fee_per_contract:.4f}/contract (${fee_total:.2f} per 100 contracts)")
            print(f"      Kalshi after fees: ${effective_cost:.4f} ({kalshi_prob_after_fees*100:.2f}%)")
            print(f"      FanDuel: {fd_odds:.2f} ({fd_prob*100:.1f}%)")
            print(f"      Edge before fees: {edge_before_fees*100:.2f}%")
            print(f"      Edge after fees: {edge*100:.2f}%")
            
            if edge >= min_edge:
                edges.append({
                    'game': f"{team1_name} vs {team2_name}",
                    'team': team_name,
                    'kalshi_price': best_price,
                    'kalshi_fee_per_contract': fee_per_contract,
                    'kalshi_price_after_fees': effective_cost,
                    'kalshi_prob': P * 100,
                    'kalshi_prob_after_fees': kalshi_prob_after_fees * 100,
                    'kalshi_method': method,
                    'fanduel_odds': fd_odds,
                    'fanduel_prob': fd_prob * 100,
                    'edge_before_fees': edge_before_fees * 100,
                    'edge_after_fees': edge * 100,
                    'recommendation': f"Buy {method} at ${P:.2f} (${effective_cost:.4f} after fees)"
                })
                print(f"      ✅ EDGE FOUND!")
        
        print()
    
    print(f"{'='*60}")
    print(f"✅ Found {len(edges)} edges\n")
    return edges


@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')


@app.route('/api/status')
def status():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'odds_api_configured': bool(ODDS_API_KEY),
        'kalshi_authenticated': bool(KALSHI_API_KEY_ID)
    })


@app.route('/api/scan', methods=['POST'])
def scan():
    """Trigger a new scan"""
    return jsonify({'message': 'Scan started'})


@app.route('/api/edges')
def get_edges():
    """Main endpoint - fetch and return edges"""
    try:
        min_edge = float(request.args.get('min_edge', 0.005))
        
        print("\n" + "="*60)
        print("STARTING EDGE SCAN")
        print("="*60)
        
        if not ODDS_API_KEY:
            return jsonify({'error': 'ODDS_API_KEY not configured'}), 500
        
        print("\n=== INITIALIZING KALSHI API ===")
        kalshi = KalshiAPI(KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY)
        
        print("\n=== FETCHING FANDUEL ODDS ===")
        fanduel = FanDuelAPI(ODDS_API_KEY)
        fanduel_odds = fanduel.get_nba_odds()
        
        if not fanduel_odds:
            return jsonify({'error': 'Could not fetch FanDuel odds'}), 500
        
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
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
