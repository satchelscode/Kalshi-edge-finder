# 🚀 Render Deployment Guide

## Step-by-Step Instructions for Deploying to Render

### Prerequisites
✅ GitHub account  
✅ Render account (sign up at https://render.com)  
✅ The Odds API key (get free at https://the-odds-api.com)  
✅ Kalshi API key (optional - get at https://kalshi.com)

---

## Step 1: Push Code to GitHub

### 1.1 Create New GitHub Repository
1. Go to https://github.com/new
2. Repository name: `kalshi-edge-finder`
3. Make it **Public** or **Private** (your choice)
4. **DO NOT** initialize with README (we already have one)
5. Click "Create repository"

### 1.2 Push Your Code
```bash
# Navigate to your project folder
cd kalshi-edge-finder

# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit - Kalshi Edge Finder"

# Add remote (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/kalshi-edge-finder.git

# Push to GitHub
git push -u origin main
```

**⚠️ IMPORTANT:** Make sure your API keys are NOT in the code!  
The `.gitignore` file prevents this, but double-check.

---

## Step 2: Deploy to Render

### 2.1 Create Render Account
1. Go to https://render.com
2. Click "Get Started"
3. Sign up with GitHub (recommended)
4. Authorize Render to access your GitHub

### 2.2 Create New Web Service
1. From Render Dashboard, click **"New +"**
2. Select **"Web Service"**
3. Connect your GitHub repository:
   - If first time: Click "Connect account" → Authorize Render
   - Search for `kalshi-edge-finder`
   - Click "Connect"

### 2.3 Configure Service Settings

Fill in the following:

| Field | Value |
|-------|-------|
| **Name** | `kalshi-edge-finder` (or any name you want) |
| **Region** | Choose closest to you (e.g., Oregon USA) |
| **Branch** | `main` |
| **Root Directory** | Leave empty |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn app:app` |

**Instance Type:** 
- Select **"Free"** (great for starting!)
- ⚠️ Free tier sleeps after 15 min of inactivity
- First request after sleep takes ~30 seconds to wake up

### 2.4 Add Environment Variables

Scroll down to **"Environment Variables"** section.

Click **"Add Environment Variable"** for each:

```
Key: ODDS_API_KEY
Value: YOUR_ODDS_API_KEY_HERE
```

```
Key: KALSHI_API_KEY
Value: YOUR_KALSHI_KEY_HERE
```

```
Key: MIN_EDGE
Value: 10.0
```

```
Key: BET_AMOUNT
Value: 10.0
```

```
Key: SCAN_INTERVAL
Value: 300
```

**🔒 Security Note:** These environment variables are encrypted and secure.  
Never put these values in your code!

### 2.5 Deploy!

1. Click **"Create Web Service"** at the bottom
2. Wait 2-5 minutes for deployment
3. Watch the logs for progress

**You'll see:**
```
==> Building...
==> Installing dependencies from requirements.txt
==> Build successful
==> Starting service with gunicorn app:app
==> Service is live!
```

### 2.6 Access Your App

Your app will be live at:
```
https://kalshi-edge-finder.onrender.com
```
(or whatever name you chose)

---

## Step 3: Verify It's Working

### 3.1 Check Homepage
1. Visit your Render URL
2. You should see the Kalshi Edge Finder UI
3. Check "API Status" - should show "🟢 Connected" or "🟡 Partial"

### 3.2 Test Scanning
1. Click **"🔍 Scan Now"**
2. Wait 10-30 seconds
3. Should see either:
   - ✅ Edges found (display shows opportunities)
   - ✅ "No edges found" (normal - markets are efficient!)

### 3.3 Check Logs (if issues)
In Render dashboard:
1. Click on your service
2. Go to "Logs" tab
3. Look for any error messages

---

## Step 4: Using Your Deployed App

### Normal Usage
1. **Visit your Render URL** whenever you want to check for edges
2. **Click "Scan Now"** to search for opportunities
3. **Enable Auto-Scan** to monitor continuously
4. **Check back** periodically for new edges

### Free Tier Limitations
- **Sleeps after 15 min** of no activity
- First request after sleep is slow (~30 sec)
- **Solution:** Enable auto-scan to keep it awake
- **Or:** Upgrade to paid tier ($7/month) for always-on

### API Rate Limits
**The Odds API (Free Tier):**
- 500 requests/month
- ~16 requests/day
- Each scan = 1 request per sport (usually 4 sports = 4 requests)
- Auto-scan every 5 min = ~288 scans/day (too many!)

**Recommendation:**
- Manual scans only on free tier
- OR increase SCAN_INTERVAL to 1800 (30 minutes)
- OR upgrade The Odds API plan

---

## Step 5: Updating Your App

### Make Changes Locally
```bash
# Edit files
nano app.py  # or any file

# Commit changes
git add .
git commit -m "Updated feature X"

# Push to GitHub
git push origin main
```

### Automatic Deployment
Render automatically deploys when you push to GitHub!
- Watch deployment in Render dashboard
- Takes 2-3 minutes
- No downtime

---

## 🔧 Advanced Configuration

### Custom Domain
1. Render Dashboard → Your Service → Settings
2. Scroll to "Custom Domain"
3. Add your domain
4. Follow DNS instructions
5. Free HTTPS certificate included!

### Monitoring
Render provides:
- **Metrics**: CPU, Memory, Request rate
- **Logs**: Real-time application logs
- **Alerts**: Email notifications for errors

### Scaling
Need more power?
- Upgrade to Starter ($7/month): Always-on, 512MB RAM
- Or Standard ($25/month): 2GB RAM, better performance

### Health Checks
Render pings `/health` endpoint every 30 seconds.
Already configured in the app!

---

## 🐛 Troubleshooting

### "Application failed to start"
**Check:**
1. Environment variables are set correctly
2. No syntax errors in code
3. Logs for specific error message

**Fix:**
```bash
# Test locally first
python app.py
# Should start without errors
```

### "No edges found" every time
**Normal!** Edges are rare. Try:
1. Lower MIN_EDGE to 5.0
2. Check during game days
3. Verify API keys are working (check logs)

### API Key Issues
**Symptoms:**
- "Mock data" instead of real odds
- Errors in logs mentioning API

**Fix:**
1. Verify keys in Render environment variables
2. Test keys locally:
```python
import requests
key = "your-key"
r = requests.get(f"https://api.the-odds-api.com/v4/sports?apiKey={key}")
print(r.json())
```

### Service Sleeping Too Much
**Solutions:**
1. Enable auto-scan (keeps service awake)
2. Upgrade to paid tier ($7/month)
3. Use a service like UptimeRobot to ping every 5 min

---

## 💰 Costs

### Free Tier (Perfect for Starting)
- ✅ Render: Free web service
- ✅ The Odds API: 500 requests/month
- ✅ GitHub: Free repositories
- **Total: $0/month**

### Recommended Paid Setup
- Render Starter: $7/month (always-on)
- The Odds API Hobby: $49/month (25,000 requests)
- **Total: $56/month**

### Heavy Usage
- Render Standard: $25/month
- The Odds API Starter: $199/month (100,000 requests)
- **Total: $224/month**

---

## 🎯 Best Practices

### 1. Monitor Your Usage
- Check Render dashboard for crashes
- Monitor The Odds API quota
- Track edge opportunities found

### 2. Security
- ✅ Never commit API keys
- ✅ Use environment variables
- ✅ Keep .gitignore updated
- ✅ Rotate keys periodically

### 3. Performance
- Don't scan too frequently (respect rate limits)
- Use auto-scan strategically
- Consider upgrading if hitting limits

### 4. Trading
- Always verify edges manually
- Don't blindly trust the data
- Track your actual results
- Only bet what you can afford

---

## 📞 Getting Help

### Render Support
- Dashboard: https://dashboard.render.com
- Docs: https://render.com/docs
- Community: https://community.render.com

### The Odds API
- Dashboard: https://the-odds-api.com
- Docs: https://the-odds-api.com/docs
- Email: support@the-odds-api.com

### GitHub Issues
- Report bugs on your repository
- Check existing issues first
- Include logs and error messages

---

## 🎉 Success!

Your Kalshi Edge Finder is now live on the internet!

**Next Steps:**
1. 📱 Bookmark your Render URL
2. 🔔 Set reminders to check during game days
3. 📊 Track your results
4. 💰 Find those edges!

**Good luck hunting for +EV opportunities!** 🎯

---

*Questions? Issues? Check the main README.md or create a GitHub issue.*
