"""
=============================================================================
EconXAI Dashboard v2.1 — DEPLOYMENT-READY
=============================================================================
All deployment blockers fixed vs v2.0:

  FIX-D1  subprocess.check_call auto-install removed — banned on Streamlit
          Cloud / Render / Railway. All deps now live in requirements.txt.
          Optional packages (yfinance, xlsxwriter, kaleido) are imported
          with graceful try/except; missing ones degrade feature, not crash.

  FIX-D2  `str | None` union syntax (Python 3.10+) replaced with
          `Optional[str]` / plain `None` default — keeps Python 3.9 compat.

  FIX-D3  orjson / Plotly JSON engine forced before any plotly import
          (retained from v1) to prevent circular-import crash on some hosts.

  FIX-D4  st.cache_data decorated functions no longer take unhashable args;
          only primitives are passed so Streamlit's hasher never errors.

  FIX-D5  CoinGecko rate-limit (HTTP 429) handled explicitly: exponential
          back-off up to 4 retries; falls back to synthetic on persistent fail.

  FIX-D6  yfinance tz-aware DatetimeIndex → tz-naive conversion is now
          guarded against AttributeError on pandas >= 2.x.

  FIX-D7  plotly make_subplots secondary_y trace now uses correct kwarg
          `secondary_y=True` inside add_trace() — was missing in Tab 5.

  FIX-D8  All st.set_page_config() called exactly once, at module top, before
          any other Streamlit call — guarantees no "can only be called once"
          error on hot-reload.

  FIX-D9  secrets.toml optional CoinGecko key wired into fetch_crypto().

  FIX-D10 `_ensure_package` helper removed entirely; replaced by clear
          import-check booleans.
=============================================================================
"""

# ---------------------------------------------------------------------------
# FIX-D3: Force Plotly → stdlib json BEFORE any plotly import
# ---------------------------------------------------------------------------
import os
os.environ["PLOTLY_RENDERER"] = "json"
import plotly.io as _pio
_pio.json.config.default_engine = "json"

# ---------------------------------------------------------------------------
# FIX-D1: Optional packages — import with graceful fallback (no subprocess)
# ---------------------------------------------------------------------------
try:
    import yfinance as yf
    _yfinance_ok = True
except ImportError:
    _yfinance_ok = False

try:
    import xlsxwriter  # noqa: F401
    _xlsxwriter_ok = True
except ImportError:
    _xlsxwriter_ok = False

try:
    import kaleido  # noqa: F401
    _kaleido_ok = True
except ImportError:
    _kaleido_ok = False

# ---------------------------------------------------------------------------
# Standard imports
# ---------------------------------------------------------------------------
import sys
import io
import time
import random
import warnings
from datetime import datetime, timedelta
from typing import Optional  # FIX-D2: replaces `str | None` union syntax

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import requests
import streamlit as st
import xgboost as xgb
import shap
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# FIX-D8: set_page_config — MUST be first Streamlit call; called exactly once
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="EconXAI Dashboard",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ===========================================================================
# CSS
# ===========================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,400&display=swap');
:root{--bg:#0d1117;--surface:#161b22;--surface2:#21262d;--border:#30363d;
      --accent:#58a6ff;--accent2:#3fb950;--accent3:#f78166;--accent4:#d2a8ff;
      --warn:#e3b341;--text:#e6edf3;--muted:#8b949e;
      --gradient:linear-gradient(135deg,#58a6ff 0%,#d2a8ff 50%,#3fb950 100%);}
html,body,.stApp{background-color:var(--bg)!important;}
*{font-family:'DM Sans',sans-serif;}
h1,h2,h3,h4,.main-header{font-family:'Syne',sans-serif!important;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding:1.5rem 2rem!important;max-width:1600px;}
.main-header{font-size:2.6rem;font-weight:800;text-align:center;padding:.5rem 0 .2rem;
  background:var(--gradient);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:-.5px;}
.sub-header{text-align:center;font-size:.95rem;color:var(--muted);margin-bottom:1.2rem;font-weight:300;}
.summary-bar{display:flex;gap:16px;padding:12px 18px;background:var(--surface);border:1px solid var(--border);
  border-radius:12px;margin-bottom:1rem;flex-wrap:wrap;align-items:center;}
.summary-item{display:flex;align-items:center;gap:6px;font-size:.83rem;color:var(--muted);}
.summary-value{font-weight:600;color:var(--text);font-size:.87rem;}
.status-dot{width:8px;height:8px;border-radius:50%;display:inline-block;}
.dot-green{background:var(--accent2);box-shadow:0 0 6px var(--accent2);}
.dot-yellow{background:var(--warn);}
.metric-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:1rem 1.2rem;border-left:3px solid var(--accent);}
.metric-card h4{color:var(--text);margin:0 0 6px;font-size:.9rem;}
.metric-card p{color:var(--muted);margin:2px 0;font-size:.82rem;}
.info-box,.warning-box,.success-box,.error-box{border-radius:10px;padding:12px 16px;margin:8px 0;}
.info-box{background:rgba(88,166,255,.08);border:1px solid rgba(88,166,255,.3);}
.warning-box{background:rgba(227,179,65,.08);border:1px solid rgba(227,179,65,.3);}
.success-box{background:rgba(63,185,80,.08);border:1px solid rgba(63,185,80,.3);}
.error-box{background:rgba(247,129,102,.08);border:1px solid rgba(247,129,102,.3);}
.info-box h4,.warning-box h4,.success-box h4,.error-box h4{color:var(--text);margin:0 0 5px;}
.info-box p,.warning-box p,.success-box p,.error-box p{color:var(--muted);font-size:.85rem;margin:2px 0;}
.quickstart{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1.1rem 1.4rem;margin-bottom:1rem;}
.quickstart h3{color:var(--text);margin:0 0 10px;font-size:1rem;}
.qs-steps{display:flex;gap:10px;flex-wrap:wrap;}
.qs-step{display:flex;align-items:flex-start;gap:8px;background:var(--surface2);border:1px solid var(--border);
  border-radius:10px;padding:8px 11px;flex:1;min-width:120px;}
.qs-num{background:var(--accent);color:#000;font-weight:700;font-size:.75rem;border-radius:50%;
  width:22px;height:22px;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-family:'Syne',sans-serif;}
.qs-text{font-size:.78rem;color:var(--muted);line-height:1.3;}
.qs-text strong{color:var(--text);display:block;font-size:.8rem;margin-bottom:2px;}
.what-it-does{background:linear-gradient(135deg,rgba(88,166,255,.06) 0%,rgba(210,168,255,.06) 100%);
  border:1px solid rgba(88,166,255,.2);border-radius:12px;padding:.9rem 1.3rem;margin-bottom:.8rem;}
.what-it-does h3{color:var(--accent4);font-size:.88rem;margin:0 0 5px;}
.what-it-does p{color:var(--muted);font-size:.84rem;line-height:1.5;margin:0;}
.use-cases{display:flex;flex-wrap:wrap;gap:7px;margin:7px 0;}
.use-case-chip{background:var(--surface2);border:1px solid var(--border);border-radius:20px;
  padding:3px 11px;font-size:.77rem;color:var(--muted);}
.insight-card{background:var(--surface2);border:1px solid var(--border);border-left:3px solid var(--accent2);
  border-radius:10px;padding:9px 13px;margin:5px 0;}
.insight-card p{color:var(--muted);font-size:.84rem;margin:0;}
.insight-card strong{color:var(--text);}
section[data-testid="stSidebar"]{background:var(--surface)!important;border-right:1px solid var(--border)!important;}
section[data-testid="stSidebar"] *{color:var(--text)!important;}
.stButton>button{background:var(--accent)!important;color:#000!important;font-weight:600!important;
  border:none!important;border-radius:8px!important;font-family:'Syne',sans-serif!important;}
.stTabs [data-baseweb="tab-list"]{gap:4px;background:var(--surface);border-radius:10px;padding:4px;}
.stTabs [data-baseweb="tab"]{background:transparent!important;border-radius:8px!important;
  color:var(--muted)!important;font-size:.83rem!important;padding:6px 10px!important;}
.stTabs [aria-selected="true"]{background:var(--surface2)!important;color:var(--text)!important;}
.stMetric{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px;}
.stMetric label{color:var(--muted)!important;font-size:.78rem!important;}
.stMetric [data-testid="stMetricValue"]{color:var(--text)!important;font-family:'Syne',sans-serif!important;}
.stSelectbox label,.stMultiSelect label,.stSlider label,.stRadio label,.stTextInput label{color:var(--muted)!important;font-size:.82rem!important;}
div[data-testid="stDataFrame"]{background:var(--surface);border-radius:10px;}
</style>
""", unsafe_allow_html=True)

# ===========================================================================
# CONSTANTS
# ===========================================================================

COUNTRIES = {
    "USA": ("US", "North America",  -95.7129,  37.0902),
    "GBR": ("GB", "Europe",          -3.4360,  55.3781),
    "DEU": ("DE", "Europe",          10.4515,  51.1657),
    "JPN": ("JP", "Asia-Pacific",   138.2529,  36.2048),
    "CHN": ("CN", "Asia-Pacific",   104.1954,  35.8617),
    "IND": ("IN", "Asia-Pacific",    78.9629,  20.5937),
    "BRA": ("BR", "Latin America",  -51.9253, -14.2350),
    "ZAF": ("ZA", "Africa",          22.9375, -30.5595),
    "NGA": ("NG", "Africa",           8.6753,   9.0820),
    "SAU": ("SA", "Middle East",     45.0792,  23.8859),
}
COUNTRY_NAMES = {
    "USA": "United States", "GBR": "United Kingdom", "DEU": "Germany",
    "JPN": "Japan",         "CHN": "China",           "IND": "India",
    "BRA": "Brazil",        "ZAF": "South Africa",    "NGA": "Nigeria",
    "SAU": "Saudi Arabia",
}
STOCK_SYMBOLS = {
    "USA": "SPY",  "GBR": "EWU",  "DEU": "EWG",  "JPN": "EWJ",
    "CHN": "MCHI", "IND": "INDA", "BRA": "EWZ",  "ZAF": "EZA",
    "NGA": "NGE",  "SAU": "KSA",
}
CRYPTO_ASSETS = {
    "BTC":  ("bitcoin",       "Crypto", 0.0, 0.0),
    "ETH":  ("ethereum",      "Crypto", 0.0, 0.0),
    "BNB":  ("binancecoin",   "Crypto", 0.0, 0.0),
    "SOL":  ("solana",        "Crypto", 0.0, 0.0),
    "ADA":  ("cardano",       "Crypto", 0.0, 0.0),
    "XRP":  ("ripple",        "Crypto", 0.0, 0.0),
    "DOT":  ("polkadot",      "Crypto", 0.0, 0.0),
    "MATIC":("matic-network", "Crypto", 0.0, 0.0),
    "AVAX": ("avalanche-2",   "Crypto", 0.0, 0.0),
    "LINK": ("chainlink",     "Crypto", 0.0, 0.0),
}
FEATURE_NAMES_HUMAN = {
    "gdp_lag1":       "Previous year's value",
    "gdp_lag2":       "Value 2 years ago",
    "gdp_lag3":       "Value 3 years ago",
    "roll3_mean":     "3-year rolling average",
    "roll3_std":      "3-year volatility",
    "yoy_growth":     "Year-over-year growth %",
    "year_num":       "Time trend (year)",
    "region_avg_gdp": "Regional peer average",
    "region_rank":    "Rank within region",
    "country_enc":    "Country identity",
    "region_enc":     "Region identity",
}

# Synthetic-data baselines
_GDP_BASELINE    = {"USA":48000,"GBR":38000,"DEU":40000,"JPN":43000,"CHN":4500,"IND":1400,"BRA":9500,"ZAF":7200,"NGA":1100,"SAU":18000}
_GDP_GROWTH      = {"USA":.020,"GBR":.018,"DEU":.019,"JPN":.008,"CHN":.085,"IND":.065,"BRA":.018,"ZAF":.012,"NGA":.030,"SAU":.025}
_STOCK_BASELINE  = {"USA":290,"GBR":33,"DEU":28,"JPN":62,"CHN":60,"IND":33,"BRA":38,"ZAF":42,"NGA":12,"SAU":28}
_STOCK_RETURN    = {"USA":.12,"GBR":.06,"DEU":.08,"JPN":.07,"CHN":.05,"IND":.10,"BRA":.07,"ZAF":.05,"NGA":.04,"SAU":.08}
_CRYPTO_BASELINE = {"BTC":11000,"ETH":400,"BNB":30,"SOL":3,"ADA":.10,"XRP":.25,"DOT":5,"MATIC":.02,"AVAX":4,"LINK":10}
_CRYPTO_RETURN   = {"BTC":.60,"ETH":.80,"BNB":1.20,"SOL":2.00,"ADA":.50,"XRP":.30,"DOT":.70,"MATIC":1.50,"AVAX":1.80,"LINK":.60}

COLORS = ["#58a6ff","#3fb950","#f78166","#d2a8ff","#e3b341",
          "#79c0ff","#56d364","#ffa657","#bc8cff","#ff7b72"]

DARK_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(22,27,34,0.9)",
    font=dict(color="#e6edf3", family="DM Sans"),
    xaxis=dict(gridcolor="#30363d", linecolor="#30363d"),
    yaxis=dict(gridcolor="#30363d", linecolor="#30363d"),
)

# Session-state defaults
for _k, _v in [("data_loaded", False), ("model_trained", False), ("syn_flags", {})]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ===========================================================================
# DATA HELPERS
# ===========================================================================

def _retry_get(url: str, params: Optional[dict] = None,
               attempts: int = 3, base: float = 2.0) -> Optional[requests.Response]:
    """GET with exponential back-off; returns None on total failure."""
    for i in range(attempts):
        try:
            r = requests.get(url, params=params, timeout=60)
            # FIX-D5: treat 429 (rate-limit) as retriable
            if r.status_code == 429:
                wait = base ** i + random.uniform(0, 2)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException:
            if i == attempts - 1:
                return None
            time.sleep(base ** i + random.uniform(0, 1))
    return None


# ── Synthetic generators ────────────────────────────────────────────────────

def _syn_gdp(country: str, sy: int, ey: int) -> pd.DataFrame:
    b = _GDP_BASELINE.get(country, 10_000)
    g = _GDP_GROWTH.get(country, 0.02)
    rng = np.random.default_rng(abs(hash(country)) % (2 ** 32))
    yrs = list(range(sy, ey + 1))
    vals = [b * (1 + g) ** (y - sy) * (1 + rng.normal(0, 0.015)) for y in yrs]
    return pd.DataFrame({"year": yrs, "value": vals, "_synthetic": True})


def _syn_stk(country: str, sy: int, ey: int) -> pd.DataFrame:
    b = _STOCK_BASELINE.get(country, 50)
    g = _STOCK_RETURN.get(country, 0.08)
    rng = np.random.default_rng(abs(hash(country + "s")) % (2 ** 32))
    yrs = list(range(sy, ey + 1))
    vals = [b * (1 + g) ** (y - sy) * (1 + rng.normal(0, 0.12)) for y in yrs]
    return pd.DataFrame({"year": yrs, "value": vals, "_synthetic": True})


def _syn_cry(asset: str, sy: int, ey: int) -> pd.DataFrame:
    b = _CRYPTO_BASELINE.get(asset, 1)
    g = _CRYPTO_RETURN.get(asset, 0.5)
    rng = np.random.default_rng(abs(hash(asset + "c")) % (2 ** 32))
    yrs = list(range(sy, ey + 1))
    vals = [b * (1 + g) ** (y - sy) * max(0.01, 1 + rng.normal(0, 0.35)) for y in yrs]
    return pd.DataFrame({"year": yrs, "value": vals, "_synthetic": True})


# ── Cached fetchers  (FIX-D4: only hashable primitives as args) ─────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_gdp(country_key: str, country_code: str, sy: int, ey: int) -> pd.DataFrame:
    url = (f"https://api.worldbank.org/v2/country/{country_code}"
           f"/indicator/NY.GDP.PCAP.CD?date={sy}:{ey}&format=json&per_page=100")
    r = _retry_get(url)
    if r:
        try:
            p = r.json()
            if len(p) >= 2 and p[1]:
                rows = [{"year": int(x["date"]), "value": x["value"], "_synthetic": False}
                        for x in p[1] if x["value"] is not None]
                if rows:
                    return pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
        except Exception:
            pass
    return _syn_gdp(country_key, sy, ey)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_stock(country: str, sy: int, ey: int) -> pd.DataFrame:
    if not _yfinance_ok:
        return _syn_stk(country, sy, ey)
    sym = STOCK_SYMBOLS.get(country)
    if not sym:
        return _syn_stk(country, sy, ey)
    try:
        df = yf.Ticker(sym).history(
            start=f"{sy}-01-01", end=f"{ey}-12-31", auto_adjust=True
        )
        if df.empty:
            raise ValueError("empty")
        df = df.reset_index()
        # FIX-D6: tz-aware index guard for pandas >= 2.x
        date_col = df["Date"]
        if hasattr(date_col.dtype, "tz") and date_col.dt.tz is not None:
            df["Date"] = date_col.dt.tz_localize(None)
        df["year"] = df["Date"].dt.year
        ann = (df.groupby("year")["Close"]
               .mean()
               .reset_index()
               .rename(columns={"Close": "value"}))
        ann = ann[(ann["year"] >= sy) & (ann["year"] <= ey)]
        if ann.empty:
            raise ValueError("empty after filter")
        ann["_synthetic"] = False
        return ann.sort_values("year").reset_index(drop=True)
    except Exception:
        return _syn_stk(country, sy, ey)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_crypto(asset: str, sy: int, ey: int) -> pd.DataFrame:
    cid = CRYPTO_ASSETS[asset][0]
    # FIX-D9: use CoinGecko Pro key from secrets if available
    headers = {}
    try:
        api_key = st.secrets.get("COINGECKO_API_KEY", "")
        if api_key:
            headers["x-cg-pro-api-key"] = api_key
    except Exception:
        pass

    params = {
        "vs_currency": "usd",
        "from": int(datetime(sy, 1, 1).timestamp()),
        "to":   int(datetime(ey, 12, 31).timestamp()),
    }
    r = _retry_get(
        f"https://api.coingecko.com/api/v3/coins/{cid}/market_chart/range",
        params=params, attempts=4, base=3.0,
    )
    if r:
        try:
            d = r.json()
            if "prices" in d and d["prices"]:
                df = pd.DataFrame(d["prices"], columns=["ts", "price"])
                df["year"] = pd.to_datetime(df["ts"], unit="ms").dt.year
                ann = (df.groupby("year")["price"]
                       .mean()
                       .reset_index()
                       .rename(columns={"price": "value"}))
                ann = ann[(ann["year"] >= sy) & (ann["year"] <= ey)]
                if not ann.empty:
                    ann["_synthetic"] = False
                    return ann.sort_values("year").reset_index(drop=True)
        except Exception:
            pass
    return _syn_cry(asset, sy, ey)


# ===========================================================================
# FEATURE ENGINEERING & MODEL
# ===========================================================================

FEATURES = [
    "gdp_lag1", "gdp_lag2", "gdp_lag3",
    "roll3_mean", "roll3_std", "yoy_growth",
    "year_num", "region_avg_gdp", "region_rank",
    "country_enc", "region_enc",
]


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    dfs = []
    for ent, grp in df.groupby("country"):
        g = grp.copy().sort_values("year")
        g["gdp_lag1"]   = g["value"].shift(1)
        g["gdp_lag2"]   = g["value"].shift(2)
        g["gdp_lag3"]   = g["value"].shift(3)
        g["roll3_mean"] = g["value"].shift(1).rolling(3).mean()
        g["roll3_std"]  = g["value"].shift(1).rolling(3).std()
        g["yoy_growth"] = g["value"].pct_change() * 100
        g["year_num"]   = g["year"].astype(int)
        dfs.append(g)
    c = pd.concat(dfs, ignore_index=True)
    c["region_avg_gdp"] = c.groupby(["year", "region"])["value"].transform("mean")
    c["region_rank"]    = c.groupby(["year", "region"])["value"].rank(ascending=False)
    le1, le2 = LabelEncoder(), LabelEncoder()
    c["country_enc"] = le1.fit_transform(c["country"].astype(str))
    c["region_enc"]  = le2.fit_transform(c["region"].astype(str))
    return c.dropna().reset_index(drop=True)


def train_xgb(df: pd.DataFrame, target: str = "value") -> xgb.XGBRegressor:
    m = xgb.XGBRegressor(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=42, verbosity=0,
    )
    m.fit(df[FEATURES], df[target])
    return m


# ===========================================================================
# INSIGHTS & EXPORT
# ===========================================================================

def generate_insights(fd: pd.DataFrame, vshort: str, upfx: str, sc: float) -> list:
    ins = []
    avg_g = fd.groupby("country")["yoy_growth"].mean().sort_values(ascending=False)
    if len(avg_g):
        ins.append({"i": "🏆", "t": f"<strong>{avg_g.index[0]}</strong> leads with avg growth of <strong>{avg_g.iloc[0]:.1f}%</strong>/year."})
    if len(avg_g) > 1:
        ins.append({"i": "📉", "t": f"<strong>{avg_g.index[-1]}</strong> shows the slowest growth at <strong>{avg_g.iloc[-1]:.1f}%</strong>/year."})
    latest = fd[fd["year"] == fd["year"].max()]
    if not latest.empty:
        top = latest.loc[latest["value"].idxmax()]
        fv = f"{upfx}{top['value']/sc:.1f}k" if sc > 1 else f"{upfx}{top['value']:,.0f}"
        ins.append({"i": "💰", "t": f"<strong>{top['country']}</strong> has the highest current {vshort} at <strong>{fv}</strong>."})
    r2 = r2_score(fd["value"], fd["pred"])
    ins.append({"i": "🤖", "t": f"The XGBoost model explains <strong>{r2*100:.1f}%</strong> of variance (R²={r2:.3f})."})
    for ent in fd["country"].unique():
        cd = fd[fd["country"] == ent].sort_values("year").tail(4)
        if len(cd) >= 4:
            e = cd.iloc[:2]["yoy_growth"].mean()
            l = cd.iloc[2:]["yoy_growth"].mean()
            if e > 3 and l < 0:
                ins.append({"i": "⚠️", "t": f"<strong>{ent}</strong> shows a recent growth reversal — momentum turned negative."})
                break
    return ins[:5]


def to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def to_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    try:
        with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
            df.to_excel(w, index=False, sheet_name="Data")
            if "pred" in df.columns:
                df[["country", "year", "value", "pred", "residual", "yoy_growth"]].to_excel(
                    w, index=False, sheet_name="Predictions"
                )
    except Exception:
        df.to_excel(buf, index=False)
    return buf.getvalue()


# ===========================================================================
# HEADER
# ===========================================================================

st.markdown('<p class="main-header">🌍 EconXAI Dashboard</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">Spatio-Temporal Forecasting · Explainable AI · Real-Time Economic Analytics</p>',
    unsafe_allow_html=True,
)

# Quick-start
with st.expander("🚀 Quick Start Guide", expanded=not st.session_state.data_loaded):
    st.markdown("""
    <div class="quickstart">
      <h3>How to Use This Dashboard</h3>
      <div class="qs-steps">
        <div class="qs-step"><div class="qs-num">1</div><div class="qs-text"><strong>Pick Data Source</strong>GDP, Stock, or Crypto</div></div>
        <div class="qs-step"><div class="qs-num">2</div><div class="qs-text"><strong>Search Countries</strong>Type to filter the list</div></div>
        <div class="qs-step"><div class="qs-num">3</div><div class="qs-text"><strong>Set Year Range</strong>Wider = more training data</div></div>
        <div class="qs-step"><div class="qs-num">4</div><div class="qs-text"><strong>Click Load Data</strong>Auto-fetches + trains model</div></div>
        <div class="qs-step"><div class="qs-num">5</div><div class="qs-text"><strong>Explore 7 Tabs</strong>Trend, Compare, Predict...</div></div>
      </div>
    </div>
    <div class="what-it-does">
      <h3>📌 What This App Does</h3>
      <p>Fetches real economic data, trains an XGBoost forecasting model, then uses
      <strong>Explainable AI (SHAP)</strong> to explain <em>why</em> each prediction was made — in plain language.</p>
    </div>
    <div class="use-cases">
      <span class="use-case-chip">📊 Compare GDP growth</span>
      <span class="use-case-chip">📈 Track stock index trends</span>
      <span class="use-case-chip">₿ Analyze crypto performance</span>
      <span class="use-case-chip">🔍 Understand economic drivers</span>
      <span class="use-case-chip">📉 Detect growth slowdowns</span>
      <span class="use-case-chip">📥 Export for presentations</span>
    </div>
    """, unsafe_allow_html=True)

# ===========================================================================
# SIDEBAR
# ===========================================================================

with st.sidebar:
    st.markdown("### ⚙️ Control Panel")
    st.markdown("---")

    st.markdown("**📊 Data Source**")
    data_source = st.radio(
        "Data Source",
        ["World Bank GDP", "Stock Market (Real-time)", "Cryptocurrency (Real-time)"],
        label_visibility="collapsed",
    )
    st.markdown("---")

    if data_source in ("World Bank GDP", "Stock Market (Real-time)"):
        st.markdown("**🔍 Country Search**")
        srch = st.text_input("Type name or code:", placeholder="India, USA, CHN...", key="srch")
        all_keys = list(COUNTRIES.keys())
        if srch.strip():
            q = srch.strip().upper()
            fil = [k for k in all_keys if q in k or q in COUNTRY_NAMES.get(k, "").upper()]
        else:
            fil = all_keys
        defaults = [c for c in ["USA", "IND", "CHN", "GBR"] if c in fil]
        selected = st.multiselect(
            "Countries:", fil, default=defaults,
            format_func=lambda k: f"{k} — {COUNTRY_NAMES.get(k, k)}",
        )
        entity_label = "country"
    else:
        st.markdown("**₿ Crypto Assets**")
        srch2 = st.text_input("Search asset:", placeholder="BTC, ETH...", key="srch2")
        all_cr = list(CRYPTO_ASSETS.keys())
        fil_cr = [k for k in all_cr if srch2.strip().upper() in k] if srch2.strip() else all_cr
        selected = st.multiselect("Assets:", fil_cr, default=["BTC", "ETH", "BNB", "SOL"])
        entity_label = "asset"

    st.markdown("---")
    st.markdown("**📅 Time Range**")
    if data_source == "World Bank GDP":
        sy = st.slider("Start Year", 2000, 2020, 2010)
        ey = st.slider("End Year",   2015, 2023, 2022)
    else:
        yb = st.slider("Years of Data", 2, 10, 5)
        ey = datetime.now().year - 1
        sy = ey - yb

    st.markdown("---")
    st.markdown("**🤖 Training Cutoff**")
    def_cut = min(ey - 2, sy + max(1, (ey - sy) - 2))
    cutoff  = st.slider("Cutoff Year", sy, ey - 1, def_cut)

    st.markdown("---")
    st.markdown("**🔴 Live Streaming**")
    stream_on  = st.checkbox("Enable Auto-Refresh", value=False)
    stream_int = st.slider("Interval (s)", 5, 60, 10) if stream_on else 10

    st.markdown("---")
    btn_load = st.button("🚀 Load Data & Train Model", type="primary", width="stretch")
    if btn_load:
        st.session_state.data_loaded   = False
        st.session_state.model_trained = False
        fetch_gdp.clear()
        fetch_stock.clear()
        fetch_crypto.clear()

    st.markdown("---")
    st.markdown("**📡 System Status**")
    ds_s = "🟢 Loaded"  if st.session_state.data_loaded   else "⚪ Not loaded"
    md_s = "🟢 Trained" if st.session_state.model_trained else "⚪ Not trained"
    yf_s = "🟢 Available" if _yfinance_ok  else "🟡 Not installed (fallback on)"
    st.markdown(f"""
    <div style="font-size:.8rem;color:#8b949e;line-height:2.1;">
    Data: {ds_s}<br>
    Model: {md_s}<br>
    Stream: {"🔴 Active" if stream_on else "⚪ Off"}<br>
    yfinance: {yf_s}<br>
    Cache: 🟢 Active
    </div>""", unsafe_allow_html=True)

# ===========================================================================
# DATA LOADING
# ===========================================================================

if not st.session_state.data_loaded:
    if not selected:
        st.markdown(
            '<div class="warning-box"><h4>⚠️ Nothing selected</h4>'
            '<p>Pick at least one country/asset in the sidebar, then click <strong>Load Data & Train Model</strong>.</p></div>',
            unsafe_allow_html=True,
        )
        st.stop()

    with st.status("📡 Fetching data...", expanded=True) as sw:
        frames, syn_flags = [], {}

        if data_source == "World Bank GDP":
            for c in selected:
                st.write(f"  Fetching {COUNTRY_NAMES.get(c, c)}...")
                code, region, lon, lat = COUNTRIES[c]
                df_c = fetch_gdp(c, code, sy, ey)
                if not df_c.empty:
                    df_c["country"]   = c
                    df_c["region"]    = region
                    df_c["longitude"] = lon
                    df_c["latitude"]  = lat
                    syn_flags[c] = bool(df_c["_synthetic"].any())
                    frames.append(df_c)
                time.sleep(0.05)

        elif data_source == "Stock Market (Real-time)":
            if not _yfinance_ok:
                st.warning("⚠️ yfinance not installed — using synthetic stock data. Add `yfinance` to requirements.txt.")
            for c in selected:
                sym = STOCK_SYMBOLS.get(c, "?")
                st.write(f"  Fetching {c} ({sym})...")
                _, region, lon, lat = COUNTRIES[c]
                df_s = fetch_stock(c, sy, ey)
                if not df_s.empty:
                    df_s["country"]   = c
                    df_s["region"]    = region
                    df_s["longitude"] = lon
                    df_s["latitude"]  = lat
                    syn_flags[c] = bool(df_s["_synthetic"].any())
                    frames.append(df_s)

        elif data_source == "Cryptocurrency (Real-time)":
            for i, a in enumerate(selected):
                st.write(f"  Fetching {a} from CoinGecko...")
                _, sector, lon, lat = CRYPTO_ASSETS[a]
                df_cr = fetch_crypto(a, sy, ey)
                if not df_cr.empty:
                    df_cr["country"]   = a
                    df_cr["region"]    = "Crypto"
                    df_cr["longitude"] = lon + i * 20
                    df_cr["latitude"]  = lat + i * 5
                    syn_flags[a] = bool(df_cr["_synthetic"].any())
                    frames.append(df_cr)
                time.sleep(0.3)

        if frames:
            raw = pd.concat(frames, ignore_index=True)
            if "_synthetic" not in raw.columns:
                raw["_synthetic"] = False
            st.session_state.update({
                "raw_df": raw, "data_loaded": True, "syn_flags": syn_flags,
                "data_source": data_source, "entity_label": entity_label,
                "selected": selected, "sy": sy, "ey": ey, "cutoff": cutoff,
            })
            live_n = sum(1 for v in syn_flags.values() if not v)
            syn_n  = sum(1 for v in syn_flags.values() if v)
            sw.update(label=f"✅ {len(raw)} records — 🟢 {live_n} live, 🟡 {syn_n} synthetic", state="complete")
        else:
            sw.update(label="❌ No data loaded", state="error")
            st.markdown("""
            <div class="error-box"><h4>❌ No data loaded</h4>
            <p>• Try different countries or a wider year range</p>
            <p>• Check your internet connection</p>
            <p>• World Bank GDP is the most reliable source</p></div>
            """, unsafe_allow_html=True)
            st.stop()

# ===========================================================================
# MODEL TRAINING
# ===========================================================================

if st.session_state.data_loaded and not st.session_state.model_trained:
    with st.status("🔧 Engineering features & training model...", expanded=False) as ms:
        cutoff = st.session_state.get("cutoff", cutoff)
        fd = engineer_features(st.session_state.raw_df)

        if len(fd) < 5:
            ms.update(label="❌ Not enough data", state="error")
            st.markdown("""
            <div class="error-box"><h4>⚠️ Not enough data to train</h4>
            <p>• Set <strong>Start Year earlier</strong> (e.g. 2010)</p>
            <p>• Add <strong>more countries</strong></p>
            <p>• Use at least a <strong>5-year range</strong></p></div>
            """, unsafe_allow_html=True)
            st.stop()

        train = fd[fd["year"] <= cutoff].copy()
        if train.empty:
            ms.update(label="❌ Training set empty", state="error")
            st.markdown("""
            <div class="error-box"><h4>⚠️ Training cutoff year is too high</h4>
            <p>Set <strong>Training Cutoff Year</strong> to an earlier year in the sidebar.</p></div>
            """, unsafe_allow_html=True)
            st.stop()

        m         = train_xgb(train)
        fd["pred"]     = m.predict(fd[FEATURES])
        fd["residual"] = fd["value"] - fd["pred"]
        explainer  = shap.TreeExplainer(m)
        shap_vals  = explainer.shap_values(fd[FEATURES])

        st.session_state.update({
            "feat_df": fd, "model": m, "explainer": explainer,
            "shap_vals": shap_vals, "model_trained": True,
        })
        ms.update(label="✅ Model ready!", state="complete")

# ===========================================================================
# DASHBOARD
# ===========================================================================

if st.session_state.model_trained:
    fd        = st.session_state.feat_df
    shap_vals = st.session_state.shap_vals
    syn_flags = st.session_state.syn_flags
    sel       = st.session_state.selected
    el        = st.session_state.entity_label
    ds        = st.session_state.data_source
    cutoff    = st.session_state.cutoff

    if ds == "World Bank GDP":
        vl = "GDP per Capita (USD)"; vs = "GDP"; sc = 1000; upfx = "$"; usfx = "k"
    elif ds == "Stock Market (Real-time)":
        vl = "ETF Price (USD)"; vs = "Price"; sc = 1; upfx = "$"; usfx = ""
    else:
        vl = "Crypto Price (USD)"; vs = "Price"; sc = 1; upfx = "$"; usfx = ""

    def fmt(v: float) -> str:
        return f"{upfx}{v/sc:.2f}{usfx}" if sc > 1 else f"{upfx}{v:,.2f}"

    # Summary bar
    live_n = sum(1 for v in syn_flags.values() if not v)
    syn_n  = sum(1 for v in syn_flags.values() if v)
    r2_all = r2_score(fd["value"], fd["pred"])
    st.markdown(f"""
    <div class="summary-bar">
      <div class="summary-item"><span class="status-dot dot-green"></span>{el.capitalize()}s: <span class="summary-value">{len(sel)}</span></div>
      <div class="summary-item">📅 Years: <span class="summary-value">{fd["year"].nunique()}</span></div>
      <div class="summary-item">📊 Records: <span class="summary-value">{len(fd):,}</span></div>
      <div class="summary-item">🤖 R²: <span class="summary-value">{r2_all:.3f}</span></div>
      <div class="summary-item">🟢 Live: <span class="summary-value">{live_n}</span></div>
      <div class="summary-item">🟡 Synthetic: <span class="summary-value">{syn_n}</span></div>
      <div class="summary-item"><span class="status-dot dot-green"></span>Model: <span class="summary-value">Trained ✓</span></div>
    </div>
    """, unsafe_allow_html=True)

    # Automated insights
    insights = generate_insights(fd, vs, upfx, sc)
    with st.expander("📌 Automated Key Insights", expanded=True):
        ic = st.columns(min(len(insights), 3))
        for i, ins in enumerate(insights):
            with ic[i % len(ic)]:
                st.markdown(f'<div class="insight-card"><p>{ins["i"]} {ins["t"]}</p></div>', unsafe_allow_html=True)

    st.markdown("---")

    # ── 7 TABS ─────────────────────────────────────────────────────────────
    t1, t2, t3, t4, t5, t6, t7 = st.tabs([
        "📈 Trend View", "⚖️ Compare", "🔮 Predictions",
        "🧠 XAI Explain", "🗺️ Spatial", "❓ Ask Why", "📥 Export",
    ])

    # ------------------------------------------------------------------ T1
    with t1:
        st.header("📈 Trend View")
        fig = go.Figure()
        for i, ent in enumerate(fd["country"].unique()):
            cd = fd[fd["country"] == ent].sort_values("year")
            yv = cd["value"] / sc if sc > 1 else cd["value"]
            fig.add_trace(go.Scatter(
                x=cd["year"], y=yv, mode="lines+markers", name=ent,
                line=dict(width=3, color=COLORS[i % len(COLORS)]),
                marker=dict(size=8, color=COLORS[i % len(COLORS)]),
                hovertemplate=f"<b>{ent}</b><br>Year: %{{x}}<br>{vs}: {upfx}%{{y:,.2f}}<extra></extra>",
            ))
        fig.add_vline(x=cutoff, line_dash="dot", line_color="#e3b341",
                      annotation_text=f"Train cutoff ({int(cutoff)})",
                      annotation_font_color="#e3b341")
        fig.update_layout(**DARK_LAYOUT,
            title=dict(text=f"{vl} Over Time", font=dict(size=18, family="Syne")),
            xaxis_title="Year", yaxis_title=vl, height=520, hovermode="x unified",
            legend=dict(bgcolor="rgba(22,27,34,.7)", bordercolor="#30363d", borderwidth=1),
        )
        st.plotly_chart(fig, width="stretch")

        ly = fd["year"].max()
        top_e = fd[fd["year"] == ly].sort_values("yoy_growth", ascending=False)
        if not top_e.empty:
            te = top_e.iloc[0]["country"]; tg = top_e.iloc[0]["yoy_growth"]
            st.markdown(f'<div class="insight-card"><p>📌 <strong>Chart Insight:</strong> In {int(ly)}, <strong>{te}</strong> shows the highest growth at <strong>{tg:.1f}%</strong>.</p></div>', unsafe_allow_html=True)

        if stream_on:
            st.info(f"🔄 Auto-refreshing every {stream_int}s...")
            time.sleep(stream_int)
            st.rerun()

        st.subheader("📊 Most Recent Year Statistics")
        sdf = fd[fd["year"] > cutoff]
        if not sdf.empty:
            lyr = sdf["year"].max()
            ltd = sdf[sdf["year"] == lyr][["country", "value", "pred", "yoy_growth"]].copy()
            ltd["value"]      = ltd["value"].apply(fmt)
            ltd["pred"]       = ltd["pred"].apply(fmt)
            ltd["yoy_growth"] = ltd["yoy_growth"].apply(lambda x: f"{x:.2f}%")
            ltd["source"]     = ltd["country"].apply(lambda c: "🟢 Live" if not syn_flags.get(c, True) else "🟡 Synthetic")
            ltd.columns       = [el.capitalize(), f"Actual {vs}", f"Predicted {vs}", "YoY Growth", "Data Source"]
            st.dataframe(ltd, width="stretch", hide_index=True)

    # ------------------------------------------------------------------ T2
    with t2:
        st.header("⚖️ Country Comparison Mode")
        ca, cb = st.columns(2)
        with ca:
            cmp_sel = st.multiselect("Select to compare:", sel, default=sel[:min(4, len(sel))], key="cmp")
        with cb:
            cmp_met = st.selectbox("Metric:", ["Actual Value", "YoY Growth %", "Predicted Value", "Residual"], key="cmet")

        if len(cmp_sel) < 2:
            st.info("Select at least 2 entities to compare.")
        else:
            cdf = fd[fd["country"].isin(cmp_sel)].copy()
            mc  = {"Actual Value": "value", "YoY Growth %": "yoy_growth", "Predicted Value": "pred", "Residual": "residual"}[cmp_met]
            use_scale = mc not in ("yoy_growth", "residual")
            fig_c = go.Figure()
            for i, ent in enumerate(cmp_sel):
                cd = cdf[cdf["country"] == ent].sort_values("year")
                yv = cd[mc] / sc if (sc > 1 and use_scale) else cd[mc]
                fig_c.add_trace(go.Scatter(x=cd["year"], y=yv, mode="lines+markers", name=ent,
                    line=dict(width=3, color=COLORS[i % len(COLORS)]),
                    marker=dict(size=9, color=COLORS[i % len(COLORS)]),
                    hovertemplate=f"<b>{ent}</b><br>Year: %{{x}}<br>{cmp_met}: %{{y:,.2f}}<extra></extra>"))
            if mc in ("yoy_growth", "residual"):
                fig_c.add_hline(y=0, line_dash="dash", line_color="#8b949e")
            fig_c.update_layout(**DARK_LAYOUT,
                title=dict(text=f"{cmp_met} — Side-by-Side", font=dict(size=16, family="Syne")),
                xaxis_title="Year", yaxis_title=cmp_met, height=480, hovermode="x unified",
                legend=dict(bgcolor="rgba(22,27,34,.7)", bordercolor="#30363d", borderwidth=1, orientation="h", y=-0.15),
            )
            st.plotly_chart(fig_c, width="stretch")

            st.subheader("📋 Ranking Table")
            rows = []
            for ent in cmp_sel:
                cd = fd[fd["country"] == ent]
                if len(cd) > 1:
                    rows.append({
                        el.capitalize(): ent,
                        f"Avg {vs}": fmt(cd["value"].mean()),
                        "Avg YoY Growth": f"{cd['yoy_growth'].mean():.2f}%",
                        "Latest Value": fmt(cd.sort_values("year").iloc[-1]["value"]),
                        "Model R²": f"{r2_score(cd['value'], cd['pred']):.3f}",
                        "Source": "🟢 Live" if not syn_flags.get(ent, True) else "🟡 Synthetic",
                    })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

            ldata = cdf[cdf["year"] == cdf["year"].max()]
            fig_b = go.Figure()
            for i, ent in enumerate(cmp_sel):
                vx = ldata[ldata["country"] == ent]["value"]
                if not vx.empty:
                    vv = vx.values[0]; dv = vv / sc if sc > 1 else vv
                    fig_b.add_trace(go.Bar(name=ent, x=[ent], y=[dv],
                        marker_color=COLORS[i % len(COLORS)],
                        text=[fmt(vv)], textposition="outside"))
            fig_b.update_layout(**DARK_LAYOUT,
                title=dict(text=f"Latest {vs} Comparison", font=dict(size=15, family="Syne")),
                yaxis_title=vl, height=380, showlegend=False)
            st.plotly_chart(fig_b, width="stretch")

    # ------------------------------------------------------------------ T3
    with t3:
        st.header("🔮 Model Predictions & Forecast")
        fig_p = go.Figure()
        for i, ent in enumerate(fd["country"].unique()):
            cd = fd[fd["country"] == ent].sort_values("year")
            yv = cd["value"] / sc if sc > 1 else cd["value"]
            yp = cd["pred"]  / sc if sc > 1 else cd["pred"]
            fig_p.add_trace(go.Scatter(x=cd["year"], y=yv, mode="lines+markers",
                name=f"{ent} Actual", line=dict(width=3, color=COLORS[i % len(COLORS)]),
                marker=dict(size=6), legendgroup=ent))
            fig_p.add_trace(go.Scatter(x=cd["year"], y=yp, mode="lines",
                name=f"{ent} Predicted", line=dict(width=2, dash="dot", color=COLORS[i % len(COLORS)]),
                opacity=0.7, legendgroup=ent))
        fig_p.add_vline(x=cutoff, line_dash="dot", line_color="#e3b341",
                        annotation_text="Training cutoff", annotation_font_color="#e3b341")
        fig_p.update_layout(**DARK_LAYOUT,
            title=dict(text=f"Actual vs Predicted {vs}", font=dict(size=18, family="Syne")),
            xaxis_title="Year", yaxis_title=vl, height=520, hovermode="x unified",
            legend=dict(bgcolor="rgba(22,27,34,.7)", bordercolor="#30363d", borderwidth=1,
                        orientation="h", y=-0.2, font=dict(size=10)),
        )
        st.plotly_chart(fig_p, width="stretch")

        c1, c2 = st.columns([1, 2])
        with c1:
            st.subheader("🎯 Per-Entity Accuracy")
            for ent in sel:
                cd = fd[fd["country"] == ent]
                if len(cd) > 1:
                    cm = mean_absolute_error(cd["value"], cd["pred"])
                    cr = r2_score(cd["value"], cd["pred"])
                    badge = "🟢 live" if not syn_flags.get(ent, True) else "🟡 synthetic"
                    st.markdown(f"""<div class="metric-card"><h4>{ent} <small>{badge}</small></h4>
                    <p>MAE: {fmt(cm)}</p><p>R²: {cr:.3f}</p></div><br>""", unsafe_allow_html=True)
        with c2:
            st.subheader("📉 Residual Analysis")
            pv = fd["pred"] / sc if sc > 1 else fd["pred"]
            rv = fd["residual"] / sc if sc > 1 else fd["residual"]
            fig_r = go.Figure(go.Scatter(x=pv, y=rv, mode="markers",
                marker=dict(size=9, color=fd["year"], colorscale="Plasma", showscale=True,
                            colorbar=dict(title="Year"), line=dict(width=1, color="#30363d")),
                text=fd["country"],
                hovertemplate=f"<b>%{{text}}</b><br>Pred: {upfx}%{{x:.2f}}<br>Residual: {upfx}%{{y:.2f}}<extra></extra>"))
            fig_r.add_hline(y=0, line_dash="dash", line_color="#f78166", annotation_text="Perfect prediction")
            fig_r.update_layout(**DARK_LAYOUT,
                title=dict(text="Residual vs Predicted", font=dict(size=15, family="Syne")),
                xaxis_title=f"Predicted {vs}", yaxis_title="Residual", height=440)
            st.plotly_chart(fig_r, width="stretch")

    # ------------------------------------------------------------------ T4
    with t4:
        st.header("🧠 Explainable AI — SHAP Analysis")
        mean_shap = pd.Series(np.abs(shap_vals).mean(axis=0), index=FEATURES).sort_values()
        hlabels   = [FEATURE_NAMES_HUMAN.get(f, f) for f in mean_shap.index]

        x1, x2 = st.columns(2)
        with x1:
            st.subheader("🎯 What Drives Predictions?")
            fig_si = go.Figure(go.Bar(
                x=mean_shap.values / sc if sc > 1 else mean_shap.values,
                y=hlabels, orientation="h",
                marker=dict(color=mean_shap.values, colorscale="Viridis", showscale=True,
                            colorbar=dict(title="Importance")),
                hovertemplate="%{y}<br>Importance: %{x:.4f}<extra></extra>"))
            fig_si.update_layout(**DARK_LAYOUT,
                title=dict(text="Global Feature Importance", font=dict(size=15, family="Syne")),
                xaxis_title="Mean |SHAP|", height=500)
            st.plotly_chart(fig_si, width="stretch")
            top_f = mean_shap.index[-1]
            st.markdown(f'<div class="insight-card"><p>📌 Most influential: <strong>"{FEATURE_NAMES_HUMAN.get(top_f, top_f)}"</strong>.</p></div>', unsafe_allow_html=True)

        with x2:
            st.subheader("📊 Feature Impact Plot")
            sf  = st.selectbox("Select feature:", FEATURES, format_func=lambda f: FEATURE_NAMES_HUMAN.get(f, f), key="sfdep")
            fi  = FEATURES.index(sf)
            svp = shap_vals[:, fi] / sc if sc > 1 else shap_vals[:, fi]
            fig_dep = go.Figure(go.Scatter(x=fd[sf], y=svp, mode="markers",
                marker=dict(size=9, color=fd["year"], colorscale="Plasma", showscale=True,
                            colorbar=dict(title="Year"), line=dict(width=1, color="#30363d")),
                text=fd["country"],
                hovertemplate=f"<b>%{{text}}</b><br>{FEATURE_NAMES_HUMAN.get(sf, sf)}: %{{x:.2f}}<br>Impact: {upfx}%{{y:.3f}}<extra></extra>"))
            fig_dep.add_hline(y=0, line_dash="dash", line_color="#f78166")
            fig_dep.update_layout(**DARK_LAYOUT,
                title=dict(text=f"Impact of: {FEATURE_NAMES_HUMAN.get(sf, sf)}", font=dict(size=13, family="Syne")),
                xaxis_title=FEATURE_NAMES_HUMAN.get(sf, sf), yaxis_title="Prediction Impact", height=500)
            st.plotly_chart(fig_dep, width="stretch")

        st.subheader("🔍 Explain a Single Prediction")
        xa, xb = st.columns(2)
        with xa: xent = st.selectbox(f"{el.capitalize()}:", sel, key="xent")
        with xb: xyr  = st.selectbox("Year:", sorted(fd[fd["country"] == xent]["year"].unique(), reverse=True), key="xyr")

        samp = fd[(fd["country"] == xent) & (fd["year"] == xyr)]
        if len(samp):
            sid  = samp.index[0]
            ss   = shap_vals[sid]
            xa2, xb2, xc2 = st.columns(3)
            with xa2: st.metric("Actual",    fmt(samp["value"].values[0]))
            with xb2: st.metric("Predicted", fmt(samp["pred"].values[0]))
            with xc2: st.metric("Error",     fmt(abs(samp["residual"].values[0])))

            top8 = np.argsort(np.abs(ss))[::-1][:8]
            sv8  = [ss[i] / sc if sc > 1 else ss[i] for i in top8]
            h8   = [FEATURE_NAMES_HUMAN.get(FEATURES[i], FEATURES[i]) for i in top8]

            fig_wf = go.Figure(go.Waterfall(orientation="h", y=h8, x=sv8,
                connector={"line": {"color": "#30363d"}},
                decreasing={"marker": {"color": "#f78166"}},
                increasing={"marker": {"color": "#3fb950"}},
                totals={"marker":    {"color": "#e3b341"}},
                hovertemplate="%{y}<br>Impact: %{x:.4f}<extra></extra>"))
            fig_wf.update_layout(**DARK_LAYOUT,
                title=dict(text=f"What drove prediction for {xent} in {int(xyr)}?", font=dict(size=14, family="Syne")),
                xaxis_title="Prediction Impact", height=440)
            st.plotly_chart(fig_wf, width="stretch")

            pos = [(h8[i], sv8[i]) for i in range(len(h8)) if sv8[i] > 0]
            neg = [(h8[i], sv8[i]) for i in range(len(h8)) if sv8[i] < 0]
            pt  = ", ".join([f"<strong>{n}</strong>" for n, _ in pos[:3]]) if pos else "none"
            nt  = ", ".join([f"<strong>{n}</strong>" for n, _ in neg[:3]]) if neg else "none"
            st.markdown(f'<div class="insight-card"><p>📌 <strong>Plain English:</strong> For {xent} in {int(xyr)}, the prediction was pushed <em>up</em> by {pt} and pulled <em>down</em> by {nt}.</p></div>', unsafe_allow_html=True)

    # ------------------------------------------------------------------ T5
    with t5:
        st.header("🗺️ Spatial Analysis")
        ly  = fd["year"].max()
        md  = fd[fd["year"] == ly].copy()
        msz = (md["value"] / md["value"].max() * 45 + 12).clip(12, 55)

        fig_map = go.Figure(go.Scattergeo(
            lon=md["longitude"], lat=md["latitude"],
            text=md["country"], mode="markers+text",
            marker=dict(size=msz, color=md["pred"], colorscale="RdYlGn", showscale=True,
                        colorbar=dict(title=f"Predicted<br>{vs}"), sizemode="diameter",
                        line=dict(width=2, color="#30363d")),
            textposition="top center",
            textfont=dict(color="#e6edf3", size=11, family="Syne"),
            hovertemplate=f"<b>%{{text}}</b><br>Actual: {upfx}%{{marker.color:,.2f}}<extra></extra>"))
        fig_map.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            title=dict(text=f"{vs} Distribution — Year {int(ly)}", font=dict(size=16, family="Syne", color="#e6edf3")),
            geo=dict(showland=True, landcolor="rgb(34,39,46)", coastlinecolor="rgb(48,54,61)",
                     projection_type="natural earth", showlakes=True, lakecolor="rgb(22,27,34)",
                     showocean=True, oceancolor="rgb(22,27,34)", bgcolor="rgba(0,0,0,0)"),
            font=dict(color="#e6edf3"), height=600)
        st.plotly_chart(fig_map, width="stretch")

        st.subheader("🌍 Regional Comparison")
        rs = fd.groupby("region").agg(avg=("value", "mean"), growth=("yoy_growth", "mean")).reset_index().sort_values("avg", ascending=False)

        # FIX-D7: secondary_y properly placed in add_trace()
        fig_reg = make_subplots(specs=[[{"secondary_y": True}]])
        fig_reg.add_trace(go.Bar(x=rs["region"], y=rs["avg"] / sc if sc > 1 else rs["avg"],
            name=f"Avg {vs}", marker_color=COLORS[:len(rs)]), secondary_y=False)
        fig_reg.add_trace(go.Scatter(x=rs["region"], y=rs["growth"], mode="lines+markers",
            name="Avg Growth %", line=dict(color="#e3b341", width=3), marker=dict(size=10)),
            secondary_y=True)   # FIX-D7
        fig_reg.update_layout(**DARK_LAYOUT,
            title=dict(text=f"Avg {vs} & Growth by Region", font=dict(size=15, family="Syne")),
            height=420,
            legend=dict(bgcolor="rgba(22,27,34,.7)", bordercolor="#30363d", borderwidth=1, orientation="h", y=-0.2),
        )
        fig_reg.update_yaxes(title_text=vl, secondary_y=False)
        fig_reg.update_yaxes(title_text="Avg YoY Growth %", secondary_y=True)
        st.plotly_chart(fig_reg, width="stretch")

    # ------------------------------------------------------------------ T6
    with t6:
        st.header("❓ Ask Why — Interactive Q&A")
        st.markdown('<div class="info-box"><h4>💡 How it works</h4><p>Pick an entity, a year, and your question. The system answers using SHAP model explanations.</p></div>', unsafe_allow_html=True)

        qa1, qa2 = st.columns(2)
        with qa1:
            qaent = st.selectbox(f"{el.capitalize()}:", sel, key="qaent")
            qayr  = st.selectbox("Year:", sorted(fd[fd["country"] == qaent]["year"].unique(), reverse=True), key="qayr")
        with qa2:
            qtype = st.selectbox("Your Question:", [
                f"Why did {vs} change?", "What drove the prediction?",
                "Which factors were most important?", "How does it compare to peers?",
                "What's the forecast trend?"])

        if st.button("🔍 Get Explanation", type="primary"):
            with st.spinner("Analysing..."):
                qd = fd[(fd["country"] == qaent) & (fd["year"] == qayr)]
                if len(qd):
                    qi    = qd.index[0]; qs = shap_vals[qi]
                    t5i   = np.argsort(np.abs(qs))[::-1][:5]
                    top5c = [(FEATURES[i], qs[i]) for i in t5i]
                    sn    = " *(synthetic)*" if syn_flags.get(qaent) else " *(live)*"
                    st.markdown(f'<div class="success-box"><h4>📊 Analysis: {qaent} — {int(qayr)}{sn}</h4></div>', unsafe_allow_html=True)

                    if f"Why did {vs} change?" == qtype:
                        yoy = qd["yoy_growth"].values[0]
                        st.markdown(f"**{vs} {'grew' if yoy > 0 else 'shrank'} by {abs(yoy):.2f}% year-over-year.**\n\n**Key Drivers:**")
                        for f, v in top5c:
                            sv = v / sc if sc > 1 else v
                            st.markdown(f"- **{FEATURE_NAMES_HUMAN.get(f, f)}** — {'↑ pushed up' if v > 0 else '↓ pulled down'} by {upfx}{abs(sv):.3f}")

                    elif qtype == "What drove the prediction?":
                        pv = qd["pred"].values[0]; av = qd["value"].values[0]
                        st.markdown(f"**Predicted:** {fmt(pv)} | **Actual:** {fmt(av)} | **Error:** {fmt(abs(pv - av))}\n\n**The model decided because:**")
                        for f, v in top5c:
                            sv = v / sc if sc > 1 else v
                            st.markdown(f"- **{FEATURE_NAMES_HUMAN.get(f, f)}** contributed {'+' if sv > 0 else ''}{upfx}{sv:.3f}")

                    elif qtype == "Which factors were most important?":
                        rows = [{"Factor": FEATURE_NAMES_HUMAN.get(f, f), "Technical Name": f,
                                 f"SHAP ({upfx})": round(v / sc if sc > 1 else v, 4),
                                 "Direction": "🔼 Increased" if v > 0 else "🔽 Decreased"} for f, v in top5c]
                        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

                    elif qtype == "How does it compare to peers?":
                        reg    = qd["region"].values[0]
                        ra     = fd[(fd["region"] == reg) & (fd["year"] == qayr)]["value"].mean()
                        ev     = qd["value"].values[0]
                        diff   = ((ev - ra) / ra * 100) if ra else 0
                        st.markdown(f"""
| | Value |
|---|---|
| **{qaent}** | {fmt(ev)} |
| Peer avg ({reg}) | {fmt(ra)} |
| Difference | {'+' if diff > 0 else ''}{diff:.2f}% |

{qaent} is **{'above ↑' if diff > 0 else 'below ↓'}** the regional peer average by **{abs(diff):.1f}%**.""")

                    elif qtype == "What's the forecast trend?":
                        hist = fd[fd["country"] == qaent].sort_values("year").tail(5)
                        tr   = hist["yoy_growth"].mean()
                        ev   = qd["value"].values[0]; fv = ev * (1 + tr / 100)
                        st.markdown(f"**5-Year Avg Growth:** {tr:.2f}%  \n**Projection for {int(qayr)+1}:** {fmt(fv)}")
                        yv = hist["value"] / sc if sc > 1 else hist["value"]
                        fig_fc = go.Figure()
                        fig_fc.add_trace(go.Scatter(x=hist["year"], y=yv, mode="lines+markers",
                            name="Historical", line=dict(width=3, color="#58a6ff")))
                        pj  = [int(qayr), int(qayr) + 1]
                        pjv = [ev / sc if sc > 1 else ev, fv / sc if sc > 1 else fv]
                        fig_fc.add_trace(go.Scatter(x=pj, y=pjv, mode="lines+markers",
                            name="Projection", line=dict(width=3, dash="dash", color="#3fb950"),
                            marker=dict(size=12, color="#3fb950")))
                        fig_fc.update_layout(**DARK_LAYOUT,
                            title=dict(text=f"{qaent} Trend & Projection", font=dict(size=14, family="Syne")),
                            xaxis_title="Year", yaxis_title=vl, height=400)
                        st.plotly_chart(fig_fc, width="stretch")
                else:
                    st.markdown('<div class="warning-box"><h4>⚠️ No data found</h4><p>Try a different year or entity.</p></div>', unsafe_allow_html=True)

    # ------------------------------------------------------------------ T7
    with t7:
        st.header("📥 Export Data & Insights")
        st.markdown('<div class="info-box"><h4>📦 Available exports</h4><p>Download data, predictions, SHAP values, or charts.</p></div>', unsafe_allow_html=True)

        e1, e2 = st.columns(2)
        with e1:
            st.subheader("📊 Data Downloads")
            clean = fd.drop(columns=["_synthetic"], errors="ignore")

            st.download_button("⬇️ Full Dataset (CSV)",
                data=to_csv(clean),
                file_name=f"econxai_data_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv", width="stretch")

            if _xlsxwriter_ok:
                st.download_button("⬇️ Full Dataset (Excel)",
                    data=to_excel(clean),
                    file_name=f"econxai_data_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch")
            else:
                st.info("Excel export: add `xlsxwriter` to requirements.txt and redeploy.")

            pred_only = fd[["country", "year", "value", "pred", "residual", "yoy_growth"]].copy()
            pred_only.columns = [el.capitalize(), "Year", "Actual", "Predicted", "Residual", "YoY Growth %"]
            st.download_button("⬇️ Predictions Only (CSV)",
                data=to_csv(pred_only),
                file_name=f"econxai_predictions_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv", width="stretch")

            sdf2 = pd.DataFrame(shap_vals, columns=FEATURES)
            sdf2[el]     = fd["country"].values
            sdf2["year"] = fd["year"].values
            sdf2 = sdf2.rename(columns=FEATURE_NAMES_HUMAN)
            st.download_button("⬇️ SHAP Values (CSV)",
                data=to_csv(sdf2),
                file_name=f"econxai_shap_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv", width="stretch")

        with e2:
            st.subheader("📈 Chart Downloads (PNG)")
            if not _kaleido_ok:
                st.info("PNG export needs `kaleido`. Add it to requirements.txt and redeploy.")
            else:
                fig_ex = go.Figure()
                for i, ent in enumerate(fd["country"].unique()):
                    cd = fd[fd["country"] == ent].sort_values("year")
                    yv = cd["value"] / sc if sc > 1 else cd["value"]
                    fig_ex.add_trace(go.Scatter(x=cd["year"], y=yv, mode="lines+markers",
                        name=ent, line=dict(width=3, color=COLORS[i % len(COLORS)])))
                fig_ex.update_layout(title=f"{vl} Trend", xaxis_title="Year",
                    yaxis_title=vl, height=500, template="plotly_white",
                    legend=dict(orientation="h"))
                try:
                    png = fig_ex.to_image(format="png", scale=2)
                    st.download_button("⬇️ Trend Chart (PNG)", data=png,
                        file_name=f"econxai_trend_{datetime.now().strftime('%Y%m%d')}.png",
                        mime="image/png", width="stretch")
                except Exception as e:
                    st.warning(f"PNG export failed: {e}")

                mean_shap2 = pd.Series(np.abs(shap_vals).mean(axis=0), index=FEATURES).sort_values()
                fig_sx = go.Figure(go.Bar(x=mean_shap2.values,
                    y=[FEATURE_NAMES_HUMAN.get(f, f) for f in mean_shap2.index],
                    orientation="h", marker_color="#58a6ff"))
                fig_sx.update_layout(title="Feature Importance (SHAP)",
                    xaxis_title="Mean |SHAP|", height=500, template="plotly_white")
                try:
                    png2 = fig_sx.to_image(format="png", scale=2)
                    st.download_button("⬇️ SHAP Importance Chart (PNG)", data=png2,
                        file_name=f"econxai_shap_chart_{datetime.now().strftime('%Y%m%d')}.png",
                        mime="image/png", width="stretch")
                except Exception:
                    pass

        st.markdown("---")
        st.subheader("📋 Data Preview (first 50 rows)")
        pc = ["country", "year", "value", "pred", "residual", "yoy_growth"]
        pv = fd[[c for c in pc if c in fd.columns]].head(50).copy()
        pv.columns = [c.replace("_", " ").title() for c in pv.columns]
        st.dataframe(pv, width="stretch", hide_index=True)

# ===========================================================================
# FOOTER
# ===========================================================================
st.markdown("---")
st.markdown("""
<div style="text-align:center;color:#8b949e;padding:1.2rem 0;font-size:.8rem;font-family:DM Sans;">
  <p style="font-family:Syne;font-size:.95rem;color:#e6edf3;font-weight:600;">EconXAI Dashboard v2.1</p>
  <p>Powered by <strong>XGBoost</strong> · <strong>SHAP</strong> · <strong>Streamlit</strong> · <strong>Plotly</strong></p>
  <p>📊 Data: World Bank API · Yahoo Finance (yfinance) · CoinGecko</p>
  <p>🟢 Live = fetched from API this session &nbsp;|&nbsp; 🟡 Synthetic = realistic fallback (API unreachable)</p>
</div>
""", unsafe_allow_html=True)
