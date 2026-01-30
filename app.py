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
        return self._get_odds('basketball_nba')
    
    def get_ncaab_odds(self) -> Dict:
        """Fetch NCAAB (college basketball) odds from FanDuel via The Odds API"""
        return self._get_odds('basketball_ncaab')
    
    def _get_odds(self, sport: str) -> Dict:
        """Generic method to fetch odds for any sport"""
        try:
            url = f"{self.base_url}/sports/{sport}/odds/"
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
            
            print(f"   Fetched {len(odds_dict)} FanDuel {sport.upper()} odds")
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
                
                # Add small delay to avoid rate limits
                import time
                time.sleep(0.5)  # 500ms delay between requests
            
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


def find_edges(kalshi_api, fanduel_odds, min_edge=0.005, series_ticker='KXNBAGAME'):
    """
    OPTIMIZED: Find arbitrage opportunities by checking BOTH ways to bet on each outcome.
    
    For each team winning, we can either:
    1. Buy YES on that team
    2. Buy NO on their opponent
    
    We pick the CHEAPER option and compare against FanDuel.
    
    Args:
        series_ticker: 'KXNBAGAME' for NBA, 'KXNCAABGAME' for NCAA basketball
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
    
    # Get all markets for the specified series
    kalshi_markets = kalshi_api.get_markets(series_ticker=series_ticker, limit=200)
    
    # Filter for TODAY only - dynamically generate today's date code
    from datetime import datetime
    today_str = datetime.utcnow().strftime('%y%b%d').upper()  # e.g., "26JAN30"
    today_markets = [m for m in kalshi_markets if today_str in m.get('ticker', '')]
    print(f"\n🗓️  TODAY's markets ({today_str}): {len(today_markets)}")
    
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
        
        # Check for ARBITRAGE opportunities
        # We ALWAYS bet on Kalshi, and hedge the OPPOSITE outcome on FanDuel
        for team_name, best_price, method in [
            (team1_name, team1_best_price, team1_method),
            (team2_name, team2_best_price, team2_method)
        ]:
            # Determine the OPPOSITE team (for FanDuel hedge)
            opposite_team = team2_name if team_name == team1_name else team1_name
            
            # Check if BOTH teams exist in FanDuel
            if team_name not in fanduel_odds or opposite_team not in fanduel_odds:
                continue
            
            # Get FanDuel odds for the OPPOSITE outcome (our hedge)
            fd_opposite_odds = fanduel_odds[opposite_team]['odds']
            fd_opposite_prob = converter.decimal_to_implied_prob(fd_opposite_odds)
            
            # Calculate Kalshi probability AFTER fees
            P = best_price  # Price per contract
            C = 100  # Calculate for 100 contracts
            
            # Kalshi fee formula: round_up(0.07 × C × P × (1-P))
            import math
            fee_total = math.ceil(0.07 * C * P * (1 - P) * 100) / 100
            fee_per_contract = fee_total / C
            effective_cost = P + fee_per_contract
            
            kalshi_prob_after_fees = effective_cost
            
            # ARBITRAGE CHECK:
            # We bet Team A on Kalshi (kalshi_prob_after_fees)
            # We bet Team B on FanDuel (fd_opposite_prob)
            # For arbitrage: kalshi_prob + fd_opposite_prob < 100%
            
            total_prob = kalshi_prob_after_fees + fd_opposite_prob
            
            # Calculate arbitrage profit
            if total_prob < 1.0:  # True arbitrage exists!
                arbitrage_profit = (1.0 / total_prob) - 1
                
                print(f"\n   📊 {team_name}:")
                print(f"      Kalshi: ${P:.2f} ({P*100:.1f}%) - {method}")
                print(f"      Kalshi fee: ${fee_per_contract:.4f}/contract (${fee_total:.2f} per 100 contracts)")
                print(f"      Kalshi after fees: ${effective_cost:.4f} ({kalshi_prob_after_fees*100:.2f}%)")
                print(f"      FanDuel {opposite_team}: {fd_opposite_odds:.2f} ({fd_opposite_prob*100:.2f}%)")
                print(f"      Total implied prob: {total_prob*100:.2f}%")
                print(f"      🎯 ARBITRAGE: {arbitrage_profit*100:.2f}% guaranteed profit")
                print(f"      ✅ ARBITRAGE FOUND!")
                
                edges.append({
                    'game': f"{team1_name} vs {team2_name}",
                    'team': team_name,
                    'opposite_team': opposite_team,
                    'kalshi_price': best_price,
                    'kalshi_fee_per_contract': fee_per_contract,
                    'kalshi_price_after_fees': effective_cost,
                    'kalshi_prob_after_fees': kalshi_prob_after_fees * 100,
                    'kalshi_method': method,
                    'fanduel_opposite_team': opposite_team,
                    'fanduel_opposite_odds': fd_opposite_odds,
                    'fanduel_opposite_prob': fd_opposite_prob * 100,
                    'total_implied_prob': total_prob * 100,
                    'arbitrage_profit': arbitrage_profit * 100,
                    'recommendation': f"Bet ${best_price:.2f} on {method} (Kalshi) + hedge on {opposite_team} at {fd_opposite_odds:.2f} (FanDuel)",
                    'strategy': f"1. Buy {method} on Kalshi\n2. Bet {opposite_team} ML on FanDuel"
                })
            else:
                # No arbitrage
                print(f"\n   📊 {team_name}:")
                print(f"      Kalshi after fees: ${effective_cost:.4f} ({kalshi_prob_after_fees*100:.2f}%)")
                print(f"      FanDuel {opposite_team}: {fd_opposite_odds:.2f} ({fd_opposite_prob*100:.2f}%)")
                print(f"      Total implied prob: {total_prob*100:.2f}%")
                print(f"      ❌ No arbitrage (total > 100%)")
        
        print()
    
    print(f"{'='*60}")
    print(f"✅ Found {len(edges)} edges\n")
    return edges


@app.route('/')
def index():
    """Redirect to debug view (working UI)"""
    from flask import redirect
    return redirect('/debug')


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
    """Main endpoint - fetch and return edges for both NBA and NCAA"""
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
        
        # Fetch both NBA and NCAA odds
        nba_odds = fanduel.get_nba_odds()
        ncaab_odds = fanduel.get_ncaab_odds()
        
        all_edges = []
        
        # Find NBA arbitrage opportunities
        if nba_odds:
            print("\n🏀 CHECKING NBA...")
            nba_edges = find_edges(kalshi, nba_odds, min_edge, series_ticker='KXNBAGAME')
            all_edges.extend(nba_edges)
        
        # Find NCAA arbitrage
        if ncaab_odds:
            print("\n🏀 CHECKING NCAA BASKETBALL...")
            ncaab_edges = find_edges(kalshi, ncaab_odds, min_edge, series_ticker='KXNCAAMBGAME')
            all_edges.extend(ncaab_edges)
        
        return jsonify({
            'edges': all_edges,
            'nba_count': len([e for e in all_edges if 'NBA' in e.get('sport', 'NBA')]),
            'ncaab_count': len([e for e in all_edges if 'NCAA' in e.get('sport', '')]),
            'timestamp': datetime.utcnow().isoformat(),
            'min_edge': min_edge
        })
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/debug')
def debug_view():
    """Simple HTML view of edges"""
    try:
        kalshi = KalshiAPI(KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY)
        fanduel = FanDuelAPI(ODDS_API_KEY)
        
        # Fetch both NBA and NCAA odds
        nba_odds = fanduel.get_nba_odds()
        ncaab_odds = fanduel.get_ncaab_odds()
        
        all_edges = []
        
        # Find NBA arbitrage
        if nba_odds:
            nba_edges = find_edges(kalshi, nba_odds, 0.005, series_ticker='KXNBAGAME')
            for edge in nba_edges:
                edge['sport'] = 'NBA'
            all_edges.extend(nba_edges)
        
        # Find NCAA arbitrage
        if ncaab_odds:
            ncaab_edges = find_edges(kalshi, ncaab_odds, 0.005, series_ticker='KXNCAAMBGAME')
            for edge in ncaab_edges:
                edge['sport'] = 'NCAA'
            all_edges.extend(ncaab_edges)
        
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Kalshi Arbitrage Finder - Live</title>
            <meta http-equiv="refresh" content="60">
            <style>
                body { 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                    color: #eee;
                    min-height: 100vh;
                }
                .container { max-width: 1200px; margin: 0 auto; }
                h1 { 
                    color: #00ff88; 
                    text-align: center;
                    font-size: 2.5em;
                    margin-bottom: 10px;
                }
                .subtitle {
                    text-align: center;
                    color: #aaa;
                    margin-bottom: 30px;
                    font-size: 1.1em;
                }
                .edge { 
                    background: #16213e; 
                    padding: 20px;
                    margin: 15px 0; 
                    border-radius: 12px;
                    border-left: 4px solid #00ff88;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.3);
                }
                .edge:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 6px 12px rgba(0,255,136,0.2);
                    transition: all 0.3s ease;
                }
                .game { 
                    font-size: 0.9em; 
                    color: #888; 
                    margin-bottom: 8px;
                }
                .team { 
                    font-weight: bold; 
                    color: #ff6b6b; 
                    font-size: 1.3em;
                    margin-bottom: 10px;
                }
                .row {
                    display: flex;
                    justify-content: space-between;
                    margin: 8px 0;
                    padding: 8px 0;
                    border-bottom: 1px solid #2a2a3e;
                }
                .label { color: #aaa; }
                .value { font-weight: 600; }
                .positive { color: #00ff88; font-weight: bold; font-size: 1.1em; }
                .method { 
                    background: #0f3460;
                    padding: 6px 12px;
                    border-radius: 6px;
                    display: inline-block;
                    margin-top: 10px;
                    font-size: 0.95em;
                }
                .count {
                    text-align: center;
                    font-size: 1.2em;
                    margin: 20px 0;
                    padding: 15px;
                    background: #0f3460;
                    border-radius: 8px;
                }
                .sport-badge {
                    display: inline-block;
                    padding: 4px 10px;
                    border-radius: 4px;
                    font-size: 0.75em;
                    font-weight: bold;
                    margin-left: 10px;
                }
                .sport-nba { background: #e74c3c; color: white; }
                .sport-ncaa { background: #3498db; color: white; }
                .no-arb {
                    text-align: center;
                    padding: 60px 20px;
                    color: #888;
                    font-size: 1.2em;
                }
                .no-arb p { margin: 15px 0; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎯 Kalshi Arbitrage Finder</h1>
                <div class="subtitle">TRUE arbitrage opportunities (guaranteed profit) • NBA + NCAA Basketball • Auto-refreshes every 30 seconds</div>
                <div class="count">
        """
        
        # Add count message
        if all_edges:
            html += f"Found <strong style='color: #00ff88;'>{len(all_edges)}</strong> arbitrage opportunities! 🎉"
        else:
            html += "⏳ No arbitrage opportunities right now"
        
        html += """
                </div>
        """
        
        if all_edges:
            for edge in all_edges:
                sport = edge.get('sport', 'NBA')
                sport_badge = f"<span class='sport-badge sport-{sport.lower()}'>{sport}</span>"
                html += f"""
            <div class="edge">
                <div class="game">{edge['game']}{sport_badge}</div>
                <div class="team">{edge['team']}</div>
                <div class="row">
                    <span class="label">Kalshi:</span>
                    <span class="value">${edge['kalshi_price']:.2f} → ${edge['kalshi_price_after_fees']:.4f} after fees ({edge['kalshi_prob_after_fees']:.2f}%)</span>
                </div>
                <div class="row">
                    <span class="label">FanDuel Hedge:</span>
                    <span class="value">{edge['opposite_team']} at {edge['fanduel_opposite_odds']:.2f} ({edge['fanduel_opposite_prob']:.1f}%)</span>
                </div>
                <div class="row">
                    <span class="label">Total Probability:</span>
                    <span class="value">{edge['total_implied_prob']:.2f}%</span>
                </div>
                <div class="row">
                    <span class="label">Arbitrage Profit:</span>
                    <span class="positive">{edge['arbitrage_profit']:.2f}% GUARANTEED</span>
                </div>
                <div class="method">💡 {edge['recommendation']}</div>
            </div>
            """
        else:
            html += """
            <div class="no-arb">
                <p>🔍 All markets are currently efficient</p>
                <p style="font-size: 0.95em; color: #aaa;">No arbitrage opportunities available right now.</p>
                <p style="font-size: 0.9em; margin-top: 25px; color: #666;">💡 Best times to find arbitrage: during live games (7-10 PM ET)</p>
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
