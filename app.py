#!/usr/bin/env python3
"""
Kalshi Edge Finder Web App
Flask application for finding betting edges between FanDuel and Kalshi
"""

from flask import Flask, render_template, jsonify, request
import os
import json
from datetime import datetime
from threading import Thread, Lock
import time

# Import our edge finder logic
from edge_finder import EdgeFinder, EdgeOpportunity

app = Flask(__name__)

# Global state
current_edges = []
scan_status = {
    'running': False,
    'last_scan': None,
    'total_scans': 0,
    'edges_found': 0,
    'status_message': 'Ready to scan'
}
state_lock = Lock()

# Background scanning
background_thread = None
auto_scan_enabled = False


def background_scanner():
    """Background thread for automatic scanning"""
    global current_edges, scan_status, auto_scan_enabled
    
    while auto_scan_enabled:
        try:
            with state_lock:
                scan_status['running'] = True
                scan_status['status_message'] = 'Scanning markets...'
            
            # Run edge finder
            finder = EdgeFinder(
                odds_api_key=os.getenv('ODDS_API_KEY'),
                kalshi_api_key=os.getenv('KALSHI_API_KEY'),
                min_edge=float(os.getenv('MIN_EDGE', '10.0'))
            )
            
            edges = finder.find_edges(
                bet_amount=float(os.getenv('BET_AMOUNT', '10.0'))
            )
            
            with state_lock:
                current_edges = edges
                scan_status['running'] = False
                scan_status['last_scan'] = datetime.now().isoformat()
                scan_status['total_scans'] += 1
                scan_status['edges_found'] = len(edges)
                scan_status['status_message'] = f'Found {len(edges)} edge(s)'
            
            # Wait before next scan
            interval = int(os.getenv('SCAN_INTERVAL', '300'))
            time.sleep(interval)
            
        except Exception as e:
            with state_lock:
                scan_status['running'] = False
                scan_status['status_message'] = f'Error: {str(e)}'
            time.sleep(60)  # Wait a minute before retrying


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


@app.route('/api/config')
def get_config():
    """Get current configuration"""
    return jsonify({
        'min_edge': float(os.getenv('MIN_EDGE', '10.0')),
        'bet_amount': float(os.getenv('BET_AMOUNT', '10.0')),
        'scan_interval': int(os.getenv('SCAN_INTERVAL', '300')),
        'has_odds_api_key': bool(os.getenv('ODDS_API_KEY')),
        'has_kalshi_api_key': bool(os.getenv('KALSHI_API_KEY')),
        'auto_scan_enabled': auto_scan_enabled
    })


@app.route('/api/scan', methods=['POST'])
def trigger_scan():
    """Manually trigger a scan"""
    global current_edges, scan_status
    
    try:
        with state_lock:
            scan_status['running'] = True
            scan_status['status_message'] = 'Scanning markets...'
        
        # Run edge finder
        finder = EdgeFinder(
            odds_api_key=os.getenv('ODDS_API_KEY'),
            kalshi_api_key=os.getenv('KALSHI_API_KEY'),
            min_edge=float(os.getenv('MIN_EDGE', '10.0'))
        )
        
        edges = finder.find_edges(
            bet_amount=float(os.getenv('BET_AMOUNT', '10.0'))
        )
        
        with state_lock:
            current_edges = edges
            scan_status['running'] = False
            scan_status['last_scan'] = datetime.now().isoformat()
            scan_status['total_scans'] += 1
            scan_status['edges_found'] = len(edges)
            scan_status['status_message'] = f'Found {len(edges)} edge(s)'
        
        return jsonify({
            'success': True,
            'edges_found': len(edges),
            'message': f'Scan complete. Found {len(edges)} edge(s).'
        })
        
    except Exception as e:
        with state_lock:
            scan_status['running'] = False
            scan_status['status_message'] = f'Error: {str(e)}'
        
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/edges')
def get_edges():
    """Get current edges"""
    with state_lock:
        edges_data = [
            {
                'event_name': edge.event_name,
                'kalshi_market': edge.kalshi_market,
                'kalshi_price': edge.kalshi_price,
                'kalshi_prob': edge.kalshi_implied_prob,
                'fanduel_odds': edge.fanduel_odds,
                'fanduel_prob': edge.fanduel_implied_prob,
                'edge_pct': edge.edge_percentage,
                'expected_value': edge.expected_value,
                'recommendation': edge.recommendation,
                'bet_amount': edge.bet_amount,
                'timestamp': edge.timestamp
            }
            for edge in current_edges
        ]
        
        return jsonify({
            'edges': edges_data,
            'status': scan_status.copy()
        })


@app.route('/api/status')
def get_status():
    """Get scan status"""
    with state_lock:
        return jsonify(scan_status.copy())


@app.route('/api/auto-scan', methods=['POST'])
def toggle_auto_scan():
    """Enable/disable automatic scanning"""
    global auto_scan_enabled, background_thread
    
    data = request.json
    enable = data.get('enable', False)
    
    if enable and not auto_scan_enabled:
        auto_scan_enabled = True
        background_thread = Thread(target=background_scanner, daemon=True)
        background_thread.start()
        return jsonify({'success': True, 'message': 'Auto-scan enabled'})
    
    elif not enable and auto_scan_enabled:
        auto_scan_enabled = False
        return jsonify({'success': True, 'message': 'Auto-scan disabled'})
    
    return jsonify({'success': True, 'message': 'No change'})


@app.route('/health')
def health():
    """Health check endpoint for Render"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})


if __name__ == '__main__':
    # Get port from environment (Render uses PORT env var)
    port = int(os.getenv('PORT', 5000))
    
    # Run the app
    app.run(host='0.0.0.0', port=port, debug=False)
