# CLAUDE.md - Kalshi Edge Finder

## Project Overview

This scanner focuses **exclusively on guaranteed markets** on Kalshi — outcomes that are already determined but still have contracts available for purchase. No FanDuel arbitrage, no probability-based edges.

**Tech Stack:** Python (Flask backend) + HTML/CSS/JS (frontend)
**Main Entry Point:** `app.py` (contains ALL business logic - ~6000 lines)
**Deployment:** Render.com with GitHub CI/CD

---

## CURRENT FOCUS: Guaranteed Markets Only

The system now ONLY scans for these three types of guaranteed money:

1. **Completed Props** - Player has ALREADY hit their stat target (e.g., player has 25 pts, market is Over 22.5)
2. **NHL Tied Totals** - Tied NHL games where the over is guaranteed (no ties in NHL = OT until winner)
3. **Basketball Analytically Final** - Games where Haslametrics formula says outcome is locked

**Everything else is DISABLED** — no FanDuel arb scanning, no crypto, no index, no probability edges.

---

## Architecture

### Active Thread (1 only)

**Completed Props Sniper** (`_completed_props_sniper_loop`) - Runs every 15 seconds, scans ONLY guaranteed markets:
- Completed player props (NBA, NHL)
- NHL tied game totals
- Basketball analytically final

### Disabled Threads

- `_background_scan_loop` - DISABLED (was FanDuel arb scanning)
- `_crypto_sniper_loop` - DISABLED
- `_index_sniper_loop` - DISABLED

### Key Components

- **OrderTracker class** - Tracks positions, prevents betting both sides of same game
- **OddsConverter class** - Handles decimal/American odds conversion and edge calculations
- **_scan_cache** - Thread-safe cache for scan results

---

## CRITICAL BUGS TO NEVER REPEAT

### 1. Moneyline NO Bets - Wrong Side Comparison
**Bug:** NO bets were comparing against the WRONG FanDuel side, creating fake 224% edges
**Example:** "NO on Knicks" = "Wizards win", but was comparing against Wizards FD prob instead of Knicks FD prob
**Rule:** For "NO on Team A", compare against FD probability of Team A winning (the losing outcome)
**Status:** Fixed in commit 9093c80

### 2. Cross-Date Game Matching
**Bug:** Same teams playing on different dates could incorrectly match
**Example:** Feb 2 Kalshi market matching Feb 4 FanDuel odds for same teams
**Rule:** ALWAYS pass `kalshi_date_str` to matcher, reject games >1 day apart
**Status:** Fixed in commit 769af3c

### 3. NHL Tied Totals Line Parsing (TWO BUGS)
**Bug 1:** Parsed ticker "35" as 35.0 instead of 3.5 (floor_strike handling)
**Bug 2:** Bought ALL lower lines instead of ONLY the guaranteed line
**Rule:** Tied X-X → minimum total = 2X+1 → buy ONLY Over (2X+0.5)
- Tied 1-1 → guaranteed Over 2.5 ONLY (not 2.5, 3.5, 4.5...)
- Tied 2-2 → guaranteed Over 4.5 ONLY
- Tied 3-3 → guaranteed Over 6.5 ONLY

**Critical:** Use strict equality: `if abs(line - target_line) < 0.01`
**Status:** Fixed in commits 2a26ac9 + 1a1ad93

### 4. Completed Props Date Matching
**Risk:** Matching yesterday's FINAL stats to today's markets
**Example:** Bam Adebayo 21 pts from Jan 31 MIA@CHI matching Feb 1 MIA@CHI
**Rule:** ALWAYS validate:
- Ticker date vs player game date
- Both game teams appear in ticker's game code
- Log skipped matches

### 5. Weather/Economic Market Misclassification
**Bug:** Range markets (e.g., "74° to 75°") treated as "above 74"
**Rule:** Check for range structure (`cap_strike != floor_strike`), never default unknown to "above"
**Status:** Fixed in commit 8c1d350

### 6. Overtime Causes False Analytically Final (COST REAL MONEY)
**Bug:** During overtime, `period > quarters` makes `periods_remaining` negative, which makes `seconds_remaining` negative. Negative time is ALWAYS less than `safe_seconds`, so EVERY overtime game was flagged "analytically final" regardless of lead or time.
**Example:** 6-point lead in OT with 2 min left → seconds_remaining = -635 → triggered as "safe" → bought 1922 contracts at $0.80
**Rule:** ALWAYS check `if period > config['quarters']` and handle OT separately — use only current period clock
**Status:** Fixed in commit 6eb3c9f

---

## Important Conventions

### Date/Time
- **ALWAYS use Eastern Time** for market opening times: `ZoneInfo('America/New_York')`
- **Ticker Format:** `KXNBAGAME-26JAN31SASCHA-SAS` where `26JAN31` = date part
- **Two-Day Window:** FanDuel API fetches today + tomorrow for evening/next-day games

### Odds & Fees
```python
# Kalshi fee calculation - 7% on profit side
def kalshi_fee(price: float, contracts: int = 100) -> float:
    return 0.07 * contracts * price * (1 - price)

# Arbitrage formula
# Profitable if: (kalshi_effective_price + fd_opposite_prob) < 1.0
# where: kalshi_effective_price = kalshi_price + kalshi_fee
```

### Game Matching (Three-Tier)
1. Exact team name match from team maps (NBA_TEAMS, NHL_TEAMS, etc.)
2. Keyword overlap (at least 2 common words)
3. Date-aware validation to prevent cross-date mismatches

### Basketball Game Formats (CRITICAL for Analytically Final)
Different leagues have different game lengths - must use correct format to calculate time remaining:

| League | Format | Total Time |
|--------|--------|------------|
| **NBA** | 4 x 12 min quarters | 48 min |
| **WNBA** | 4 x 10 min quarters | 40 min |
| **NCAAB Men** | 2 x 20 min halves | 40 min |
| **NCAAB Women** | 4 x 10 min quarters | 40 min |
| **Euroleague/EuroCup** | 4 x 10 min quarters | 40 min |
| **FIBA (all)** | 4 x 10 min quarters | 40 min |
| **NBL Australia** | 4 x 10 min quarters | 40 min |
| **Japan B League** | 4 x 10 min quarters | 40 min |
| **Korea KBL** | 4 x 10 min quarters | 40 min |
| **France LNB** | 4 x 10 min quarters | 40 min |
| **Argentina Liga** | 4 x 10 min quarters | 40 min |
| **Unrivaled** | 4 x 10 min quarters | 40 min |

**Note:** International leagues may not have ESPN coverage - scanner silently skips them if no data available.

---

## Configuration Constants

```python
AUTO_TRADE_ENABLED = True
MAX_POSITIONS = 999                # No practical limit
MIN_EDGE_PERCENT = 0.5             # Skip sub-0.5% edges (fee slippage)
TARGET_PROFIT = $5.00              # per FanDuel arb trade
MAX_RISK = $250.00                 # max cost per order

# Crypto & Index (higher conviction)
CRYPTO_TARGET_PROFIT = $15.00
CRYPTO_MAX_RISK = $1,000.00
INDEX_TARGET_PROFIT = $15.00
INDEX_MAX_RISK = $1,000.00

COMPLETED_PROP_MAX_PRICE = 1.00    # Buy any completed prop < $1.00
```

---

## Current Trading Status (as of Feb 2025)

### ACTIVE (Guaranteed Markets Only)
- **Completed Props Scanner:** ACTIVE - scans every 15s
- **NHL Tied Totals Scanner:** ACTIVE - runs within completed props loop
- **Basketball Analytically Final:** ACTIVE - runs within completed props loop
- **Auto-Trading for Guaranteed Props:** ACTIVE (`auto_trade_completed_prop`)

### DISABLED
- **FanDuel Arb Scanning:** DISABLED (main background scanner stopped)
- **FanDuel Arb Auto-Trading:** DISABLED (returns None in `auto_trade_edge`)
- **Crypto Trading:** DISABLED (sniper thread not started)
- **Index Trading:** DISABLED (sniper thread not started)
- **NHL Moneyline/Spread/Total:** DISABLED (commented out in sport configs)

---

## API Rate Limits

- **Kalshi API:** No strict rate limit, but be reasonable
- **ESPN API:** Used for live scores/box scores - no auth needed
- **The Odds API:** NOT USED (FanDuel arb scanning disabled)
- **Scan interval:** 15 seconds between guaranteed market scans

---

## Environment Variables Required

```bash
KALSHI_API_KEY_ID         # Kalshi username or API key ID
KALSHI_PRIVATE_KEY        # RSA private key (PEM format, newlines = \n)
TELEGRAM_BOT_TOKEN        # Optional: notifications
TELEGRAM_CHAT_ID          # Optional: notification target
# ODDS_API_KEY            # NOT NEEDED (FanDuel arb scanning disabled)
```

---

## DO's and DON'Ts

### DO:
- Always validate dates when matching games across platforms
- Use strict equality (`abs(x - y) < 0.01`) for line comparisons
- Check BOTH team names appear in ticker when matching props
- Log skipped matches to debug false negatives
- Account for Kalshi's 7% fee in all edge calculations
- Use Eastern Time for all market time comparisons

### DON'T:
- Never assume "NO on Team A" means compare against Team B's odds
- Never buy multiple lines when only ONE line is guaranteed (tied totals)
- Never match games without date validation
- Never default unknown market types to "above" or "below"
- Never trust stale odds from in-progress games
- Never exceed The Odds API rate limits

---

## File Structure

```
/app.py              - ALL business logic (~6000 lines)
/edge_finder.py      - Legacy/unused
/templates/          - Frontend HTML
/static/             - CSS/JS assets
/requirements.txt    - Dependencies
```

**Note:** `edge_finder.py` is largely unused - all real implementation is in `app.py`

---

## Common Debugging

### False Positive Edges
1. Check if comparing correct FD side (especially for NO bets)
2. Check for date mismatch between platforms
3. Verify fees are included in edge calculation
4. Check if odds are stale (game in progress)

### Missed Opportunities
1. Check rate limiting (The Odds API quota)
2. Verify market is in active sports list
3. Check if team name mapping exists
4. Verify scan loop is running (check `_scan_cache['timestamp']`)

### Position Tracking Issues
1. `has_position()` - checks ticker level
2. `has_game_position()` - checks game level (prevents both sides)
3. Completed props intentionally allow repeated buys

---

## Recent Commit Patterns (for context)

The codebase has evolved toward:
1. **Guaranteed markets only** - disabled all FanDuel arb, crypto, index scanning
2. Single focused scanner (completed props sniper) running every 15s
3. Bug fixes around date matching and line parsing for guaranteed markets
4. Careful position management for auto-trading guaranteed props
