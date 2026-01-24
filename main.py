#!/usr/bin/env python3
"""Capital Growth Engine - Main Orchestrator."""

import argparse
import schedule
import time
from datetime import datetime
import pytz
from agents import Librarian, Architect, Trader


def run_full_pipeline(universe_scan: bool = False):
    """Execute the full agent pipeline."""
    print(f"\n{'='*70}")
    print(f"        CAPITAL GROWTH ENGINE v2.0 - Total Capital Growth")
    print(f"        Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    try:
        # Step 1: Librarian - Data Collection
        librarian = Librarian()
        if universe_scan:
            print("Running FULL UNIVERSE scan...")
            librarian_output = librarian.run_full_universe_scan()
        else:
            librarian_output = librarian.run_daily_scan()
        print()
        
        # Step 2: Architect - Multi-Factor Scoring
        architect = Architect()
        architect_output = architect.run_analysis()
        print()
        
        # Step 3: Trader - Position Sizing & Risk
        trader = Trader()
        trader_output = trader.run_audit()
        
        # Step 4: Send detailed Discord notification
        print("\n📤 Sending Discord notification...")
        top_picks = architect_output.get("top_picks", [])
        all_candidates = architect_output.get("candidates", [])
        librarian.send_detailed_discord_report(all_candidates, top_picks)
        
        print(f"\n{'='*70}")
        print(f"        Pipeline Complete: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}\n")
        
        return {
            "librarian": librarian_output,
            "architect": architect_output,
            "trader": trader_output
        }
        
    except Exception as e:
        print(f"\n❌ Pipeline Error: {e}")
        raise


def run_librarian_only(universe: bool = False):
    """Run only the Librarian agent."""
    librarian = Librarian()
    if universe:
        return librarian.run_full_universe_scan()
    return librarian.run_daily_scan()


def run_architect_only():
    """Run only the Architect agent."""
    architect = Architect()
    return architect.run_analysis()


def run_trader_only():
    """Run only the Trader agent."""
    trader = Trader()
    return trader.run_audit()


def research(query: str):
    """Perform web research on any topic."""
    librarian = Librarian()
    result = librarian.research_topic(query)
    
    print(f"\n{'='*60}")
    print(f"Research: {query}")
    print(f"{'='*60}")
    print(f"Articles Found: {result['articles_found']}")
    print(f"Overall Sentiment: {result['overall']} ({result['avg_sentiment']:.2f})")
    print(f"\nTop Headlines:")
    for i, headline in enumerate(result['top_headlines'], 1):
        print(f"  {i}. {headline}")
    print()
    
    return result


def read_discord(channel_id: str = None):
    """Read and analyze Discord chat."""
    librarian = Librarian()
    
    if channel_id:
        result = librarian.analyze_discord_chat(channel_id)
    else:
        result = librarian.analyze_discord_chat()
    
    print(f"\n{'='*60}")
    print(f"Discord Chat Analysis")
    print(f"{'='*60}")
    
    if "error" in result:
        print(f"Error: {result['error']}")
        print("\nTo enable Discord reading:")
        print("1. Create a bot at discord.com/developers")
        print("2. Enable 'Message Content Intent'")
        print("3. Add DISCORD_BOT_TOKEN to .env")
        print("4. Set DISCORD_CHANNEL_ID in config.py")
    else:
        print(f"Messages Analyzed: {result['messages_analyzed']}")
        print(f"\nTicker Mentions:")
        for ticker, mentions in result.get('ticker_mentions', {}).items():
            print(f"  ${ticker}: {len(mentions)} mentions")
    
    return result


def schedule_daily_updates():
    """Schedule daily updates at 12:05 CST."""
    cst = pytz.timezone('America/Chicago')
    
    print(f"Scheduling daily updates at 12:05 CST")
    print(f"Current time (CST): {datetime.now(cst).strftime('%Y-%m-%d %H:%M:%S')}")
    
    schedule.every().day.at("12:05").do(run_full_pipeline)
    
    print("\nScheduler started. Press Ctrl+C to stop.")
    print("Next run:", schedule.next_run())
    
    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(
        description="Capital Growth Engine - Total Capital Growth System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py run                    # Run full pipeline (watchlist)
  python main.py run --universe         # Run full pipeline (all stocks)
  python main.py librarian              # Just data collection
  python main.py architect              # Just scoring
  python main.py trader                 # Just position sizing
  python main.py research "AI stocks"   # Research any topic
  python main.py discord                # Read Discord chat
  python main.py schedule               # Schedule daily at 12:05 CST
        """
    )
    
    parser.add_argument(
        "command",
        choices=["run", "librarian", "architect", "trader", "research", "discord", "schedule"],
        help="Command to execute"
    )
    parser.add_argument(
        "--universe",
        action="store_true",
        help="Scan full universe instead of watchlist"
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        help="Research query (for 'research' command)"
    )
    parser.add_argument(
        "--channel",
        type=str,
        help="Discord channel ID (for 'discord' command)"
    )
    
    args = parser.parse_args()
    
    if args.command == "run":
        run_full_pipeline(universe_scan=args.universe)
    elif args.command == "librarian":
        run_librarian_only(universe=args.universe)
    elif args.command == "architect":
        run_architect_only()
    elif args.command == "trader":
        run_trader_only()
    elif args.command == "research":
        query = args.query or input("Enter research query: ")
        research(query)
    elif args.command == "discord":
        read_discord(args.channel)
    elif args.command == "schedule":
        schedule_daily_updates()


if __name__ == "__main__":
    main()
