"""Architect Agent - Multi-Factor Scoring & Ranking."""

import os
import json
from datetime import datetime
from config import (
    WEIGHTS, MAX_PE_RATIO, MAX_PEG_RATIO, MIN_FCF_YIELD,
    MIN_REVENUE_GROWTH, MIN_EPS_GROWTH, RSI_OVERSOLD, RSI_OVERBOUGHT
)


class Architect:
    """Multi-factor scoring: Momentum + Value + Growth + Sentiment."""
    
    def __init__(self):
        self.data_dir = "data"
        self.weights = WEIGHTS
    
    def load_market_data(self) -> list:
        """Load data from Librarian output."""
        path = os.path.join(self.data_dir, "market_data.json")
        if not os.path.exists(path):
            raise FileNotFoundError("market_data.json not found. Run @Librarian first.")
        
        with open(path, "r") as f:
            return json.load(f)
    
    def load_news_data(self) -> list:
        """Load news data for sentiment scoring."""
        path = os.path.join(self.data_dir, "news_data.json")
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return []
    
    # =========================================================================
    # SCORING COMPONENTS
    # =========================================================================
    
    def score_momentum(self, data: dict) -> float:
        """Score momentum (0-100): Price returns + RSI positioning."""
        score = 0
        
        # 3-month return (40% of momentum score)
        ret_3m = data.get("returns_3m", 0)
        if ret_3m > 30:
            score += 40
        elif ret_3m > 20:
            score += 35
        elif ret_3m > 10:
            score += 28
        elif ret_3m > 5:
            score += 20
        elif ret_3m > 0:
            score += 12
        elif ret_3m > -5:
            score += 5
        
        # 6-month return (30% of momentum score)
        ret_6m = data.get("returns_6m", 0)
        if ret_6m > 50:
            score += 30
        elif ret_6m > 30:
            score += 25
        elif ret_6m > 15:
            score += 18
        elif ret_6m > 0:
            score += 10
        
        # RSI positioning (30% of momentum score)
        rsi = data.get("rsi", 50)
        if RSI_OVERSOLD < rsi < 60:  # Sweet spot - not overbought
            score += 30
        elif 60 <= rsi < RSI_OVERBOUGHT:
            score += 20
        elif rsi <= RSI_OVERSOLD:  # Oversold = potential bounce
            score += 25
        elif rsi >= RSI_OVERBOUGHT:  # Overbought = risky
            score += 5
        
        return min(score, 100)
    
    def score_value(self, data: dict) -> float:
        """Score value (0-100): P/E, PEG, FCF Yield."""
        score = 0
        
        # P/E Ratio (40% of value score)
        pe = data.get("pe_ratio", 0)
        if pe <= 0:  # Negative or no earnings
            score += 0
        elif pe < 15:
            score += 40
        elif pe < 20:
            score += 32
        elif pe < 25:
            score += 24
        elif pe < MAX_PE_RATIO:
            score += 15
        else:
            score += 0  # Too expensive
        
        # PEG Ratio (30% of value score)
        peg = data.get("peg_ratio", 0)
        if 0 < peg < 1:
            score += 30  # Undervalued growth
        elif 1 <= peg < 1.5:
            score += 24
        elif 1.5 <= peg < MAX_PEG_RATIO:
            score += 15
        elif peg >= MAX_PEG_RATIO:
            score += 5
        
        # FCF Yield (30% of value score)
        fcf_yield = data.get("fcf_yield", 0)
        if fcf_yield > 8:
            score += 30
        elif fcf_yield > 5:
            score += 24
        elif fcf_yield > MIN_FCF_YIELD * 100:
            score += 18
        elif fcf_yield > 0:
            score += 10
        
        return min(score, 100)
    
    def score_growth(self, data: dict) -> float:
        """Score growth (0-100): Revenue + Earnings growth."""
        score = 0
        
        # Revenue growth (50% of growth score)
        rev_growth = data.get("revenue_growth", 0)
        if rev_growth > 30:
            score += 50
        elif rev_growth > 20:
            score += 42
        elif rev_growth > 10:
            score += 32
        elif rev_growth > MIN_REVENUE_GROWTH * 100:
            score += 22
        elif rev_growth > 0:
            score += 12
        
        # Earnings growth (50% of growth score)
        eps_growth = data.get("earnings_growth", 0)
        if eps_growth > 30:
            score += 50
        elif eps_growth > 20:
            score += 40
        elif eps_growth > 10:
            score += 30
        elif eps_growth > MIN_EPS_GROWTH * 100:
            score += 20
        elif eps_growth > 0:
            score += 10
        
        return min(score, 100)
    
    def score_sentiment(self, data: dict, news: list) -> float:
        """Score sentiment (0-100): Analyst rating + News sentiment."""
        score = 50  # Start neutral
        
        # Analyst rating (50% of sentiment)
        # Rating: 1 = Strong Buy, 2 = Buy, 3 = Hold, 4 = Sell, 5 = Strong Sell
        rating = data.get("analyst_rating", 3)
        if rating <= 1.5:
            score += 25
        elif rating <= 2:
            score += 20
        elif rating <= 2.5:
            score += 15
        elif rating <= 3:
            score += 5
        elif rating > 3:
            score -= 10
        
        # Upside potential
        upside = data.get("upside_potential", 0)
        if upside > 30:
            score += 15
        elif upside > 15:
            score += 10
        elif upside > 5:
            score += 5
        elif upside < -10:
            score -= 10
        
        # News sentiment (rest of score)
        ticker = data.get("ticker", "")
        ticker_news = [n for n in news if n.get("ticker") == ticker]
        
        if ticker_news:
            bullish = sum(1 for n in ticker_news if n.get("sentiment", {}).get("sentiment") == "bullish")
            bearish = sum(1 for n in ticker_news if n.get("sentiment", {}).get("sentiment") == "bearish")
            
            if bullish > bearish:
                score += min((bullish - bearish) * 5, 15)
            elif bearish > bullish:
                score -= min((bearish - bullish) * 5, 15)
        
        return max(0, min(score, 100))
    
    def score_catalyst(self, data: dict) -> float:
        """Score catalyst potential (0-100): Near-term catalysts."""
        score = 50  # Base score
        
        # Strong upside from analysts suggests catalyst expectation
        upside = data.get("upside_potential", 0)
        if upside > 20:
            score += 25
        elif upside > 10:
            score += 15
        
        # RSI oversold could mean bounce catalyst
        rsi = data.get("rsi", 50)
        if rsi < RSI_OVERSOLD:
            score += 15
        
        # High growth companies more likely to have positive surprises
        rev_growth = data.get("revenue_growth", 0)
        if rev_growth > 20:
            score += 10
        
        return min(score, 100)
    
    # =========================================================================
    # COMPOSITE SCORING
    # =========================================================================
    
    def calculate_composite_score(self, data: dict, news: list) -> dict:
        """Calculate weighted composite score."""
        momentum = self.score_momentum(data)
        value = self.score_value(data)
        growth = self.score_growth(data)
        sentiment = self.score_sentiment(data, news)
        catalyst = self.score_catalyst(data)
        
        # Weighted composite
        composite = (
            momentum * (self.weights["momentum"] / 100) +
            value * (self.weights["value"] / 100) +
            growth * (self.weights["growth"] / 100) +
            sentiment * (self.weights["sentiment"] / 100) +
            catalyst * (self.weights["catalyst"] / 100)
        )
        
        return {
            "momentum": round(momentum, 1),
            "value": round(value, 1),
            "growth": round(growth, 1),
            "sentiment": round(sentiment, 1),
            "catalyst": round(catalyst, 1),
            "composite": round(composite, 1)
        }
    
    def classify_opportunity(self, scores: dict, data: dict) -> str:
        """Classify the type of opportunity."""
        if scores["momentum"] > 70 and scores["growth"] > 60:
            return "MOMENTUM_GROWTH"
        elif scores["value"] > 70 and scores["growth"] > 50:
            return "VALUE_GROWTH"
        elif scores["momentum"] > 80:
            return "PURE_MOMENTUM"
        elif scores["value"] > 80:
            return "DEEP_VALUE"
        elif scores["catalyst"] > 75:
            return "CATALYST_PLAY"
        elif scores["composite"] > 60:
            return "BALANCED"
        return "SPECULATIVE"
    
    # =========================================================================
    # ANALYSIS WORKFLOW
    # =========================================================================
    
    def run_analysis(self) -> dict:
        """Execute full analysis workflow."""
        print("@Architect: Starting multi-factor analysis...")
        
        market_data = self.load_market_data()
        news_data = self.load_news_data()
        
        scored_candidates = []
        
        for data in market_data:
            if "error" in data:
                continue
            
            ticker = data["ticker"]
            scores = self.calculate_composite_score(data, news_data)
            opportunity_type = self.classify_opportunity(scores, data)
            
            scored_candidates.append({
                "ticker": ticker,
                "price": data.get("price", 0),
                "sector": data.get("sector", "Unknown"),
                "scores": scores,
                "opportunity_type": opportunity_type,
                "returns_3m": data.get("returns_3m", 0),
                "pe_ratio": data.get("pe_ratio", 0),
                "revenue_growth": data.get("revenue_growth", 0),
                "upside_potential": data.get("upside_potential", 0)
            })
        
        # Rank by composite score
        scored_candidates.sort(key=lambda x: x["scores"]["composite"], reverse=True)
        
        # Add rank
        for i, c in enumerate(scored_candidates, 1):
            c["rank"] = i
        
        # Top picks (composite > 60)
        top_picks = [c for c in scored_candidates if c["scores"]["composite"] >= 60]
        
        # Generate report
        self.generate_report(scored_candidates, top_picks)
        
        # Save results
        output = {
            "timestamp": datetime.now().isoformat(),
            "total_analyzed": len(scored_candidates),
            "top_picks_count": len(top_picks),
            "candidates": scored_candidates,
            "top_picks": top_picks
        }
        
        output_path = os.path.join(self.data_dir, "scored_candidates.json")
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)
        
        print(f"@Architect: Analysis complete. {len(top_picks)} opportunities identified. Tagging @Trader")
        return output
    
    def generate_report(self, candidates: list, top_picks: list):
        """Generate markdown report."""
        report = f"""# Capital Growth Engine - Analysis Report

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Scoring Weights
- Momentum: {self.weights['momentum']}%
- Value: {self.weights['value']}%
- Growth: {self.weights['growth']}%
- Sentiment: {self.weights['sentiment']}%
- Catalyst: {self.weights['catalyst']}%

---

## All Candidates (Ranked by Composite Score)

| Rank | Ticker | Composite | Mom | Val | Grw | Sent | Type | 3M Ret |
|------|--------|-----------|-----|-----|-----|------|------|--------|
"""
        
        for c in candidates:
            s = c["scores"]
            report += f"| {c['rank']} | **{c['ticker']}** | {s['composite']:.0f} | {s['momentum']:.0f} | {s['value']:.0f} | {s['growth']:.0f} | {s['sentiment']:.0f} | {c['opportunity_type']} | {c['returns_3m']:.1f}% |\n"
        
        if top_picks:
            report += f"""
---

## 🎯 Top Opportunities (Score >= 60)

"""
            for pick in top_picks[:5]:
                s = pick["scores"]
                report += f"""### #{pick['rank']} {pick['ticker']} - {pick['opportunity_type']}
- **Composite Score**: {s['composite']:.0f}/100
- **Breakdown**: Momentum {s['momentum']:.0f} | Value {s['value']:.0f} | Growth {s['growth']:.0f} | Sentiment {s['sentiment']:.0f}
- **Price**: ${pick['price']:.2f} | P/E: {pick['pe_ratio']:.1f} | Rev Growth: {pick['revenue_growth']:.1f}%
- **Upside Potential**: {pick['upside_potential']:.1f}%

"""
        
        report += """
---

*Report generated by @Architect. Pending @Trader review for position sizing and risk management.*
"""
        
        output_path = os.path.join(self.data_dir, "analysis_report.md")
        with open(output_path, "w") as f:
            f.write(report)
        
        print(f"  Report saved to {output_path}")


if __name__ == "__main__":
    architect = Architect()
    architect.run_analysis()
