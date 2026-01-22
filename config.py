"""Configuration for the Capital Growth Engine."""

# =============================================================================
# STRATEGY: Total Capital Growth (Momentum + Value + Growth + Catalysts)
# =============================================================================

# Dynamic universe - top liquid stocks across sectors
SCAN_UNIVERSE = [
    # Tech Giants
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    # Semiconductors
    "LRCX", "KLAC", "ASML", "AMAT", "TSM", "AMD", "AVGO", "QCOM",
    # Financials
    "JPM", "BAC", "GS", "MS", "V", "MA", "BLK",
    # Healthcare
    "UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK", "TMO",
    # Industrials
    "CAT", "DE", "HON", "UPS", "RTX", "LMT", "GE",
    # Consumer
    "COST", "WMT", "HD", "MCD", "SBUX", "NKE", "DIS",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG",
    # High Growth / Momentum plays
    "PLTR", "SNOW", "CRWD", "NET", "DDOG", "ZS", "PANW",
]

# User's focused watchlist (can be customized)
WATCHLIST = ["NVDA", "PLTR", "ASML", "LLY", "COST", "AVGO"]

# =============================================================================
# SCORING WEIGHTS (Total = 100)
# =============================================================================
WEIGHTS = {
    "momentum": 30,      # Price momentum (3m, 6m, 12m returns)
    "growth": 25,        # Revenue/EPS growth
    "value": 20,         # P/E, PEG, FCF yield
    "sentiment": 15,     # News sentiment, analyst ratings
    "catalyst": 10,      # Upcoming earnings, insider buying
}

# =============================================================================
# MOMENTUM CRITERIA
# =============================================================================
MOMENTUM_LOOKBACK_DAYS = [63, 126, 252]  # 3m, 6m, 12m
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# =============================================================================
# VALUE CRITERIA
# =============================================================================
MAX_PE_RATIO = 50           # Exclude extreme valuations
MAX_PEG_RATIO = 2.5         # Growth at reasonable price
MIN_FCF_YIELD = 0.02        # At least 2% FCF yield

# =============================================================================
# GROWTH CRITERIA
# =============================================================================
MIN_REVENUE_GROWTH = 0.05   # 5% minimum
MIN_EPS_GROWTH = 0.05       # 5% minimum

# =============================================================================
# RISK MANAGEMENT
# =============================================================================
MAX_POSITION_SIZE = 0.10    # 10% max per position
TRAILING_STOP_PERCENT = 0.15  # 15% trailing stop
MAX_PORTFOLIO_DRAWDOWN = 0.20  # 20% max drawdown kill switch
MAX_SECTOR_CONCENTRATION = 0.30  # 30% max in one sector

BASELINE_BUDGET = 10000  # Adjust based on your actual portfolio size

# =============================================================================
# KILL SWITCHES (Immediate Exit Triggers)
# =============================================================================
KILL_SWITCHES = {
    "earnings_miss_percent": -0.10,  # Exit if earnings miss by >10%
    "guidance_cut": True,            # Exit on guidance cut
    "insider_selling_threshold": 0.05,  # Exit if insiders sell >5% in 30 days
    "price_drop_percent": -0.20,     # Exit on 20% drop from entry
}

# =============================================================================
# NEWS & SENTIMENT
# =============================================================================
NEWS_SOURCES = {
    "yahoo_rss": "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US",
    "google_news": "https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en",
}

POSITIVE_KEYWORDS = [
    "beat", "exceeds", "raises", "upgrade", "bullish", "growth", "expansion",
    "record", "strong", "outperform", "buy", "accelerate", "surge", "breakout",
    "ai", "innovation", "partnership", "acquisition", "buyback", "profit"
]

NEGATIVE_KEYWORDS = [
    "miss", "disappoints", "cuts", "downgrade", "bearish", "decline", "weakness",
    "slump", "underperform", "sell", "warning", "layoffs", "lawsuit", "recall",
    "investigation", "fraud", "debt", "bankruptcy", "default"
]

# =============================================================================
# SCHEDULER
# =============================================================================
DAILY_UPDATE_TIME = "12:05"  # CST (Central Standard Time)
TIMEZONE = "America/Chicago"

# =============================================================================
# DISCORD
# =============================================================================
# Bot token for reading messages (optional - requires separate setup)
# DISCORD_BOT_TOKEN in .env for reading chat
# DISCORD_WEBHOOK_URL in .env for sending notifications
DISCORD_CHANNEL_ID = None  # Set to channel ID to monitor
