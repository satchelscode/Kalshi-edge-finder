// Kalshi Edge Finder - Frontend JavaScript WITH DEBUG INFO

let scanInterval = null;

async function startScan() {
    const btn = document.getElementById('scan-btn');
    const loading = document.getElementById('loading');
    const edgesContainer = document.getElementById('edges-container');
    
    btn.disabled = true;
    btn.textContent = '⏳ Scanning...';
    loading.style.display = 'block';
    edgesContainer.innerHTML = '';
    
    try {
        const response = await fetch('/api/scan', {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.status === 'scanning') {
            pollForResults();
        } else {
            showError(data.message);
        }
    } catch (error) {
        showError('Failed to start scan: ' + error.message);
        btn.disabled = false;
        btn.textContent = '🔍 Scan for Edges';
        loading.style.display = 'none';
    }
}

function pollForResults() {
    scanInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/edges');
            const data = await response.json();
            
            if (!data.scanning) {
                clearInterval(scanInterval);
                displayResults(data);
                
                const btn = document.getElementById('scan-btn');
                btn.disabled = false;
                btn.textContent = '🔍 Scan for Edges';
                document.getElementById('loading').style.display = 'none';
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, 2000);
}

function displayResults(data) {
    const edgesContainer = document.getElementById('edges-container');
    const lastScan = document.getElementById('last-scan');
    
    lastScan.textContent = data.last_scan || 'Just now';
    
    if (data.edges && data.edges.length > 0) {
        let html = `<h2>✅ Found ${data.edges.length} Edge(s)!</h2>`;
        
        data.edges.forEach((edge, index) => {
            html += createEdgeCard(edge, index + 1);
        });
        
        edgesContainer.innerHTML = html;
    } else {
        // Show debug information
        edgesContainer.innerHTML = createDebugDisplay(data);
    }
}

function createDebugDisplay(data) {
    const debug = data.debug || {};
    
    return `
        <div class="no-edges">
            <h2>❌ No Edges Found</h2>
            <p>Searched for edges ≥ ${data.min_edge}%</p>
            
            <div class="debug-box">
                <h3>🔍 Debug Information</h3>
                
                <div class="debug-section">
                    <h4>📊 Data Collection:</h4>
                    <ul>
                        <li><strong>Total Kalshi markets:</strong> ${debug.kalshi_markets_total || 0}</li>
                        <li><strong>Sports markets:</strong> ${debug.kalshi_markets_sports || 0}</li>
                        <li><strong>FanDuel odds collected:</strong> ${debug.fanduel_odds_total || 0}</li>
                        <li><strong>Successfully matched:</strong> ${debug.matches_found || 0}</li>
                    </ul>
                </div>
                
                ${debug.kalshi_markets_list && debug.kalshi_markets_list.length > 0 ? `
                <div class="debug-section">
                    <h4>📝 Sample Kalshi Markets:</h4>
                    <ul class="market-list">
                        ${debug.kalshi_markets_list.slice(0, 10).map(m => `<li>${m}</li>`).join('')}
                    </ul>
                </div>
                ` : ''}
                
                ${debug.fanduel_teams && debug.fanduel_teams.length > 0 ? `
                <div class="debug-section">
                    <h4>🏈 Sample FanDuel Teams:</h4>
                    <ul class="market-list">
                        ${debug.fanduel_teams.slice(0, 10).map(t => `<li>${t}</li>`).join('')}
                    </ul>
                </div>
                ` : ''}
                
                ${debug.match_details && debug.match_details.length > 0 ? `
                <div class="debug-section">
                    <h4>🎯 Matched Events (All Edges):</h4>
                    <table class="match-table">
                        <tr>
                            <th>Kalshi Market</th>
                            <th>Kalshi Price</th>
                            <th>FanDuel Odds</th>
                            <th>Edge %</th>
                        </tr>
                        ${debug.match_details.map(m => `
                            <tr class="${m.edge >= data.min_edge ? 'good-edge' : ''}">
                                <td>${m.kalshi_title}</td>
                                <td>$${m.kalshi_price.toFixed(2)}</td>
                                <td>${formatOdds(m.fanduel_odds)}</td>
                                <td>${m.edge.toFixed(1)}%</td>
                            </tr>
                        `).join('')}
                    </table>
                </div>
                ` : ''}
                
                ${debug.matches_found === 0 ? `
                <div class="debug-section warning">
                    <h4>⚠️ Problem Identified:</h4>
                    <p><strong>No events were matched between FanDuel and Kalshi.</strong></p>
                    <p>This means team/event names aren't matching. Possible reasons:</p>
                    <ul>
                        <li>Different naming formats (e.g., "LA Lakers" vs "Lakers")</li>
                        <li>Different sports being offered</li>
                        <li>Timing - no overlapping games right now</li>
                    </ul>
                </div>
                ` : ''}
                
                ${debug.errors && debug.errors.length > 0 ? `
                <div class="debug-section error">
                    <h4>❌ Errors:</h4>
                    <ul>
                        ${debug.errors.map(e => `<li>${e}</li>`).join('')}
                    </ul>
                </div>
                ` : ''}
            </div>
            
            <div class="info-box" style="margin-top: 30px;">
                <h3>💡 What to do:</h3>
                <ul>
                    <li><strong>If matches_found = 0:</strong> Event names aren't matching. This is the main issue!</li>
                    <li><strong>If matched but edge too small:</strong> Markets are efficient right now</li>
                    <li><strong>Try again:</strong> During game days (tonight, weekends)</li>
                    <li><strong>Lower threshold:</strong> Try MIN_EDGE=0.5 to see all matches</li>
                </ul>
            </div>
        </div>
    `;
}

function createEdgeCard(edge, number) {
    return `
        <div class="edge-card">
            <div class="edge-header">
                <div class="edge-title">
                    <h3>Edge #${number}: ${edge.event_name}</h3>
                    <p class="market-ticker">Market: ${edge.kalshi_market}</p>
                </div>
                <div class="edge-badge">
                    ${edge.edge}% Edge
                </div>
            </div>
            
            <div class="edge-details">
                <div class="detail-box">
                    <div class="label">FanDuel Odds</div>
                    <div class="value">${formatOdds(edge.fanduel_odds)}</div>
                    <div class="label" style="margin-top: 5px;">(${edge.fanduel_prob}% implied)</div>
                </div>
                
                <div class="detail-box">
                    <div class="label">Kalshi Price</div>
                    <div class="value">$${edge.kalshi_price.toFixed(2)}</div>
                    <div class="label" style="margin-top: 5px;">(${edge.kalshi_prob}% implied)</div>
                </div>
                
                <div class="detail-box">
                    <div class="label">Expected Value</div>
                    <div class="value" style="color: ${edge.ev >= 0 ? '#28a745' : '#dc3545'}">
                        ${edge.ev >= 0 ? '+' : ''}$${edge.ev.toFixed(2)}
                    </div>
                    <div class="label" style="margin-top: 5px;">on $${edge.bet_amount.toFixed(0)} bet</div>
                </div>
            </div>
            
            <div class="edge-footer">
                <div class="ev-box">
                    <div class="label">💡 Recommendation</div>
                    <div class="value">Buy YES at $${edge.kalshi_price.toFixed(2)} on Kalshi</div>
                </div>
                
                <div class="edge-actions">
                    <a href="${edge.kalshi_url}" target="_blank" class="btn-small btn-kalshi">
                        Trade on Kalshi →
                    </a>
                </div>
            </div>
            
            <div class="note" style="margin-top: 15px; font-size: 0.85em;">
                ⚠️ <strong>Verify first!</strong> Check both FanDuel and Kalshi to confirm odds before trading.
            </div>
        </div>
    `;
}

function formatOdds(odds) {
    return odds > 0 ? `+${odds}` : `${odds}`;
}

async function refreshEdges() {
    try {
        const response = await fetch('/api/edges');
        const data = await response.json();
        displayResults(data);
    } catch (error) {
        showError('Failed to refresh: ' + error.message);
    }
}

function showError(message) {
    const edgesContainer = document.getElementById('edges-container');
    edgesContainer.innerHTML = `
        <div class="no-edges">
            <h2>❌ Error</h2>
            <p>${message}</p>
        </div>
    `;
}

async function checkStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        const indicator = document.getElementById('api-indicator');
        if (data.has_odds_api) {
            indicator.innerHTML = '<span class="status-good">✓ Connected</span>';
        } else {
            indicator.innerHTML = '<span class="status-warning">⚠ Demo Mode</span>';
        }
        
        if (data.edges_found > 0) {
            refreshEdges();
        }
    } catch (error) {
        console.error('Status check failed:', error);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    checkStatus();
});
