# 🌍 EconXAI Dashboard v2.1

Spatio-Temporal Forecasting · Explainable AI · Real-Time Economic Analytics

---

## 🚀 Deploy in 5 Minutes (Streamlit Community Cloud — Free)

**Prerequisites:** GitHub account + Streamlit Cloud account (free at share.streamlit.io)

### Step 1 — Push to GitHub
```bash
git init
git add .
git commit -m "Initial deploy"
git remote add origin https://github.com/YOUR_USERNAME/econxai-dashboard.git
git push -u origin main
```

### Step 2 — Deploy on Streamlit Cloud
1. Go to **https://share.streamlit.io** → **New app**
2. Select your repo, branch `main`, main file `app.py`
3. Click **Deploy!**

### Step 3 — (Optional) Add CoinGecko API key for higher rate limits
In your app's **Settings → Secrets**, add:
```toml
COINGECKO_API_KEY = "your_key_here"
```

---

## 🐳 Deploy with Docker (Render / Railway / Fly.io / VPS)

```bash
docker build -t econxai .
docker run -p 8501:8501 econxai
```
Then open **http://localhost:8501**

---

## 💻 Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## 📁 File Structure

```
econxai/
├── app.py                          # Main application (single file)
├── requirements.txt                # All Python dependencies
├── .streamlit/
│   ├── config.toml                 # Streamlit server settings
│   └── secrets.toml.template       # Copy → secrets.toml, never commit
├── .gitignore                      # Excludes secrets + cache
├── Dockerfile                      # For Docker/cloud deployments
└── README.md                       # This file
```

---

## 🔧 What Was Fixed for Deployment (v2.0 → v2.1)

| # | Bug | Fix |
|---|-----|-----|
| D1 | `subprocess.check_call` auto-installs fail on Streamlit Cloud | Removed; all deps in `requirements.txt` |
| D2 | `str \| None` syntax crashes Python < 3.10 | Replaced with `Optional[str]` |
| D3 | orjson/Plotly circular import crash | Plotly JSON engine forced before imports |
| D4 | `@st.cache_data` with unhashable args causes `UnhashableTypeError` | Only primitives passed to cached functions |
| D5 | CoinGecko 429 rate-limits not handled | Explicit 429 retry with exponential back-off |
| D6 | `yfinance` tz-aware index crashes on pandas ≥ 2.x | `tz_localize(None)` with attribute guard |
| D7 | `make_subplots` secondary_y missing in `add_trace()` | Added `secondary_y=True` kwarg |
| D8 | `st.set_page_config()` called after other Streamlit calls on rerun | Moved to module top, called exactly once |
| D9 | CoinGecko Pro API key unused | Wired into `fetch_crypto()` via `st.secrets` |
| D10 | Auto-install helper left in code | Removed entirely |

---

## 📊 Data Sources

| Source | Reliability | Notes |
|--------|-------------|-------|
| World Bank GDP | ✅ Very reliable | Falls back to synthetic on timeout |
| Stock Market (yfinance) | ✅ Reliable | Requires `yfinance` in requirements.txt |
| Cryptocurrency (CoinGecko) | ⚠️ Rate-limited | Free tier: ~30 req/min; add API key for more |

🟢 **Live** = fetched from API this session  
🟡 **Synthetic** = realistic fallback when API is unreachable

---

## ⚙️ Environment Variables / Secrets

| Key | Required | Description |
|-----|----------|-------------|
| `COINGECKO_API_KEY` | No | Pro key removes CoinGecko rate limits |
