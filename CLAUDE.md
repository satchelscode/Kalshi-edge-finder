# CLAUDE.md - Kalshi Edge Finder

## Project Overview

Four-part system on Kalshi:
1. **Auto-trades guaranteed markets** — completed props, NHL tied totals (real money, every 15s)
2. **Prop market-making** — places YES/NO orders on pre-game player props based on FanDuel lines (real money, every scan)
3. **Combo (parlay) market-making** — quotes NO on incoming RFQs using Kalshi mid-market pricing (real money, polls every 3s)
4. **Sends Telegram notifications for +EV edges** — moneylines, spreads, totals, BTTS, tennis (NO trading, notification only)

**Tech Stack:** Python (Flask backend) + HTML/CSS/JS (frontend)
**Main Entry Point:** `app.py` (contains ALL business logic - ~5000 lines)
**Deployment:** Render.com with GitHub CI/CD

---

## Architecture

### Active Threads (3)

1. **Completed Props Sniper** (`_completed_props_sniper_loop`) — Runs every 15 seconds
   - Completed player props (NBA, NHL) — **AUTO-TRADES**
   - NHL tied game totals — **AUTO-TRADES**
   - Basketball analytically final — DISABLED (not reliable)

2. **Background Scanner** (`_background_scan_loop`) — Runs continuously (~30s rest between scans)
   - Pre-game player prop comparison (FD one-way vs Kalshi YES/NO) → **`/props` web page + file cache**
   - **Prop market-making** (`manage_prop_orders`) — **AUTO-TRADES** (YES buys + NO limit orders)
   - Moneyline edges (NBA, NHL, NCAAB, UFC, soccer) — **NOTIFICATION ONLY**
   - Spread edges (NBA, NHL, NCAAB) — **NOTIFICATION ONLY**
   - Total edges (NBA, NHL, NCAAB) — **NOTIFICATION ONLY**
   - BTTS edges (soccer) — **NOTIFICATION ONLY**
   - Tennis match-winner edges — **NOTIFICATION ONLY**
   - Live player prop value (FD one-way vs Kalshi) — DISABLED (live data unreliable)
   - Completed props + NHL tied (also here, duplicated from sniper) — **AUTO-TRADES**
   - Prop MM Telegram reporting (30-min status + 9am daily summary)

3. **Combo Market Maker** (`_combo_mm_loop`) — Polls every 3 seconds
   - Polls `GET /communications/rfqs?status=open` for new combo RFQs
   - Calculates fair value from Kalshi mid-market prices of each leg
   - Quotes NO at fair minus 2¢ edge — **AUTO-TRADES**
   - Only quotes NBA (`KXNBA*`) and NCAAB (`KXNCAAMB*`) combos
   - $100 max total exposure, Telegram confirmation on each quote

### Key Components

- **FanDuelAPI class** — Fetches odds from The Odds API (FanDuel + Pinnacle)
- **KalshiAPI class** — Fetches markets/orderbooks and places/cancels orders on Kalshi
- **OrderTracker class** — Tracks positions, prevents betting both sides of same game
- **OddsConverter class** — Handles decimal/American odds conversion
- **_scan_cache** — Thread-safe in-memory cache for scan results (displayed on web dashboard)
- **File-based caches** (`/tmp/`) — Props and bet data shared across gunicorn processes
  - Gunicorn may use separate processes for background thread vs web requests
  - In-memory dicts are NOT shared across processes → use file-based caching
  - Atomic writes via `os.replace()` prevent partial reads

---

## WHAT AUTO-TRADES vs WHAT ONLY NOTIFIES

### AUTO-TRADES (real money):
- `auto_trade_completed_prop()` — buys completed props and NHL tied totals
  - Called from `find_completed_props()` and `find_nhl_tied_game_totals()`
  - These are GUARANTEED outcomes — player already hit stat, or NHL game tied (no ties allowed)
- `manage_prop_orders()` — prop market-making on pre-game player props
  - **YES side:** Buys 1 YES contract at market when FD implied > Kalshi YES by 4+pp
  - **NO side:** Places 1 resting NO limit order at FD's implied NO price, only if top of orderbook
  - Max 1 contract per prop (open + filled combined), no rebuy once filled
  - Bets tracked in `/tmp/propmm_bets.json` for Telegram reporting
- `process_combo_rfq()` — combo (parlay) market-making via RFQ system
  - Polls for open RFQs, calculates fair combo price from individual leg orderbooks
  - **NO side only:** Quotes NO at mid-market fair minus 2¢ edge
  - Uses Kalshi's own prices (no external API) for speed
  - $100 total portfolio exposure cap, auto-reduces contract count to fit
  - Bets tracked in `/tmp/combo_mm_bets.json`

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

### Prop Market-Making (manage_prop_orders)
- FanDuel publishes one-way Over lines on player props (e.g., "LaMelo Ball 4+ Threes at -130")
- FD's implied probability includes ~4-5% vig — they want to be on the NO side
- **NO side:** We mirror FD's position by bidding NO at FD's implied NO price (vig = our edge)
  - Only places if we'd be top of NO orderbook (highest bid)
  - Resting limit order, 1 contract max
- **YES side:** If FD's implied Over exceeds Kalshi's YES ask by 4+pp, buy 1 YES at market
  - Market buy (immediate fill), 1 contract max, no rebuy once filled
- Bets tracked in `/tmp/propmm_bets.json` for Telegram reporting
- `compare_pregame_props()` provides raw orderbook data (`best_no_bid_cents`, `best_yes_bid_cents`)

### Combo (Parlay) Market-Making (process_combo_rfq)
- Polls Kalshi RFQ endpoint for open combo requests
- For each leg: fetches Kalshi orderbook, calculates mid-market YES:
  `mid_yes = (best_yes_bid + (100 - best_no_bid)) / 2 / 100`
- Fair combo YES = product of all leg probabilities (assumes independence)
- Fair combo NO = 1 - combo YES
- Quote: NO bid = fair_no - 2¢, YES bid = fair_yes - 2¢ (effectively NO-only)
- **Correlation risk:** Same-game parlays have correlated legs, making independent
  multiplication underestimate combo YES. Accepted risk with $100 cap for v1.
- Eligible: NBA (KXNBA*) + NCAAB (KXNCAAMB*) only, 2-10 legs

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

# Prop market-making
PROP_MM_ENABLED = True
PROP_MM_EDGE_PP = 0.0              # Match FD exactly for NO bids (FD's vig IS our edge)
PROP_MM_CONTRACTS = 1              # Max 1 contract per prop
PROP_MM_YES_MIN_DIFF = 4.0         # Buy YES if FD implied > Kalshi YES by 4+pp
PROPMM_UPDATE_INTERVAL_MINS = 30   # Telegram status update frequency
PROPMM_MORNING_HOUR_ET = 9         # 9am ET daily W/L summary

# Combo (parlay) market-making
COMBO_MM_ENABLED = True
COMBO_MM_MAX_EXPOSURE = 100.00     # Total $ at risk across all open combo positions
COMBO_MM_EDGE_CENTS = 2            # Quote N cents under fair NO
COMBO_MM_POLL_SECONDS = 3          # Poll for new RFQs every N seconds
COMBO_MM_ELIGIBLE_PREFIXES = ('KXNBA', 'KXNCAAMB')  # NBA + NCAAB

# Books used for fair value
PREGAME_BOOKS = ['fanduel', 'pinnacle']
LIVE_BOOK = 'pinnacle'
```

---

## Telegram Notifications

Four formats:

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

### Prop MM Status (every 30 minutes)
```
PROP MM STATUS (13 active bets)

Filled (11):
  YES Anthony Edwards Assists 4+ @ -113 (+5.5pp)
  YES Deni Avdija Threes 2+ @ -156 (+5.2pp)
  ...

Total invested: $6.37

Resting (2):
  NO Donte DiVincenzo Rebounds 4+ @ +110 (+0.0pp)
```

### Prop MM Daily Summary (9am ET)
```
PROP MM DAILY SUMMARY (Feb 20)

Results: 8W / 5L (62%)
Invested: $6.37
Returned: $8.00
Net P/L: +$1.63
ROI: +25.6%

Winners:
  W Nikola Jokić Points 30+ YES @ +104
Losers:
  L James Harden Threes 3+ YES @ +133
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
/app.py              - ALL business logic (~5000 lines)
/edge_finder.py      - Legacy/unused (not imported)
/templates/          - Frontend HTML
/static/             - CSS/JS assets
/requirements.txt    - Dependencies
/CLAUDE.md           - This file

# Runtime files (shared across gunicorn processes via /tmp)
/tmp/props_cache.json     - FD vs Kalshi prop comparison data (read by /props route)
/tmp/propmm_bets.json     - Tracked prop MM bets (for Telegram reporting)
/tmp/combo_mm_bets.json   - Tracked combo MM quotes/fills (exposure tracking)
```

---

## Code Sections in app.py (line numbers approximate)

| Lines | Section | Status |
|-------|---------|--------|
| 1-180 | Imports, constants, config dicts (incl. PROP_MM_*) | ACTIVE |
| 180-540 | Utility functions, telegram, `auto_trade_edge` (returns None) | ACTIVE |
| 540-700 | OddsConverter, prob_to_american, devig functions | ACTIVE |
| 700-1090 | FanDuelAPI: get_moneyline, get_spreads, get_totals, get_btts | ACTIVE |
| 1090-1300 | FanDuelAPI: get_fd_live_props, get_player_props_pregame | ACTIVE |
| 1300-1540 | KalshiAPI class (incl. cancel_order, _auth_delete) | ACTIVE |
| 1540-1660 | OrderTracker, get_best_yes/no_price | ACTIVE |
| 1660-1920 | find_moneyline_edges (2-way + 3-way) | ACTIVE (notify only) |
| 1920-2100 | find_spread_edges | ACTIVE (notify only) |
| 2100-2280 | find_total_edges | ACTIVE (notify only) |
| 2280-2380 | find_live_prop_value | DISABLED (live data unreliable) |
| 2380-2520 | compare_pregame_props (FD one-way vs Kalshi YES/NO) | ACTIVE (/props page) |
| 2520-2660 | manage_prop_orders (prop MM: YES buys + NO limit orders) | ACTIVE (auto-trades) |
| 2660-2900 | Prop MM bet tracking & Telegram reporting | ACTIVE |
| 2900-3200 | Combo (parlay) MM: RFQ polling, pricing, quoting | ACTIVE (auto-trades) |
| 3200-3400 | find_btts_edges | ACTIVE (notify only) |
| 3100-3300 | find_tennis_edges | ACTIVE (notify only) |
| 3300-4000 | Completed props infrastructure (ESPN, box scores) | ACTIVE (auto-trades) |
| 4000-4200 | find_basketball_analytically_final | DISABLED (not called) |
| 4200-4400 | auto_trade_completed_prop | ACTIVE (auto-trades) |
| 4400-4500 | Completed props sniper loop | ACTIVE |
| 4500-4700 | scan_all_sports (main scanner, incl. prop MM) | ACTIVE |
| 4700-4750 | Background scanner thread (incl. Telegram checks) | ACTIVE |
| 4750-end | Flask routes, /props page, /orders page, debug dashboard | ACTIVE |

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
