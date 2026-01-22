"""Librarian Agent - Research, Data Collection & Discord Integration."""

import os
import json
import asyncio
import feedparser
import requests
import yfinance as yf
from datetime import datetime, timedelta
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from config import (
    SCAN_UNIVERSE, WATCHLIST, NEWS_SOURCES,
    POSITIVE_KEYWORDS, NEGATIVE_KEYWORDS, DISCORD_CHANNEL_ID
)

load_dotenv()


class Librarian:
    """Research, Data Extraction, Web Search & Discord Integration."""
    
    def __init__(self):
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        self.bot_token = os.getenv("DISCORD_BOT_TOKEN")
        self.universe = SCAN_UNIVERSE
        self.watchlist = WATCHLIST
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)
        self._discord_client = None
    
    # =========================================================================
    # FINANCIAL DATA COLLECTION
    # =========================================================================
    
    def fetch_stock_data(self, ticker: str) -> dict:
        """Fetch comprehensive stock data for scoring."""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="1y")
            
            # Price momentum
            current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
            
            # Calculate returns
            returns = {}
            if len(hist) > 0:
                for days, label in [(63, "3m"), (126, "6m"), (252, "12m")]:
                    if len(hist) >= days:
                        past_price = hist["Close"].iloc[-days] if len(hist) >= days else hist["Close"].iloc[0]
                        returns[label] = ((current_price - past_price) / past_price) * 100
                    else:
                        returns[label] = 0
            
            # RSI calculation (14-day)
            rsi = self._calculate_rsi(hist["Close"]) if len(hist) > 14 else 50
            
            # Fundamentals
            pe_ratio = info.get("trailingPE") or info.get("forwardPE", 0)
            peg_ratio = info.get("pegRatio", 0)
            fcf = info.get("freeCashflow", 0)
            market_cap = info.get("marketCap", 1)
            fcf_yield = (fcf / market_cap * 100) if market_cap else 0
            
            # Growth metrics
            revenue_growth = (info.get("revenueGrowth", 0) or 0) * 100
            earnings_growth = (info.get("earningsGrowth", 0) or 0) * 100
            
            # Dividend info
            dividend_yield = (info.get("trailingAnnualDividendYield", 0) or 0) * 100
            
            # Analyst sentiment
            analyst_rating = info.get("recommendationMean", 3)  # 1=Strong Buy, 5=Sell
            target_price = info.get("targetMeanPrice", current_price)
            upside = ((target_price - current_price) / current_price * 100) if current_price else 0
            
            # Sector
            sector = info.get("sector", "Unknown")
            
            return {
                "ticker": ticker,
                "price": current_price,
                "market_cap": market_cap,
                "sector": sector,
                "returns_3m": returns.get("3m", 0),
                "returns_6m": returns.get("6m", 0),
                "returns_12m": returns.get("12m", 0),
                "rsi": rsi,
                "pe_ratio": pe_ratio or 0,
                "peg_ratio": peg_ratio or 0,
                "fcf_yield": fcf_yield,
                "revenue_growth": revenue_growth,
                "earnings_growth": earnings_growth,
                "dividend_yield": dividend_yield,
                "analyst_rating": analyst_rating,
                "price_target": target_price,
                "upside_potential": upside,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"  Error fetching {ticker}: {e}")
            return {"ticker": ticker, "error": str(e)}
    
    def _calculate_rsi(self, prices, period=14):
        """Calculate RSI indicator."""
        if len(prices) < period + 1:
            return 50
        
        deltas = prices.diff()
        gain = (deltas.where(deltas > 0, 0)).rolling(window=period).mean()
        loss = (-deltas.where(deltas < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not rsi.empty else 50
    
    # =========================================================================
    # NEWS & SENTIMENT
    # =========================================================================
    
    def fetch_news(self, ticker: str) -> list:
        """Fetch news from free RSS sources."""
        articles = []
        
        for source_name, url_template in NEWS_SOURCES.items():
            try:
                url = url_template.format(ticker=ticker)
                feed = feedparser.parse(url)
                
                for entry in feed.entries[:5]:
                    articles.append({
                        "ticker": ticker,
                        "source": source_name,
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", ""),
                        "summary": entry.get("summary", "")[:500]
                    })
            except Exception as e:
                print(f"  News error {ticker}/{source_name}: {e}")
        
        return articles
    
    def analyze_sentiment(self, text: str) -> dict:
        """Keyword-based sentiment analysis."""
        text_lower = text.lower()
        
        positive_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
        negative_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)
        
        total = positive_count + negative_count + 1
        if positive_count > negative_count:
            return {"sentiment": "bullish", "score": positive_count / total}
        elif negative_count > positive_count:
            return {"sentiment": "bearish", "score": -negative_count / total}
        return {"sentiment": "neutral", "score": 0}
    
    # =========================================================================
    # WEB RESEARCH (General Purpose)
    # =========================================================================
    
    def web_search(self, query: str) -> list:
        """Perform web research via Google News RSS."""
        results = []
        try:
            search_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(search_url)
            
            for entry in feed.entries[:10]:
                sentiment = self.analyze_sentiment(entry.get("title", "") + " " + entry.get("summary", ""))
                results.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary": entry.get("summary", "")[:300],
                    "sentiment": sentiment
                })
        except Exception as e:
            print(f"  Web search error: {e}")
        
        return results
    
    def research_topic(self, topic: str) -> dict:
        """Research any topic and return summarized findings."""
        print(f"@Librarian: Researching '{topic}'...")
        
        results = self.web_search(topic)
        
        # Aggregate sentiment
        sentiments = [r["sentiment"]["score"] for r in results]
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0
        
        return {
            "topic": topic,
            "articles_found": len(results),
            "avg_sentiment": avg_sentiment,
            "overall": "bullish" if avg_sentiment > 0.1 else "bearish" if avg_sentiment < -0.1 else "neutral",
            "top_headlines": [r["title"] for r in results[:5]],
            "articles": results,
            "timestamp": datetime.now().isoformat()
        }
    
    # =========================================================================
    # DISCORD INTEGRATION
    # =========================================================================
    
    def send_discord_message(self, message: str, embeds: list = None):
        """Send message to Discord webhook."""
        if not self.webhook_url:
            print("Discord webhook not configured")
            return False
        
        payload = {"content": message}
        if embeds:
            payload["embeds"] = embeds
        
        try:
            response = requests.post(self.webhook_url, json=payload)
            return response.status_code == 204
        except Exception as e:
            print(f"Discord send error: {e}")
            return False
    
    def read_discord_messages(self, channel_id: str = None, limit: int = 50) -> list:
        """
        Read messages from Discord channel.
        Requires DISCORD_BOT_TOKEN with Message Content Intent enabled.
        """
        if not self.bot_token:
            print("Discord bot token not configured - cannot read messages")
            print("To enable: Add DISCORD_BOT_TOKEN to .env and set up bot at discord.com/developers")
            return []
        
        channel_id = channel_id or DISCORD_CHANNEL_ID
        if not channel_id:
            print("No Discord channel ID configured")
            return []
        
        headers = {
            "Authorization": f"Bot {self.bot_token}",
            "Content-Type": "application/json"
        }
        
        try:
            url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}"
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                messages = response.json()
                return [{
                    "author": msg.get("author", {}).get("username", "Unknown"),
                    "content": msg.get("content", ""),
                    "timestamp": msg.get("timestamp", ""),
                    "id": msg.get("id", "")
                } for msg in messages]
            else:
                print(f"Discord API error: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            print(f"Discord read error: {e}")
            return []
    
    def analyze_discord_chat(self, channel_id: str = None) -> dict:
        """Analyze Discord chat for stock mentions and sentiment."""
        messages = self.read_discord_messages(channel_id)
        
        if not messages:
            return {"error": "No messages retrieved"}
        
        # Find stock ticker mentions
        ticker_mentions = {}
        for msg in messages:
            content = msg["content"].upper()
            for ticker in self.universe:
                if f"${ticker}" in content or f" {ticker} " in content:
                    if ticker not in ticker_mentions:
                        ticker_mentions[ticker] = []
                    ticker_mentions[ticker].append({
                        "author": msg["author"],
                        "content": msg["content"],
                        "sentiment": self.analyze_sentiment(msg["content"])
                    })
        
        return {
            "messages_analyzed": len(messages),
            "ticker_mentions": ticker_mentions,
            "timestamp": datetime.now().isoformat()
        }
    
    # =========================================================================
    # DAILY UPDATE WORKFLOW
    # =========================================================================
    
    def create_daily_embed(self, data: list, news: list) -> list:
        """Create Discord embeds for daily update."""
        embeds = []
        
        # Top movers embed
        sorted_by_momentum = sorted(
            [d for d in data if "error" not in d],
            key=lambda x: x.get("returns_3m", 0),
            reverse=True
        )
        
        top_fields = []
        for d in sorted_by_momentum[:6]:
            emoji = "🟢" if d["returns_3m"] > 0 else "🔴"
            top_fields.append({
                "name": f"{emoji} {d['ticker']}",
                "value": f"3M: {d['returns_3m']:.1f}% | RSI: {d['rsi']:.0f}",
                "inline": True
            })
        
        embeds.append({
            "title": "📈 Capital Growth Engine - Daily Scan",
            "description": f"{datetime.now().strftime('%Y-%m-%d %H:%M')} CST",
            "color": 3066993,
            "fields": top_fields
        })
        
        # News sentiment
        if news:
            bullish = sum(1 for n in news if n.get("sentiment", {}).get("sentiment") == "bullish")
            bearish = sum(1 for n in news if n.get("sentiment", {}).get("sentiment") == "bearish")
            
            embeds.append({
                "title": "📰 News Sentiment",
                "description": f"Bullish: {bullish} | Bearish: {bearish} | Neutral: {len(news) - bullish - bearish}",
                "color": 15105570 if bearish > bullish else 3066993
            })
        
        return embeds
    
    def run_daily_scan(self, tickers: list = None):
        """Execute daily data collection."""
        tickers = tickers or self.watchlist
        print(f"@Librarian: Scanning {len(tickers)} stocks...")
        
        all_data = []
        all_news = []
        
        for ticker in tickers:
            print(f"  Fetching {ticker}...")
            data = self.fetch_stock_data(ticker)
            all_data.append(data)
            
            # Get news for watchlist
            if ticker in self.watchlist:
                articles = self.fetch_news(ticker)
                for article in articles[:2]:
                    sentiment = self.analyze_sentiment(article["title"] + " " + article.get("summary", ""))
                    article["sentiment"] = sentiment
                    all_news.append(article)
        
        # Save data
        output_path = os.path.join(self.data_dir, "market_data.json")
        with open(output_path, "w") as f:
            json.dump(all_data, f, indent=2)
        print(f"  Saved to {output_path}")
        
        news_path = os.path.join(self.data_dir, "news_data.json")
        with open(news_path, "w") as f:
            json.dump(all_news, f, indent=2)
        
        # Send Discord update
        embeds = self.create_daily_embed(all_data, all_news)
        self.send_discord_message("**CAPITAL GROWTH ENGINE - Daily Scan**", embeds)
        
        print("@Librarian: Scan complete. Tagging @Architect")
        return {"data": all_data, "news": all_news}
    
    def run_full_universe_scan(self):
        """Scan entire universe for opportunities."""
        return self.run_daily_scan(self.universe)


if __name__ == "__main__":
    librarian = Librarian()
    librarian.run_daily_scan()
