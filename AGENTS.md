# AGENTS.md - Capital Growth Engine

## Project Overview
Multi-factor investment analysis system with 3 AI agents:
- **Librarian**: Data collection, news sentiment, Discord integration
- **Architect**: Stock scoring (momentum, value, growth, sentiment, catalyst)
- **Trader**: Position sizing, risk management, human-in-the-loop approval

## Quick Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Run full pipeline (watchlist)
python main.py run

# Run full universe scan (50+ stocks)
python main.py run --universe

# Individual agents
python main.py librarian
python main.py architect
python main.py trader

# Research any topic
python main.py research "AI stocks"

# Schedule daily at 12:05 CST (runs continuously)
python main.py schedule
```

## Project Structure
```
my-investment-agents/
├── main.py              # Entry point, CLI commands
├── config.py            # Stock universe, scoring weights, risk settings
├── requirements.txt     # Python dependencies
├── .env.example         # Environment template (Discord webhook)
├── agents/
│   ├── librarian.py     # Data fetching, news, Discord
│   ├── architect.py     # Multi-factor scoring
│   └── trader.py        # Position sizing, risk
├── data/                # Output files (JSON, markdown reports)
└── .github/workflows/   # GitHub Actions for daily scans
```

## Environment Variables
- `DISCORD_WEBHOOK_URL` - For sending notifications (optional)
- `DISCORD_BOT_TOKEN` - For reading Discord messages (optional)

## Daily Automation
GitHub Actions runs daily at 12:05 PM CST. Configure the Discord webhook secret in repository settings.

## Key Files to Check
- `data/market_data.json` - Latest stock data
- `data/scored_candidates.json` - Scored and ranked stocks
- `data/factory_log.txt` - Execution plan awaiting approval
- `data/analysis_report.md` - Human-readable analysis

## Testing
No tests yet. To add: `pytest` with tests for scoring logic.

## Owner Intent
This is a personal investment tool. The owner wants:
1. Daily automated scans at 12:05 CST
2. Discord notifications with top picks
3. Human approval required before any execution
