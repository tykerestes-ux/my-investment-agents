"""News Sentiment Filter - Detect negative headlines that could impact trades."""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

import yfinance as yf

logger = logging.getLogger(__name__)

# Negative keywords that should trigger a warning
NEGATIVE_KEYWORDS = [
    # Legal/Regulatory
    "lawsuit", "sued", "litigation", "settlement", "class action",
    "sec investigation", "investigation", "subpoena", "fraud",
    "indictment", "criminal", "violation", "penalty", "fine",
    "regulatory", "antitrust", "ftc", "doj",
    
    # Financial distress
    "bankruptcy", "default", "restructuring", "layoffs", "layoff",
    "downsizing", "cost cutting", "writedown", "impairment",
    "guidance cut", "lowers guidance", "misses estimates",
    "revenue miss", "earnings miss", "profit warning",
    
    # Product/Safety
    "recall", "safety issue", "defect", "malfunction",
    "fda warning", "product failure", "cybersecurity breach",
    "data breach", "hack", "hacked",
    
    # Leadership
    "ceo resigns", "cfo resigns", "executive departure",
    "management shake", "accounting issue", "restatement",
    
    # Market sentiment
    "downgrade", "sell rating", "price target cut",
    "short seller", "short report", "bear case",
    "overvalued", "bubble",
    
    # Geopolitical
    "tariff", "sanctions", "ban", "blacklist", "export controls",
]

# Positive keywords (for context)
POSITIVE_KEYWORDS = [
    "upgrade", "buy rating", "price target raise",
    "beats estimates", "revenue beat", "earnings beat",
    "record revenue", "guidance raise", "raises guidance",
    "contract win", "partnership", "acquisition",
    "fda approval", "breakthrough",
]


@dataclass
class NewsAnalysis:
    """News sentiment analysis result."""
    symbol: str
    headlines: list[str]
    negative_found: bool
    negative_headlines: list[str]
    negative_keywords_found: list[str]
    positive_found: bool
    sentiment_score: int  # -10 to +10
    should_pause: bool
    warning_message: str | None


def analyze_news_sentiment(symbol: str) -> NewsAnalysis:
    """Analyze recent news for negative sentiment.
    
    Uses yfinance news feed (free, no API key needed).
    """
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        
        if not news:
            return NewsAnalysis(
                symbol=symbol,
                headlines=[],
                negative_found=False,
                negative_headlines=[],
                negative_keywords_found=[],
                positive_found=False,
                sentiment_score=0,
                should_pause=False,
                warning_message=None,
            )
        
        headlines = []
        negative_headlines = []
        negative_keywords_found = []
        positive_count = 0
        negative_count = 0
        
        for article in news[:10]:  # Check last 10 articles
            title = article.get("title", "").lower()
            headlines.append(article.get("title", ""))
            
            # Check for negative keywords
            for keyword in NEGATIVE_KEYWORDS:
                if keyword in title:
                    negative_headlines.append(article.get("title", ""))
                    if keyword not in negative_keywords_found:
                        negative_keywords_found.append(keyword)
                    negative_count += 1
                    break
            
            # Check for positive keywords
            for keyword in POSITIVE_KEYWORDS:
                if keyword in title:
                    positive_count += 1
                    break
        
        # Calculate sentiment score (-10 to +10)
        sentiment_score = min(10, max(-10, positive_count * 2 - negative_count * 3))
        
        # Determine if we should pause trading
        # Pause if significant negative news found
        should_pause = len(negative_keywords_found) >= 2 or any(
            kw in negative_keywords_found for kw in [
                "lawsuit", "sec investigation", "fraud", "bankruptcy",
                "recall", "data breach", "criminal"
            ]
        )
        
        warning_message = None
        if should_pause:
            warning_message = (
                f"NEGATIVE NEWS ALERT: Found {len(negative_keywords_found)} risk keywords: "
                f"{', '.join(negative_keywords_found[:5])}"
            )
        elif negative_keywords_found:
            warning_message = (
                f"Minor negative news: {', '.join(negative_keywords_found[:3])}"
            )
        
        return NewsAnalysis(
            symbol=symbol,
            headlines=headlines,
            negative_found=len(negative_headlines) > 0,
            negative_headlines=negative_headlines[:5],
            negative_keywords_found=negative_keywords_found,
            positive_found=positive_count > 0,
            sentiment_score=sentiment_score,
            should_pause=should_pause,
            warning_message=warning_message,
        )
        
    except Exception as e:
        logger.error(f"Error analyzing news for {symbol}: {e}")
        return NewsAnalysis(
            symbol=symbol,
            headlines=[],
            negative_found=False,
            negative_headlines=[],
            negative_keywords_found=[],
            positive_found=False,
            sentiment_score=0,
            should_pause=False,
            warning_message=None,
        )


def check_news_sentiment(symbol: str) -> tuple[bool, str | None]:
    """Quick check if news sentiment is negative.
    
    Returns:
        (should_pause, warning_message)
    """
    analysis = analyze_news_sentiment(symbol)
    return analysis.should_pause, analysis.warning_message


def format_news_discord(analysis: NewsAnalysis) -> str:
    """Format news analysis for Discord."""
    if not analysis.headlines:
        return f"📰 **{analysis.symbol}**: No recent news found"
    
    if analysis.should_pause:
        emoji = "🚨"
        status = "PAUSE RECOMMENDED"
    elif analysis.negative_found:
        emoji = "⚠️"
        status = "CAUTION"
    else:
        emoji = "✅"
        status = "CLEAR"
    
    lines = [
        f"{emoji} **News Sentiment: {analysis.symbol}** - {status}",
        f"Sentiment Score: {analysis.sentiment_score:+d}/10",
    ]
    
    if analysis.warning_message:
        lines.append(f"⚠️ {analysis.warning_message}")
    
    if analysis.negative_headlines:
        lines.append("\n**Concerning Headlines:**")
        for headline in analysis.negative_headlines[:3]:
            lines.append(f"• {headline[:80]}...")
    
    if not analysis.negative_found and analysis.headlines:
        lines.append(f"\n✅ No negative keywords in {len(analysis.headlines)} recent headlines")
    
    return "\n".join(lines)
