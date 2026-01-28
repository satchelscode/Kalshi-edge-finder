"""
Kalshi Edge Finder - NBA FOCUSED VERSION
Matches NBA sides, totals, moneylines, and player props between FanDuel and Kalshi
"""

from flask import Flask, render_template, jsonify
import requests
import os
from datetime import datetime
from typing import Dict, List, Optional
import threading
import time
import re

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
    """Wrapper for Kalshi API - NBA focused"""
    
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
        
    def get_markets(self, limit: int = 200, status: str = "open") -> List[Dict]:
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
            return None
    
    def get_nba_markets(self) -> List[Dict]:
        """Get NBA-specific markets only"""
        all_markets = self.get_markets(limit=200)
        
        nba_keywords = ['nba', 'lakers', 'warriors', 'celtics', 'bulls', 'heat', 
                       'knicks', 'nets', 'sixers', '76ers', 'bucks', 'cavaliers',
                       'mavericks', 'rockets', 'spurs', 'suns', 'clippers', 'kings',
                       'trail blazers', 'nuggets', 'timberwolves', 'thunder', 'jazz',
                       'grizzlies', 'pelicans', 'hornets', 'magic', 'hawks', 'wizards',
                       'pistons', 'pacers', 'raptors', 'lebron', 'curry', 'durant',
                       'points', 'rebounds', 'assists', 'basketball']
        
        nba_markets = []
        for market in all_markets:
            title = market.get('title', '').lower()
            subtitle = market.get('subtitle', '').lower()
            
            # Must contain NBA keyword
            if any(keyword in title or keyword in subtitle for keyword in nba_keywords):
                # Exclude non-sports (politics, economics, etc.)
                exclude_keywords = ['president', 'election', 'congress', 'senate', 
                                   'inflation', 'gdp', 'unemployment', 'fed', 'rate']
                if not any(ex in title or ex in subtitle for ex in exclude_keywords):
                    nba_markets.append(market)
        
        return nba_markets


class TheOddsAPI:
    """Wrapper for The Odds API - NBA focused"""
    
    BASE_URL = "https://api.the-odds-api.com/v4"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.session = requests.Session()
    
    def get_nba_odds(self) -> Dict[str, Dict]:
        """Get comprehensive NBA odds from FanDuel"""
        if not self.api_key:
            return self._get_mock_nba_odds()
        
        all_odds = {}
        
        # Get moneylines (h2h)
        moneylines = self._get_odds_for_market('basketball_nba', 'h2h')
        self._parse_odds(moneylines, all_odds, 'moneyline')
        
        # Get spreads
        spreads = self._get_odds_for_market('basketball_nba', 'spreads')
        self._parse_odds(spreads, all_odds, 'spread')
        
        # Get totals
        totals = self._get_odds_for_market('basketball_nba', 'totals')
        self._parse_odds(totals, all_odds, 'total')
        
        # Get player props if available
        player_props = self._get_odds_for_market('basketball_nba', 'player_points')
        self._parse_odds(player_props, all_odds, 'player_prop')
        
        time.sleep(0.5)  # Rate limiting
        
        return all_odds
    
    def _get_odds_for_market(self, sport: str, market: str) -> List[Dict]:
        """Get odds for specific market type"""
        if not self.api_key:
            return []
        
        url = f"{self.BASE_URL}/sports/{sport}/odds"
        params = {
            'apiKey': self.api_key,
            'regions': 'us',
            'markets': market,
            'bookmakers': 'fanduel',
            'oddsFormat': 'american'
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching {market} odds: {e}")
            return []
    
    def _parse_odds(self, games_data: List[Dict], all_odds: Dict, market_type: str):
        """Parse odds data into structured format"""
        for game in games_data:
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
                        
                        # Create multiple key formats for matching
                        keys = [
                            team,
                            f"{team} Win",
                            f"{team} to win",
                            f"{away} at {home}" if team == home else f"{home} at {away}",
                        ]
                        
                        # Add spread/total specific keys
                        if point:
                            keys.append(f"{team} {point:+.1f}")
                            keys.append(f"{team} spread {point:+.1f}")
                        
                        for key in keys:
                            all_odds[key] = {
                                'odds': price,
                                'type': market_type,
                                'team': team,
                                'matchup': f"{away} @ {home}",
                                'point': point
                            }
    
    def _get_mock_nba_odds(self) -> Dict[str, Dict]:
        """Mock NBA odds for testing"""
        return {
            "Lakers": {'odds': -150, 'type': 'moneyline', 'team': 'Lakers', 'matchup': 'Celtics @ Lakers'},
            "Lakers Win": {'odds': -150, 'type': 'moneyline', 'team': 'Lakers', 'matchup': 'Celtics @ Lakers'},
            "Celtics": {'odds': +130, 'type': 'moneyline', 'team': 'Celtics', 'matchup': 'Celtics @ Lakers'},
            "Celtics Win": {'odds': +130, 'type': 'moneyline', 'team': 'Celtics', 'matchup': 'Celtics @ Lakers'},
            "Warriors": {'odds': -200, 'type': 'moneyline', 'team': 'Warriors', 'matchup': 'Heat @ Warriors'},
            "Warriors Win": {'odds': -200, 'type': 'moneyline', 'team': 'Warriors', 'matchup': 'Heat @ Warriors'},
        }


def extract_nba_teams(text: str) -> List[str]:
    """Extract NBA team names from text"""
    nba_teams = [
        'lakers', 'warriors', 'celtics', 'bulls', 'heat', 'knicks', 'nets',
        'sixers', '76ers', 'bucks', 'cavaliers', 'mavericks', 'rockets',
        'spurs', 'suns', 'clippers', 'kings', 'blazers', 'nuggets',
        'timberwolves', 'thunder', 'jazz', 'grizzlies', 'pelicans',
        'hornets', 'magic', 'hawks', 'wizards', 'pistons', 'pacers', 'raptors'
    ]
    
    text_lower = text.lower()
    found_teams = []
    
    for team in nba_teams:
        if team in text_lower:
            found_teams.append(team)
    
    return found_teams


def match_nba_event(kalshi_title: str, fanduel_odds: Dict) -> Optional[Dict]:
    """Match Kalshi NBA event with FanDuel odds"""
    
    # Direct match first
    for fd_key, fd_data in fanduel_odds.items():
        if kalshi_title.lower() in fd_key.lower() or fd_key.lower() in kalshi_title.lower():
            return fd_data
    
    # Extract teams from Kalshi title
    kalshi_teams = extract_nba_teams(kalshi_title)
    
    if not kalshi_teams:
        return None
    
    # Look for matching teams in FanDuel
    for fd_key, fd_data in fanduel_odds.items():
        fd_teams = extract_nba_teams(fd_key)
        
        # If we have team overlap, it's likely a match
        overlap = set(kalshi_teams) & set(fd_teams)
        if overlap:
            return fd_data
    
    return None


def find_edges() -> tuple[List[Dict], Dict]:
    """Find NBA betting edges"""
    global scan_in_progress
    
    scan_in_progress = True
    edges = []
    debug = {
        'kalshi_markets_total': 0,
        'kalshi_markets_nba': 0,
        'kalshi_markets_list': [],
        'fanduel_odds_total': 0,
        'fanduel_matchups': [],
        'matches_found': 0,
        'match_details': [],
        'errors': []
    }
    
    try:
        converter = OddsConverter()
        kalshi = KalshiAPI(api_key=KALSHI_API_KEY)
        odds_api = TheOddsAPI(api_key=ODDS_API_KEY)
        
        # Get NBA data only
        fanduel_odds = odds_api.get_nba_odds()
        debug['fanduel_odds_total'] = len(fanduel_odds)
        debug['fanduel_matchups'] = list(set([v.get('matchup', '') for v in fanduel_odds.values() if v.get('matchup')]))[:10]
        
        # Get Kalshi NBA markets
        all_markets = kalshi.get_markets(limit=200)
        debug['kalshi_markets_total'] = len(all_markets)
        
        markets = kalshi.get_nba_markets()
        debug['kalshi_markets_nba'] = len(markets)
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
            matched = match_nba_event(title, fanduel_odds)
            
            if matched:
                debug['matches_found'] += 1
                
                fanduel_odds_value = matched['odds']
                fanduel_prob = converter.american_to_implied_prob(fanduel_odds_value)
                edge = converter.calculate_edge(fanduel_prob, kalshi_prob)
                
                match_info = {
                    'kalshi_title': title,
                    'kalshi_price': kalshi_price,
                    'fanduel_odds': fanduel_odds_value,
                    'fanduel_matchup': matched.get('matchup', ''),
                    'market_type': matched.get('type', 'unknown'),
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
        'mode': 'NBA_FOCUSED'
    })


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
