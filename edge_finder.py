"""
Edge Finder Logic Module
Core functionality for finding betting edges
"""

import requests
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class EdgeOpportunity:
    """Represents a betting edge opportunity"""
    event_name: str
    kalshi_market: str
    kalshi_price: float
    kalshi_implied_prob: float
    fanduel_odds: float
    fanduel_implied_prob: float
    edge_percentage: float
    expected_value: float
    recommendation: str
    bet_amount: float = 10.0
    timestamp: str = ""


class OddsConverter:
    """Convert between different odds formats"""
    
    @staticmethod
    def american_to_implied_prob(american_odds: float) -> float:
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


class TheOddsAPI:
    """Wrapper for The Odds API"""
    
    BASE_URL = "https://api.the-odds-api.com/v4"
    
    def __init__(self, api_key: Optional[str]):
        self.api_key = api_key
        self.session = requests.Session()
    
    def get_fanduel_odds(self) -> Dict[str, float]:
        """Get FanDuel odds across multiple sports"""
        if not self.api_key:
            return self._get_mock_odds()
        
        sports = ['basketball_nba', 'americanfootball_nfl', 'icehockey_nhl', 'baseball_mlb']
        all_odds = {}
        
        for sport in sports:
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
                games = response.json()
                
                for game in games:
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
            
            except Exception as e:
                print(f"Error fetching {sport}: {e}")
                continue
        
        return all_odds if all_odds else self._get_mock_odds()
    
    def _get_mock_odds(self) -> Dict[str, float]:
        """Mock data for testing"""
        return {
            "Lakers": -150,
            "Celtics": +130,
            "Warriors": -200,
            "Heat": +180,
        }


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
    
    def get_sports_markets(self) -> List[Dict]:
        """Get sports-related markets"""
        url = f"{self.base_url}/markets"
        params = {'limit': 200, 'status': 'open'}
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            markets = response.json().get('markets', [])
            
            # Filter for sports
            sports_keywords = ['nba', 'nfl', 'nhl', 'mlb', 'championship', 'playoff']
            return [
                m for m in markets
                if any(kw in m.get('title', '').lower() for kw in sports_keywords)
            ]
        except:
            return []
    
    def get_orderbook(self, ticker: str) -> Optional[Dict]:
        """Get orderbook for market"""
        url = f"{self.base_url}/markets/{ticker}/orderbook"
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except:
            return None


class EdgeFinder:
    """Main edge finding logic"""
    
    def __init__(self, odds_api_key: Optional[str] = None,
                 kalshi_api_key: Optional[str] = None,
                 min_edge: float = 10.0):
        self.odds_api = TheOddsAPI(odds_api_key)
        self.kalshi = KalshiAPI(kalshi_api_key)
        self.min_edge = min_edge
        self.converter = OddsConverter()
    
    def find_edges(self, bet_amount: float = 10.0) -> List[EdgeOpportunity]:
        """Find all edges meeting threshold"""
        edges = []
        
        # Get data from both platforms
        fanduel_odds = self.odds_api.get_fanduel_odds()
        kalshi_markets = self.kalshi.get_sports_markets()
        
        for market in kalshi_markets:
            ticker = market.get('ticker', '')
            title = market.get('title', '')
            
            # Get orderbook
            orderbook = self.kalshi.get_orderbook(ticker)
            if not orderbook:
                continue
            
            yes_asks = orderbook.get('orderbook', {}).get('yes', [])
            if not yes_asks:
                continue
            
            # Best ask price
            kalshi_price = min(yes_asks, key=lambda x: x[0])[0] / 100
            kalshi_prob = kalshi_price
            
            # Match with FanDuel
            matched_odds = self._match_event(title, fanduel_odds)
            if matched_odds is None:
                continue
            
            fanduel_prob = self.converter.american_to_implied_prob(matched_odds)
            edge = self.converter.calculate_edge(fanduel_prob, kalshi_prob)
            
            if edge >= self.min_edge:
                payout_if_win = 1.0 - kalshi_price
                ev = fanduel_prob * payout_if_win - (1 - fanduel_prob) * kalshi_price
                ev_dollars = ev * bet_amount
                
                edges.append(EdgeOpportunity(
                    event_name=title,
                    kalshi_market=ticker,
                    kalshi_price=kalshi_price,
                    kalshi_implied_prob=kalshi_prob * 100,
                    fanduel_odds=matched_odds,
                    fanduel_implied_prob=fanduel_prob * 100,
                    edge_percentage=edge,
                    expected_value=ev_dollars,
                    recommendation=f"Buy YES at ${kalshi_price:.2f} on Kalshi",
                    bet_amount=bet_amount,
                    timestamp=datetime.now().isoformat()
                ))
        
        return edges
    
    def _match_event(self, kalshi_title: str, fanduel_odds: Dict) -> Optional[float]:
        """Match Kalshi event with FanDuel odds"""
        # Try exact match
        if kalshi_title in fanduel_odds:
            return fanduel_odds[kalshi_title]
        
        # Keyword matching
        kalshi_words = set(kalshi_title.lower().split())
        for fd_event, odds in fanduel_odds.items():
            fd_words = set(fd_event.lower().split())
            overlap = kalshi_words & fd_words
            if len(overlap) >= 2:
                return odds
        
        return None
