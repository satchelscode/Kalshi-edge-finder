# CLAUDE.md - Kalshi Edge Finder

## Project Overview

Two-part system on Kalshi:
1. **Auto-trades guaranteed markets** — completed props, NHL tied totals (real money, every 15s)
2. **Sends Telegram notifications for +EV edges** — moneylines, spreads, totals, BTTS, tennis, live player props (NO trading, notification only)

**Tech Stack:** Python (Flask backend) + HTML/CSS/JS (frontend)
**Main Entry Point:** `app.py` (contains ALL business logic - ~4600 lines)
**Deployment:** Render.com with GitHub CI/CD

---

## Architecture

### Active Threads (2)

1. **Completed Props Sniper** (`_completed_props_sniper_loop`) — Runs every 15 seconds
   - Completed player props (NBA, NHL) — **AUTO-TRADES**
   - NHL tied game totals — **AUTO-TRADES**
   - Basketball analytically final — DISABLED (not reliable)

2. **Background Scanner** (`_background_scan_loop`) — Runs continuously (~30s rest between scans)
   - Moneyline edges (NBA, NHL, NCAAB, soccer) — **NOTIFICATION ONLY**
   - Spread edges (NBA, NHL, NCAAB) — **NOTIFICATION ONLY**
   - Total edges (NBA, NHL, NCAAB) — **NOTIFICATION ONLY**
   - **Pre-game player prop edges (NBA, NHL) — YES + NO sides — NOTIFICATION ONLY**
   - BTTS edges (soccer) — **NOTIFICATION ONLY**
   - Tennis match-winner edges — **NOTIFICATION ONLY**
   - Live player prop value (FD one-way vs Kalshi) — DISABLED (live data unreliable)
   - Completed props + NHL tied (also here, duplicated from sniper) — **AUTO-TRADES**

### Key Components

- **FanDuelAPI class** — Fetches odds from The Odds API (FanDuel + Pinnacle)
- **KalshiAPI class** — Fetches markets/orderbooks and places orders on Kalshi
- **OrderTracker class** — Tracks positions, prevents betting both sides of same game
- **OddsConverter class** — Handles decimal/American odds conversion
- **_scan_cache** — Thread-safe cache for scan results (displayed on web dashboard)

---

## WHAT AUTO-TRADES vs WHAT ONLY NOTIFIES

### AUTO-TRADES (real money):
- `auto_trade_completed_prop()` — buys completed props and NHL tied totals
- Called from `find_completed_props()` and `find_nhl_tied_game_totals()`
- These are GUARANTEED outcomes — player already hit stat, or NHL game tied (no ties allowed)

### NOTIFICATION ONLY (no money):
- `auto_trade_edge()` — **ALWAYS returns None** (line 543)
- Called from all fair-value edge finders (moneyline, spread, total, BTTS, tennis)
- `find_live_prop_value()` — only calls `send_telegram_notification()`, never trades
- Telegram notifications show: edge %, odds comparison, odds age

### NEVER re-enable auto_trade_edge without explicit instruction!

---

## CRITICAL BUGS TO NEVER REPEAT

### 7. Resolved Market Auto-Trading (COST $900+)
**Bug:** `find_all_resolved_markets()` was auto-buying contracts on games it thought were finished
based on ESPN data. Incorrect NCAAB game matching caused it to buy NO on Albany at $0.01
(~$880 lost across two orders of 35k and 46k contracts).
**Root cause:** This system was running silently in the background via `scan_all_sports()` →
`find_all_resolved_markets()`. It was NEVER intended to be active alongside the completed
props sniper, but both threads were started on boot.
**Resolution:** Entire resolved market system DELETED (~1700 lines). Functions removed:
- `find_all_resolved_markets()` — master orchestrator
- `find_resolved_game_markets()` — ESPN game results → Kalshi auto-buy
- `find_resolved_crypto_markets()` — BTC/ETH price → Kalshi auto-buy
- `find_resolved_econ_markets()` — economic data → Kalshi auto-buy
- `find_resolved_index_markets()` — S&P/Nasdaq → Kalshi auto-buy (2 duplicate copies!)
- `_buy_resolved_market()` — the actual order-placing function
- `_index_sniper_loop()` / `start_index_sniper()` — background thread for index markets
- `_crypto_sniper_loop()` / `start_crypto_sniper()` — background thread for crypto markets
- `_get_game_scores()` — ESPN score fetcher for resolved markets
- `_classify_kalshi_market()` — market classifier for crypto
- `_find_game_for_ticker()` — ticker→game matcher for resolved markets
**Rule:** NEVER add code that auto-trades outside of `auto_trade_completed_prop()`.
Any new auto-trading must be explicitly approved and thoroughly tested.
**Status:** Deleted in Feb 2025 cleanup

### 8. Stale Live Odds from The Odds API
**Bug:** The Odds API is NOT real-time. Live data can be minutes old. System showed Pinnacle
at +240 when FanDuel was actually -145, and FD prop at -227 when actual was -162.
Fake edges appeared because stale data was treated as current.
**Rule:** Live odds staleness window is 15 SECONDS max. Data older than 15s is rejected.
All notifications include "Odds age: Xm ago" so user can verify freshness.
**Status:** Fixed — `are_odds_stale()` uses `timedelta(seconds=15)` for live games

### 9. Moneyline Odds Dict Keyed by Team Name (Wrong Game Lookup)
**Bug:** `get_moneyline()` built a flat dict `{team_name: data}`. If two games in the
2-day window shared a team name, the second would overwrite the first, causing
`find_moneyline_edges()` to compare Kalshi prices against the WRONG game's odds.
**Rule:** Always key odds by `game_id`, not team name. Spreads and totals already did this.
**Status:** Fixed — `odds_dict[game_id] = game_odds` (nested dict)

### 10. bball_final NameError Crashed Sniper Loop
**Bug:** `find_basketball_analytically_final()` was commented out but the print statement
on line 5836 still referenced `bball_final`, causing NameError every time the sniper
found any guaranteed edge. The try/except caught it silently.
**Rule:** When commenting out a feature, also update all references to its variables.
**Status:** Fixed — removed the variable reference from print statement

### 1. Moneyline NO Bets - Wrong Side Comparison
**Bug:** NO bets were comparing against the WRONG FanDuel side, creating fake 224% edges
**Rule:** For "NO on Team A", compare against FD probability of Team A winning
**Status:** Fixed in commit 9093c80

### 2. Cross-Date Game Matching
**Bug:** Same teams playing on different dates could incorrectly match
**Rule:** ALWAYS pass `kalshi_date_str` to matcher, reject games >1 day apart
**Status:** Fixed in commit 769af3c

### 3. NHL Tied Totals Line Parsing (TWO BUGS)
**Bug 1:** Parsed ticker "35" as 35.0 instead of 3.5
**Bug 2:** Bought ALL lower lines instead of ONLY the guaranteed line
**Rule:** Tied X-X → minimum total = 2X+1 → buy ONLY Over (2X+0.5) with strict equality
**Status:** Fixed in commits 2a26ac9 + 1a1ad93

### 4. Completed Props Date Matching
**Rule:** ALWAYS validate ticker date vs player game date, both teams in ticker's game code

### 5. Weather/Economic Market Misclassification
**Bug:** Range markets treated as "above X"
**Rule:** Check for range structure, never default unknown to "above"

### 6. Overtime Causes False Analytically Final (COST REAL MONEY)
**Bug:** Negative `seconds_remaining` in OT always triggered "analytically final"
**Rule:** Check `if period > config['quarters']` and handle OT separately
**Status:** Fixed in commit 6eb3c9f

---

## Fair Value Methodology

### Devigged Lines (Moneyline, Spread, Total, BTTS)
- **Pre-game:** FanDuel + Pinnacle combined → multiplicative devig → consensus average
- **Live:** Pinnacle only → devig (FD live data too unreliable through The Odds API)
- **Formula:** `fair_A = implied_A / (implied_A + implied_B)` (normalize to remove vig)
- **Edge:** `total_implied = kalshi_eff + fd_opposite_fair_prob; if < 1.0 → edge`

### Pre-game Player Props (YES + NO, Devigged)
- FanDuel + Pinnacle Over/Under for each player/threshold → multiplicative devig
- **Both sides compared** against Kalshi orderbook:
  - YES edge: `kalshi_yes_eff + fair_under < 1.0`
  - NO edge: `kalshi_no_eff + fair_over < 1.0`
- Kalshi thresholds map to API points: "20+" = Over 19.5 (`point = threshold - 0.5`)
- Stats covered: Points, Rebounds, Assists, 3PM (NBA); Points, Assists, Saves (NHL)
- Uses `PLAYER_PROP_SPORTS` config for series tickers
- All stat types fetched in one API call per game (saves API quota)

### Live Player Props — DISABLED
- Was: FanDuel one-way Over vs Kalshi YES (no devigging)
- Disabled because The Odds API live data is unreliable

### Staleness & Data Quality
- Live data from The Odds API must be < 15 seconds old
- All notifications include "Odds age" timestamp
- Pre-game data has no staleness requirement
- **Cross-book divergence check:** If FanDuel and Pinnacle devigged probs differ by >10pp,
  the edge is rejected. Catches secretly-live games where API reports wrong commence_time
  (e.g., WTA match already started but API said pre-game, FD at -111 vs Pinnacle at +157).

---

## Configuration Constants

```python
AUTO_TRADE_ENABLED = True
MAX_POSITIONS = 999
MIN_EDGE_PERCENT = 2.0             # Only notify/display edges >= 2% over fair value
LIVE_PROP_MIN_EDGE = 5.0           # Live props need 5%+ (noisier one-way comparison)
MAX_BOOK_DIVERGENCE = 0.10         # Reject edge if books disagree by >10 percentage points
COMPLETED_PROP_MAX_PRICE = 1.00    # Buy any completed prop < $1.00
SCAN_REST_SECONDS = 30             # Rest between background scans

# Books used for fair value
PREGAME_BOOKS = ['fanduel', 'pinnacle']
LIVE_BOOK = 'pinnacle'
```

---

## Telegram Notifications

Two formats:

### Devigged Edge (moneyline/spread/total/BTTS/tennis)
```
+EV OPPORTUNITY (NBA - Moneyline LIVE)
Game Name
Devigged Fair Lines (live/pinnacle):
  Consensus fair (opposite): +240
  pinnacle: +240
Kalshi: YES on Team @ $0.60
Kalshi after fees: -161
Edge: 9.81%
Odds age: 12s ago
Would bet: YES TICKER @ 60c
```

### Live Prop (direct one-way comparison)
```
+EV OPPORTUNITY (NBA Points - Live Prop)
Game Name
FanDuel Live Over: -227 (69.4%)
Kalshi YES: Player 25+ @ $0.60
Kalshi after fees: -150 (60.0%)
Difference: 9.40%
Odds age: 8s ago
Would bet: YES TICKER @ 60c
```

---

## Environment Variables Required

```bash
KALSHI_API_KEY_ID         # Kalshi username or API key ID
KALSHI_PRIVATE_KEY        # RSA private key (PEM format, newlines = \n)
ODDS_API_KEY              # The Odds API key (for FanDuel/Pinnacle data)
TELEGRAM_BOT_TOKEN        # Optional: notifications
TELEGRAM_CHAT_ID          # Optional: notification target
```

---

## File Structure

```
/app.py              - ALL business logic (~4600 lines)
/edge_finder.py      - Legacy/unused (not imported)
/templates/          - Frontend HTML
/static/             - CSS/JS assets
/requirements.txt    - Dependencies
/CLAUDE.md           - This file
```

---

## Code Sections in app.py (line numbers approximate)

| Lines | Section | Status |
|-------|---------|--------|
| 1-180 | Imports, constants, config dicts | ACTIVE |
| 180-540 | Utility functions, telegram, `auto_trade_edge` (returns None) | ACTIVE |
| 540-700 | OddsConverter, prob_to_american, devig functions | ACTIVE |
| 700-1090 | FanDuelAPI: get_moneyline, get_spreads, get_totals, get_btts | ACTIVE |
| 1090-1300 | FanDuelAPI: get_fd_live_props | ACTIVE |
| 1300-1540 | KalshiAPI class | ACTIVE |
| 1540-1660 | OrderTracker, get_best_yes/no_price | ACTIVE |
| 1660-1920 | find_moneyline_edges (2-way + 3-way) | ACTIVE (notify only) |
| 1920-2100 | find_spread_edges | ACTIVE (notify only) |
| 2100-2280 | find_total_edges | ACTIVE (notify only) |
| 2280-2380 | find_live_prop_value | DISABLED (live data unreliable) |
| 2380-2530 | find_pregame_prop_edges (YES + NO) | ACTIVE (notify only) |
| 2530-2700 | find_btts_edges | ACTIVE (notify only) |
| 2700-2900 | find_tennis_edges | ACTIVE (notify only) |
| 2820-3600 | Completed props infrastructure (ESPN, box scores) | ACTIVE (auto-trades) |
| 3600-3800 | find_basketball_analytically_final | DISABLED (not called) |
| 3800-3990 | auto_trade_completed_prop | ACTIVE (auto-trades) |
| 3990-4050 | Completed props sniper loop | ACTIVE |
| 4050-4140 | scan_all_sports (main scanner) | ACTIVE |
| 4140-4200 | Background scanner thread | ACTIVE |
| 4200-end | Flask routes, debug dashboard | ACTIVE |

---

## DELETED CODE (Feb 2025 Cleanup)

The following was removed to prevent unintended auto-trading:

| What | Lines Removed | Why |
|------|---------------|-----|
| `find_all_resolved_markets()` | ~40 lines | Master orchestrator for all resolved market trading |
| `find_resolved_game_markets()` | ~300 lines | ESPN game results → auto-buy on Kalshi |
| `find_resolved_crypto_markets()` | ~200 lines | BTC/ETH price → auto-buy on Kalshi |
| `find_resolved_econ_markets()` | ~120 lines | Economic data → auto-buy on Kalshi |
| `find_resolved_index_markets()` (x2) | ~400 lines | S&P/Nasdaq → auto-buy (had TWO duplicate copies!) |
| `_buy_resolved_market()` | ~100 lines | The actual order-placing function |
| `_index_sniper_loop()` / `start_index_sniper()` | ~90 lines | Background thread for index auto-trading |
| `_crypto_sniper_loop()` / `start_crypto_sniper()` | ~85 lines | Background thread for crypto auto-trading |
| `_get_game_scores()` | ~70 lines | ESPN score fetcher for resolved markets |
| `_classify_kalshi_market()` | ~90 lines | Market classifier for crypto |
| `_find_game_for_ticker()` | ~80 lines | Ticker→game matcher |
| `ESPN_TO_KALSHI` / `ESPN_TO_KALSHI_SOCCER` | ~20 lines | Team abbreviation mappings for resolved markets |
| `RESOLVED_GAME_SPORTS` config | ~60 lines | Sport configs for resolved market scanning |
| `find_player_prop_edges()` | ~170 lines | Devigged player prop edge finder (replaced by live prop value) |
| `get_player_props()` (FanDuelAPI method) | ~140 lines | Multi-book player prop fetcher (replaced by get_fd_live_props) |
| `auto_trade_edge()` dead code | ~100 lines | Unreachable code after `return None` |

**Total: ~2,100 lines removed**

---

## DO's and DON'Ts

### DO:
- Always validate dates when matching games across platforms
- Use strict equality (`abs(x - y) < 0.01`) for line comparisons
- Check BOTH team names appear in ticker when matching props
- Account for Kalshi's 7% fee in all edge calculations
- Use Eastern Time for all market time comparisons
- Include odds age in all notifications
- Reject live data older than 15 seconds

### DON'T:
- **NEVER add auto-trading code without explicit approval**
- Never assume "NO on Team A" means compare against Team B's odds
- Never buy multiple lines when only ONE line is guaranteed (tied totals)
- Never match games without date validation
- Never default unknown market types to "above" or "below"
- Never trust stale odds from in-progress games (15s max for live)
- Never key odds dicts by team name (use game_id to avoid cross-game collisions)
