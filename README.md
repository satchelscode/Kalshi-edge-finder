# Kalshi Edge Finder 🎯

**Web app for finding +EV betting opportunities between FanDuel and Kalshi**

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-blue.svg)

## 🚀 Features

- 🔍 **Automatic Edge Detection** - Scans markets and finds profitable opportunities
- 📊 **Real-time Data** - Uses The Odds API for live FanDuel odds
- 🎨 **Beautiful UI** - Clean, responsive web interface
- 🔄 **Auto-scan Mode** - Continuously monitors markets
- 💰 **EV Calculations** - Shows expected value for each opportunity
- 📱 **Mobile Friendly** - Works on any device

## 📸 Screenshot

![Kalshi Edge Finder UI](https://via.placeholder.com/800x400?text=Beautiful+Web+Interface)

## 🛠️ Quick Deploy to Render

### 1. Fork this Repository
Click the "Fork" button at the top of this page.

### 2. Sign up for API Keys

**The Odds API (Required for real data)**
- Go to https://the-odds-api.com
- Sign up for free (500 requests/month)
- Copy your API key

**Kalshi API (Optional)**
- Go to https://kalshi.com
- Settings → API → Generate Key
- Copy your API key

### 3. Deploy to Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com)

1. Go to https://render.com and sign up
2. Click "New +" → "Web Service"
3. Connect your GitHub account
4. Select your forked repository
5. Configure:
   - **Name**: `kalshi-edge-finder`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Instance Type**: Free

### 4. Set Environment Variables in Render

In your Render dashboard, go to "Environment" and add:

```
ODDS_API_KEY=your-odds-api-key-here
KALSHI_API_KEY=your-kalshi-key-here (optional)
MIN_EDGE=10.0
BET_AMOUNT=10.0
SCAN_INTERVAL=300
```

### 5. Deploy!

Click "Create Web Service" and wait ~2 minutes for deployment.

Your app will be live at: `https://kalshi-edge-finder.onrender.com`

## 🏃 Running Locally

### Prerequisites
- Python 3.9+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/kalshi-edge-finder.git
cd kalshi-edge-finder

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export ODDS_API_KEY="your-api-key"
export KALSHI_API_KEY="your-kalshi-key"  # optional
export MIN_EDGE="10.0"
export BET_AMOUNT="10.0"
export SCAN_INTERVAL="300"

# Run the app
python app.py
```

Visit `http://localhost:5000` in your browser.

## 📖 How It Works

1. **Fetch Data**
   - Gets current FanDuel odds via The Odds API
   - Gets Kalshi market prices via Kalshi API

2. **Calculate Edges**
   - Converts odds to implied probabilities
   - Compares FanDuel probability vs Kalshi price
   - Calculates edge percentage and expected value

3. **Alert You**
   - Displays opportunities in beautiful web UI
   - Shows edge %, EV, and recommendations
   - You manually verify and trade

## 🎮 Using the App

### Manual Scan
1. Click "🔍 Scan Now"
2. Wait for results (~10-30 seconds)
3. Review opportunities found
4. Verify odds on both platforms
5. Manually place trades on Kalshi

### Auto-Scan Mode
1. Click "🔄 Enable Auto-Scan"
2. App scans every 5 minutes automatically
3. Check back periodically for new edges
4. Click "⏸️ Disable Auto-Scan" to stop

## ⚙️ Configuration

Edit environment variables in Render dashboard:

| Variable | Description | Default |
|----------|-------------|---------|
| `ODDS_API_KEY` | The Odds API key | Required |
| `KALSHI_API_KEY` | Kalshi API key | Optional |
| `MIN_EDGE` | Minimum edge % to display | 10.0 |
| `BET_AMOUNT` | Bet size for EV calculation | 10.0 |
| `SCAN_INTERVAL` | Auto-scan interval (seconds) | 300 |

## 📊 Understanding the Results

### Edge Percentage
How much better FanDuel's implied probability is vs Kalshi's price.
- **10-15%**: Good opportunity
- **15-25%**: Very good
- **25%+**: Verify carefully (might be error)

### Expected Value (EV)
Average profit per bet if repeated many times.
- **Positive EV**: Good bet on average
- **Negative EV**: Bad bet on average

### Example
```
FanDuel: -150 (60% implied probability)
Kalshi: $0.52 (52% implied probability)
Edge: 15.4%
EV: +$0.92 on $10 bet
```

## ⚠️ Important Disclaimers

### 1. Not Financial Advice
This is a tool, not investment advice. Do your own research.

### 2. Manual Trading Only
This app ALERTS you to opportunities. You must:
- Verify edges are still valid
- Check both platforms manually
- Place trades yourself

### 3. Edge ≠ Guaranteed Profit
- Markets move fast
- Edges can disappear
- Variance exists

### 4. Respect Terms of Service
- Use API responsibly
- Follow rate limits
- Don't manipulate markets

### 5. Risk Management
- Only bet what you can afford to lose
- Start small
- Track your results

## 🔒 Security

**NEVER commit API keys to GitHub!**

✅ Store keys in Render environment variables  
✅ Use `.gitignore` to exclude `.env` files  
❌ Never hardcode keys in code  
❌ Never commit `.env` files  

## 🐛 Troubleshooting

### "No edges found"
- Normal! Edges are rare in efficient markets
- Try during peak times (game days)
- Lower MIN_EDGE threshold
- Enable auto-scan for continuous monitoring

### API Errors
- Check your API keys are correct
- Verify you haven't exceeded rate limits
- The Odds API: 500 requests/month on free tier

### Deployment Issues
- Ensure all environment variables are set in Render
- Check logs in Render dashboard
- Verify `requirements.txt` is complete

## 📈 Roadmap

- [ ] Email/SMS alerts
- [ ] Historical edge tracking
- [ ] Multiple sportsbook comparison
- [ ] Kelly Criterion bet sizing
- [ ] Backtesting results

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

MIT License - feel free to use and modify!

## ⚖️ Legal

This tool is for educational purposes. You are responsible for:
- Complying with all applicable laws
- Following platform terms of service
- Your own trading decisions
- Any losses incurred

**Trade responsibly. Only bet what you can afford to lose.**

## 🙏 Acknowledgments

- [The Odds API](https://the-odds-api.com) - Real-time sports odds data
- [Kalshi](https://kalshi.com) - Event contracts platform
- [Render](https://render.com) - Easy deployment platform

---

**Built with ❤️ for finding edges, not financial advice.**

*Star ⭐ this repo if you found it useful!*
