"""Trader Agent - Position Sizing, Risk Management & Execution."""

import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from config import (
    BASELINE_BUDGET, MAX_POSITION_SIZE, TRAILING_STOP_PERCENT,
    MAX_PORTFOLIO_DRAWDOWN, MAX_SECTOR_CONCENTRATION, KILL_SWITCHES
)

load_dotenv()


class Trader:
    """Position sizing, risk management, and human-in-the-loop execution."""
    
    def __init__(self):
        self.data_dir = "data"
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        self.budget = BASELINE_BUDGET
    
    def load_scored_candidates(self) -> dict:
        """Load scored candidates from Architect."""
        path = os.path.join(self.data_dir, "scored_candidates.json")
        if not os.path.exists(path):
            raise FileNotFoundError("scored_candidates.json not found. Run @Architect first.")
        
        with open(path, "r") as f:
            return json.load(f)
    
    # =========================================================================
    # POSITION SIZING
    # =========================================================================
    
    def calculate_position_size(self, candidate: dict) -> dict:
        """Calculate position size based on score and risk."""
        composite = candidate["scores"]["composite"]
        
        # Base position: 5% for score 60, up to 10% for score 100
        if composite >= 80:
            size_pct = MAX_POSITION_SIZE
        elif composite >= 70:
            size_pct = 0.08
        elif composite >= 60:
            size_pct = 0.06
        else:
            size_pct = 0.05
        
        position_value = self.budget * size_pct
        
        # Calculate shares
        price = candidate.get("price", 1)
        shares = int(position_value / price) if price > 0 else 0
        actual_value = shares * price
        
        return {
            "size_percent": size_pct * 100,
            "position_value": round(actual_value, 2),
            "shares": shares,
            "price": price
        }
    
    def calculate_stop_loss(self, candidate: dict) -> dict:
        """Calculate stop loss levels."""
        price = candidate.get("price", 0)
        
        # Trailing stop
        trailing_stop = price * (1 - TRAILING_STOP_PERCENT)
        
        # Hard stop based on volatility (use 3M return as proxy)
        ret_3m = abs(candidate.get("returns_3m", 10))
        volatility_factor = min(ret_3m / 100, 0.25)  # Cap at 25%
        hard_stop = price * (1 - max(volatility_factor, TRAILING_STOP_PERCENT))
        
        return {
            "entry_price": price,
            "trailing_stop": round(trailing_stop, 2),
            "trailing_stop_pct": TRAILING_STOP_PERCENT * 100,
            "hard_stop": round(hard_stop, 2),
            "hard_stop_pct": round((1 - hard_stop/price) * 100, 1) if price else 0
        }
    
    def calculate_profit_targets(self, candidate: dict) -> dict:
        """Calculate profit target levels."""
        price = candidate.get("price", 0)
        upside = candidate.get("upside_potential", 15)
        
        # Use analyst target as reference, with our own levels
        target_1 = price * 1.10  # 10% gain
        target_2 = price * 1.20  # 20% gain
        target_3 = price * (1 + upside/100) if upside > 20 else price * 1.30
        
        return {
            "target_1": {"price": round(target_1, 2), "gain_pct": 10, "action": "Sell 25%"},
            "target_2": {"price": round(target_2, 2), "gain_pct": 20, "action": "Sell 25%"},
            "target_3": {"price": round(target_3, 2), "gain_pct": round((target_3/price - 1) * 100, 1), "action": "Sell remaining"},
        }
    
    # =========================================================================
    # RISK ASSESSMENT
    # =========================================================================
    
    def assess_kill_switches(self, candidate: dict) -> list:
        """Identify active kill switch conditions."""
        warnings = []
        
        # Check if approaching any kill switch
        returns_3m = candidate.get("returns_3m", 0)
        if returns_3m < KILL_SWITCHES["price_drop_percent"] * 100:
            warnings.append({
                "type": "PRICE_DROP",
                "status": "TRIGGERED",
                "message": f"3M return {returns_3m:.1f}% below threshold"
            })
        
        # PE sanity check
        pe = candidate.get("pe_ratio", 0)
        if pe > 100:
            warnings.append({
                "type": "VALUATION",
                "status": "WARNING",
                "message": f"P/E ratio {pe:.1f} extremely high"
            })
        
        return warnings
    
    def check_sector_concentration(self, candidates: list) -> dict:
        """Check sector concentration risk."""
        sector_allocation = {}
        total_value = 0
        
        for c in candidates:
            sector = c.get("sector", "Unknown")
            position = self.calculate_position_size(c)
            value = position["position_value"]
            
            sector_allocation[sector] = sector_allocation.get(sector, 0) + value
            total_value += value
        
        # Calculate percentages
        concentration = {}
        warnings = []
        
        for sector, value in sector_allocation.items():
            pct = (value / total_value * 100) if total_value else 0
            concentration[sector] = round(pct, 1)
            
            if pct > MAX_SECTOR_CONCENTRATION * 100:
                warnings.append(f"{sector}: {pct:.1f}% (max {MAX_SECTOR_CONCENTRATION*100}%)")
        
        return {
            "allocation": concentration,
            "warnings": warnings,
            "diversified": len(warnings) == 0
        }
    
    # =========================================================================
    # EXECUTION PLAN
    # =========================================================================
    
    def generate_execution_plan(self, candidates: list) -> list:
        """Generate detailed execution plan for each candidate."""
        plans = []
        
        for candidate in candidates:
            position = self.calculate_position_size(candidate)
            stops = self.calculate_stop_loss(candidate)
            targets = self.calculate_profit_targets(candidate)
            warnings = self.assess_kill_switches(candidate)
            
            plans.append({
                "ticker": candidate["ticker"],
                "opportunity_type": candidate["opportunity_type"],
                "composite_score": candidate["scores"]["composite"],
                "sector": candidate.get("sector", "Unknown"),
                "position": position,
                "stops": stops,
                "targets": targets,
                "kill_switch_warnings": warnings,
                "risk_status": "CAUTION" if warnings else "CLEAR"
            })
        
        return plans
    
    def generate_factory_log(self, plans: list, sector_check: dict) -> str:
        """Generate the Factory Log for human review."""
        log = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║               CAPITAL GROWTH ENGINE - FACTORY LOG                            ║
║                      {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} CST                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

💰 BUDGET: ${self.budget:,.2f}
📊 CANDIDATES: {len(plans)}
🎯 STRATEGY: Multi-Factor (Momentum {30}% | Value {20}% | Growth {25}% | Sentiment {15}% | Catalyst {10}%)

"""
        
        # Sector concentration
        if sector_check["warnings"]:
            log += f"""
⚠️  SECTOR CONCENTRATION WARNING:
"""
            for w in sector_check["warnings"]:
                log += f"    • {w}\n"
        
        log += f"""
{'─'*80}
                              EXECUTION PLAN
{'─'*80}
"""
        
        for i, plan in enumerate(plans, 1):
            pos = plan["position"]
            stops = plan["stops"]
            targets = plan["targets"]
            
            risk_emoji = "🟢" if plan["risk_status"] == "CLEAR" else "🟡"
            
            log += f"""
┌──────────────────────────────────────────────────────────────────────────────┐
│  #{i} {plan['ticker']:6} │ {plan['opportunity_type']:20} │ Score: {plan['composite_score']:.0f}/100 {risk_emoji}
├──────────────────────────────────────────────────────────────────────────────┤
│  POSITION                                                                    │
│    • Size: {pos['size_percent']:.0f}% of portfolio (${pos['position_value']:,.2f})                           
│    • Shares: {pos['shares']} @ ${pos['price']:.2f}                                              
│    • Sector: {plan['sector']}                                                
├──────────────────────────────────────────────────────────────────────────────┤
│  RISK MANAGEMENT                                                             │
│    • Entry: ${stops['entry_price']:.2f}                                                        
│    • Stop Loss: ${stops['trailing_stop']:.2f} (-{stops['trailing_stop_pct']:.0f}%)                                     
│    • Hard Stop: ${stops['hard_stop']:.2f} (-{stops['hard_stop_pct']:.0f}%)                                       
├──────────────────────────────────────────────────────────────────────────────┤
│  PROFIT TARGETS                                                              │
│    • T1: ${targets['target_1']['price']:.2f} (+{targets['target_1']['gain_pct']}%) → {targets['target_1']['action']}                        
│    • T2: ${targets['target_2']['price']:.2f} (+{targets['target_2']['gain_pct']}%) → {targets['target_2']['action']}                       
│    • T3: ${targets['target_3']['price']:.2f} (+{targets['target_3']['gain_pct']:.0f}%) → {targets['target_3']['action']}                     
└──────────────────────────────────────────────────────────────────────────────┘
"""
            
            if plan["kill_switch_warnings"]:
                log += f"""
    ⚠️  WARNINGS:
"""
                for w in plan["kill_switch_warnings"]:
                    log += f"        • [{w['status']}] {w['type']}: {w['message']}\n"
        
        # Portfolio summary
        total_invested = sum(p["position"]["position_value"] for p in plans)
        cash_remaining = self.budget - total_invested
        
        log += f"""
{'─'*80}
                            PORTFOLIO SUMMARY
{'─'*80}

    Total Invested:    ${total_invested:,.2f}
    Cash Remaining:    ${cash_remaining:,.2f}
    Positions:         {len(plans)}
    
{'─'*80}

⚠️  CONSTRAINT: EXECUTION PAUSED - AWAITING HUMAN APPROVAL

    Commands:
    • "YES"              - Approve all positions
    • "YES <TICKER>"     - Approve specific position
    • "NO"               - Reject and revise
    • "SKIP <TICKER>"    - Remove from plan
    • "RESIZE <TICKER> <PCT>" - Adjust position size

{'─'*80}
"""
        
        return log
    
    def send_discord_alert(self, plans: list):
        """Send summary to Discord."""
        if not self.webhook_url:
            return
        
        fields = []
        for plan in plans[:5]:
            emoji = "🟢" if plan["risk_status"] == "CLEAR" else "🟡"
            fields.append({
                "name": f"{emoji} {plan['ticker']}",
                "value": f"Score: {plan['composite_score']:.0f} | ${plan['position']['position_value']:.0f}",
                "inline": True
            })
        
        embeds = [{
            "title": "🏭 Capital Growth Engine - Awaiting Approval",
            "description": f"{len(plans)} positions ready for review",
            "color": 15844367,
            "fields": fields,
            "footer": {"text": "Reply YES to approve"}
        }]
        
        try:
            requests.post(self.webhook_url, json={
                "content": "**@Trader Alert: Execution plan ready**",
                "embeds": embeds
            })
        except:
            pass
    
    # =========================================================================
    # MAIN WORKFLOW
    # =========================================================================
    
    def run_audit(self) -> dict:
        """Execute Trader workflow."""
        print("@Trader: Starting risk audit and position sizing...")
        
        data = self.load_scored_candidates()
        top_picks = data.get("top_picks", [])
        
        if not top_picks:
            print("  No top picks. Using top 5 candidates.")
            top_picks = data.get("candidates", [])[:5]
        
        # Generate execution plans
        plans = self.generate_execution_plan(top_picks)
        
        # Check sector concentration
        sector_check = self.check_sector_concentration(top_picks)
        
        # Generate Factory Log
        factory_log = self.generate_factory_log(plans, sector_check)
        
        # Save log
        log_path = os.path.join(self.data_dir, "factory_log.txt")
        with open(log_path, "w") as f:
            f.write(factory_log)
        
        # Print to console
        print(factory_log)
        
        # Send Discord notification
        self.send_discord_alert(plans)
        
        # Save execution data
        execution_data = {
            "timestamp": datetime.now().isoformat(),
            "status": "PENDING_APPROVAL",
            "budget": self.budget,
            "plans": plans,
            "sector_concentration": sector_check
        }
        
        exec_path = os.path.join(self.data_dir, "execution_plan.json")
        with open(exec_path, "w") as f:
            json.dump(execution_data, f, indent=2)
        
        print("@Trader: Audit complete. Awaiting human approval.")
        return execution_data


if __name__ == "__main__":
    trader = Trader()
    trader.run_audit()
