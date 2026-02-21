"""Auto-Improvement System - Suggests and applies parameter changes with approval."""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONFIG_FILE = Path("data/trading_config.json")
PENDING_IMPROVEMENTS_FILE = Path("data/pending_improvements.json")
IMPROVEMENT_HISTORY_FILE = Path("data/improvement_history.json")


class ImprovementType(Enum):
    """Types of improvements that can be suggested."""
    WEIGHT_ADJUSTMENT = "weight_adjustment"
    THRESHOLD_CHANGE = "threshold_change"
    FILTER_TOGGLE = "filter_toggle"
    POSITION_SIZE_ADJUSTMENT = "position_size_adjustment"
    STOP_LOSS_ADJUSTMENT = "stop_loss_adjustment"


class ImprovementStatus(Enum):
    """Status of an improvement suggestion."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


@dataclass
class TradingConfig:
    """Current trading configuration parameters."""
    # Confidence thresholds
    strong_buy_threshold: int = 85
    buy_threshold: int = 70
    min_confidence_for_entry: int = 60
    
    # Condition weights (1-10)
    vwap_weight: int = 10
    volume_weight: int = 9
    overextension_weight: int = 8
    dilution_weight: int = 8
    morning_rule_weight: int = 7
    support_weight: int = 7
    momentum_weight: int = 6
    near_support_weight: int = 6
    volume_health_weight: int = 5
    volatility_weight: int = 4
    
    # Filter thresholds
    overextension_max_percent: float = 12.0  # Max 7-day gain before flagging
    volume_min_ratio: float = 0.8  # Min volume vs 10-day average
    vwap_min_above_percent: float = 0.2  # Min % above VWAP
    
    # Position sizing
    max_position_percent: float = 20.0
    min_position_percent: float = 2.0
    base_position_percent: float = 10.0
    
    # Stop loss
    default_stop_loss_percent: float = 5.0
    tight_stop_loss_percent: float = 3.0
    wide_stop_loss_percent: float = 8.0
    
    # Earnings lockout
    earnings_lockout_days: int = 5
    
    # Sector crowding
    sector_crowding_threshold: int = 3


@dataclass
class ImprovementSuggestion:
    """A single improvement suggestion."""
    id: str
    timestamp: str
    improvement_type: str
    parameter: str
    current_value: Any
    suggested_value: Any
    reason: str
    expected_impact: str
    source_audit_date: str
    status: str = "pending"
    approved_date: str | None = None
    applied_date: str | None = None
    rejection_reason: str | None = None


class AutoImproveSystem:
    """Manages automatic improvement suggestions and approvals."""
    
    def __init__(self) -> None:
        self.config = self._load_config()
        self.pending: list[ImprovementSuggestion] = []
        self.history: list[ImprovementSuggestion] = []
        self._load_improvements()
    
    def _load_config(self) -> TradingConfig:
        """Load trading config from file."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    data = json.load(f)
                    return TradingConfig(**data)
            except Exception as e:
                logger.error(f"Error loading config: {e}")
        return TradingConfig()
    
    def _save_config(self) -> None:
        """Save trading config to file."""
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w") as f:
                json.dump(asdict(self.config), f, indent=2)
            logger.info("Trading config saved")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def _load_improvements(self) -> None:
        """Load pending improvements and history."""
        if PENDING_IMPROVEMENTS_FILE.exists():
            try:
                with open(PENDING_IMPROVEMENTS_FILE) as f:
                    data = json.load(f)
                    self.pending = [ImprovementSuggestion(**s) for s in data.get("suggestions", [])]
            except Exception as e:
                logger.error(f"Error loading pending improvements: {e}")
        
        if IMPROVEMENT_HISTORY_FILE.exists():
            try:
                with open(IMPROVEMENT_HISTORY_FILE) as f:
                    data = json.load(f)
                    self.history = [ImprovementSuggestion(**s) for s in data.get("history", [])]
            except Exception as e:
                logger.error(f"Error loading improvement history: {e}")
    
    def _save_improvements(self) -> None:
        """Save pending improvements and history."""
        try:
            PENDING_IMPROVEMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            
            with open(PENDING_IMPROVEMENTS_FILE, "w") as f:
                json.dump({"suggestions": [asdict(s) for s in self.pending]}, f, indent=2)
            
            with open(IMPROVEMENT_HISTORY_FILE, "w") as f:
                json.dump({"history": [asdict(s) for s in self.history]}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving improvements: {e}")
    
    def generate_suggestions_from_audit(
        self,
        accuracy: float,
        common_failures: list[str],
        weight_adjustments: dict[str, float],
    ) -> list[ImprovementSuggestion]:
        """Generate improvement suggestions from variance audit results."""
        suggestions: list[ImprovementSuggestion] = []
        audit_date = datetime.now().isoformat()
        
        # 1. Confidence threshold adjustments based on accuracy
        if accuracy < 50:
            suggestions.append(ImprovementSuggestion(
                id=f"conf_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                timestamp=datetime.now().isoformat(),
                improvement_type=ImprovementType.THRESHOLD_CHANGE.value,
                parameter="min_confidence_for_entry",
                current_value=self.config.min_confidence_for_entry,
                suggested_value=80,
                reason=f"Accuracy at {accuracy:.1f}% - too low. Raise minimum confidence to be more selective.",
                expected_impact="Fewer trades but higher quality entries",
                source_audit_date=audit_date,
            ))
        elif accuracy < 60:
            suggestions.append(ImprovementSuggestion(
                id=f"conf_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                timestamp=datetime.now().isoformat(),
                improvement_type=ImprovementType.THRESHOLD_CHANGE.value,
                parameter="buy_threshold",
                current_value=self.config.buy_threshold,
                suggested_value=75,
                reason=f"Accuracy at {accuracy:.1f}%. Raise BUY threshold from 70% to 75%.",
                expected_impact="More selective BUY signals",
                source_audit_date=audit_date,
            ))
        
        # 2. Weight adjustments based on failures
        for condition, adjustment in weight_adjustments.items():
            # Map condition name to config parameter
            param_map = {
                "vwap": "vwap_weight",
                "vwap_position": "vwap_weight",
                "volume": "volume_weight",
                "volume_confirmation": "volume_weight",
                "overextended": "overextension_weight",
                "not_overextended": "overextension_weight",
                "dilution": "dilution_weight",
                "morning": "morning_rule_weight",
                "support": "support_weight",
                "momentum": "momentum_weight",
            }
            
            param = None
            for key, value in param_map.items():
                if key in condition.lower():
                    param = value
                    break
            
            if param and abs(adjustment) >= 2:
                current = getattr(self.config, param, 5)
                new_value = max(1, min(10, current + int(adjustment / 2)))
                
                if new_value != current:
                    suggestions.append(ImprovementSuggestion(
                        id=f"weight_{param}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        timestamp=datetime.now().isoformat(),
                        improvement_type=ImprovementType.WEIGHT_ADJUSTMENT.value,
                        parameter=param,
                        current_value=current,
                        suggested_value=new_value,
                        reason=f"Condition '{condition}' frequently involved in failures. Adjust weight.",
                        expected_impact=f"{'Increase' if adjustment > 0 else 'Decrease'} importance of {param.replace('_', ' ')}",
                        source_audit_date=audit_date,
                    ))
        
        # 3. Filter threshold adjustments based on common failures
        for failure in common_failures:
            failure_lower = failure.lower()
            
            if "overextended" in failure_lower or "extended" in failure_lower:
                if self.config.overextension_max_percent > 8:
                    suggestions.append(ImprovementSuggestion(
                        id=f"ext_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        timestamp=datetime.now().isoformat(),
                        improvement_type=ImprovementType.THRESHOLD_CHANGE.value,
                        parameter="overextension_max_percent",
                        current_value=self.config.overextension_max_percent,
                        suggested_value=8.0,
                        reason="Chasing extended moves causing losses. Tighten overextension filter.",
                        expected_impact="Avoid entries on stocks up >8% in 7 days",
                        source_audit_date=audit_date,
                    ))
            
            if "vwap" in failure_lower:
                if self.config.vwap_min_above_percent < 0.5:
                    suggestions.append(ImprovementSuggestion(
                        id=f"vwap_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        timestamp=datetime.now().isoformat(),
                        improvement_type=ImprovementType.THRESHOLD_CHANGE.value,
                        parameter="vwap_min_above_percent",
                        current_value=self.config.vwap_min_above_percent,
                        suggested_value=0.5,
                        reason="VWAP rejections causing losses. Require stronger VWAP confirmation.",
                        expected_impact="Only enter when price is 0.5%+ above VWAP",
                        source_audit_date=audit_date,
                    ))
            
            if "stop" in failure_lower:
                if self.config.default_stop_loss_percent > 4:
                    suggestions.append(ImprovementSuggestion(
                        id=f"stop_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        timestamp=datetime.now().isoformat(),
                        improvement_type=ImprovementType.STOP_LOSS_ADJUSTMENT.value,
                        parameter="default_stop_loss_percent",
                        current_value=self.config.default_stop_loss_percent,
                        suggested_value=4.0,
                        reason="Stop losses too wide. Tighten to reduce losses.",
                        expected_impact="Smaller losses on failed trades",
                        source_audit_date=audit_date,
                    ))
        
        # 4. Position size adjustment if losing
        if accuracy < 50:
            if self.config.max_position_percent > 10:
                suggestions.append(ImprovementSuggestion(
                    id=f"pos_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    timestamp=datetime.now().isoformat(),
                    improvement_type=ImprovementType.POSITION_SIZE_ADJUSTMENT.value,
                    parameter="max_position_percent",
                    current_value=self.config.max_position_percent,
                    suggested_value=10.0,
                    reason=f"Accuracy at {accuracy:.1f}%. Reduce max position size to limit risk.",
                    expected_impact="Cap positions at 10% until accuracy improves",
                    source_audit_date=audit_date,
                ))
        
        # Add new suggestions to pending list
        for suggestion in suggestions:
            # Check if similar suggestion already pending
            existing = [s for s in self.pending if s.parameter == suggestion.parameter]
            if not existing:
                self.pending.append(suggestion)
        
        self._save_improvements()
        return suggestions
    
    def get_pending_suggestions(self) -> list[ImprovementSuggestion]:
        """Get all pending improvement suggestions."""
        return [s for s in self.pending if s.status == "pending"]
    
    def approve_suggestion(self, suggestion_id: str) -> tuple[bool, str]:
        """Approve and apply a suggestion."""
        for suggestion in self.pending:
            if suggestion.id == suggestion_id and suggestion.status == "pending":
                # Apply the change
                if hasattr(self.config, suggestion.parameter):
                    setattr(self.config, suggestion.parameter, suggestion.suggested_value)
                    self._save_config()
                    
                    suggestion.status = ImprovementStatus.APPLIED.value
                    suggestion.approved_date = datetime.now().isoformat()
                    suggestion.applied_date = datetime.now().isoformat()
                    
                    # Move to history
                    self.pending.remove(suggestion)
                    self.history.append(suggestion)
                    self._save_improvements()
                    
                    return True, f"Applied: {suggestion.parameter} = {suggestion.suggested_value}"
                else:
                    return False, f"Unknown parameter: {suggestion.parameter}"
        
        return False, "Suggestion not found or already processed"
    
    def reject_suggestion(self, suggestion_id: str, reason: str = "") -> tuple[bool, str]:
        """Reject a suggestion."""
        for suggestion in self.pending:
            if suggestion.id == suggestion_id and suggestion.status == "pending":
                suggestion.status = ImprovementStatus.REJECTED.value
                suggestion.rejection_reason = reason
                
                # Move to history
                self.pending.remove(suggestion)
                self.history.append(suggestion)
                self._save_improvements()
                
                return True, f"Rejected: {suggestion.parameter}"
        
        return False, "Suggestion not found or already processed"
    
    def approve_all_pending(self) -> list[str]:
        """Approve all pending suggestions."""
        results = []
        pending_copy = list(self.pending)
        
        for suggestion in pending_copy:
            if suggestion.status == "pending":
                success, msg = self.approve_suggestion(suggestion.id)
                results.append(msg)
        
        return results
    
    def get_config_summary(self) -> str:
        """Get current config as formatted string."""
        return f"""
**Current Trading Config:**
• Strong Buy Threshold: {self.config.strong_buy_threshold}%
• Buy Threshold: {self.config.buy_threshold}%
• Min Confidence: {self.config.min_confidence_for_entry}%
• Overextension Max: {self.config.overextension_max_percent}%
• Volume Min Ratio: {self.config.volume_min_ratio}
• VWAP Min Above: {self.config.vwap_min_above_percent}%
• Max Position: {self.config.max_position_percent}%
• Default Stop Loss: {self.config.default_stop_loss_percent}%
"""
    
    def format_pending_discord(self) -> str:
        """Format pending suggestions for Discord."""
        pending = self.get_pending_suggestions()
        
        if not pending:
            return "✅ No pending improvement suggestions."
        
        lines = [
            f"📋 **{len(pending)} Pending Improvements:**",
            "",
        ]
        
        for i, s in enumerate(pending, 1):
            lines.append(f"**{i}. {s.id}**")
            lines.append(f"   {s.parameter}: {s.current_value} → {s.suggested_value}")
            lines.append(f"   Reason: {s.reason}")
            lines.append(f"   Impact: {s.expected_impact}")
            lines.append("")
        
        lines.append("Use `!approve <id>` or `!approveall` to apply")
        lines.append("Use `!reject <id> [reason]` to reject")
        
        return "\n".join(lines)


# Global instance
_improve_system: AutoImproveSystem | None = None


def get_improve_system() -> AutoImproveSystem:
    """Get or create the auto-improve system."""
    global _improve_system
    if _improve_system is None:
        _improve_system = AutoImproveSystem()
    return _improve_system
