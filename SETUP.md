# Capital Growth Engine - Setup Guide

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy environment template and add your Discord webhook
cp .env.example .env
# Edit .env and add your Discord webhook URL

# 3. Run once to test
python main.py run

# 4. Run with full universe scan
python main.py run --universe
```

## Getting Daily Updates Automatically

The script needs to run continuously OR be scheduled. Choose ONE option below:

---

### Option 1: Cron Job (Linux/Mac) - Recommended

This runs the script every day at 12:05 PM.

```bash
# Open crontab editor
crontab -e

# Add this line (adjust path to your actual location):
5 12 * * * cd /path/to/my-investment-agents && /usr/bin/python3 main.py run >> /tmp/investment-agents.log 2>&1
```

---

### Option 2: Windows Task Scheduler

1. Open Task Scheduler (search in Start menu)
2. Click "Create Basic Task"
3. Name: "Investment Agents Daily Update"
4. Trigger: Daily at 12:05 PM
5. Action: Start a program
   - Program: `python` or `C:\Python310\python.exe`
   - Arguments: `main.py run`
   - Start in: `C:\path\to\my-investment-agents`

---

### Option 3: Run Continuously (keeps running until you close it)

```bash
python main.py schedule
```

This will run at 12:05 CST every day, but stops when you close the terminal.

---

### Option 4: Systemd Service (Linux - runs on boot)

Create `/etc/systemd/system/investment-agents.service`:

```ini
[Unit]
Description=Capital Growth Engine
After=network.target

[Service]
Type=simple
User=yourusername
WorkingDirectory=/path/to/my-investment-agents
ExecStart=/usr/bin/python3 main.py schedule
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable it:
```bash
sudo systemctl enable investment-agents
sudo systemctl start investment-agents
```

---

### Option 5: GitHub Actions (runs even when computer is off)

See `.github/workflows/daily-scan.yml` - this runs in the cloud daily.

---

## Discord Setup

1. Go to your Discord server
2. Server Settings > Integrations > Webhooks
3. Create a webhook, copy the URL
4. Add to `.env`:
   ```
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
   ```

## Commands

```bash
python main.py run              # Run full pipeline (watchlist only)
python main.py run --universe   # Scan all 50+ stocks
python main.py librarian        # Just fetch data
python main.py architect        # Just score stocks
python main.py trader           # Just position sizing
python main.py research "AI stocks"  # Research any topic
python main.py schedule         # Run daily at 12:05 CST
```
