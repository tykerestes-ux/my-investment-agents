"""Adaptive Parameters - Self-improving system with user approval."""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PARAMS_FILE = Path("data/adaptive_params.json")
PENDING_FILE = Path("data/pending_suggestions.json")


@dataclass
class ParameterChange:
    """A single parameter change suggestion."""
    id: str
    timestamp: str
    parameter: str
    current_value: float
    suggested_value: float
    change_percent: float
    reason: str
    based_on_failures: int  # Number of failures this addresses
    status: str = "pending"  # pending, approved, rejected
    approved_date: str | None = None


@dataclass
class AdaptiveParameters:
    """Current active parameters for the trading system."""
    # Confidence thresholds
    strong_buy_threshold: float = 85.0
    buy_threshold: float = 70.0
    wait_threshold: float = 50.0
    
    # Condition weights (1-10)
    vwap_weight: int = 10
    volume_weight: int = 9
    overextension_weight: int = 8
    dilution_weight: int = 8
    morning_settled_weight: int = 7
    support_weight: int = 7
    momentum_weight: int = 6
    near_support_weight: int = 6
    volume_health_weight: int = 5
    volatility_weight: int = 4
    
    # Filter thresholds
    overextension_limit: float = 12.0  # Max 7-day % gain
    volume_min_ratio: float = 0.8  # Min volume vs 10-day avg
    vwap_buffer: float = 0.2  # Min % above VWAP
    morning_settle_minutes: int = 60  # Minutes after open
    intraday_range_max: float = 5.0  # Max intraday range %
    
    # Position sizing
    max_position_percent: float = 20.0
    min_position_percent: float = 2.0
    
    # Earnings lockout
    earnings_lockout_days: int = 5
    
    # News sentiment
    news_pause_threshold: int = 2  # Number of negative keywords
    
    # Multi-timeframe
    timeframe_min_alignment: int = 3  # Min aligned timeframes (out of 4)
    
    # Stop loss
    stop_loss_buffer: float = 2.0  # % below support
    
    last_updated: str = ""
    version: int = 1


class AdaptiveParameterManager:
    """Manages adaptive parameters with suggestion/approval workflow."""
    
    def __init__(self) -> None:
        self.params = AdaptiveParameters()
        self.pending_changes: list[ParameterChange] = []
        self.change_history: list[ParameterChange] = []
        self._load()
    
    def _load(self) -> None:
        """Load parameters and pending changes from files."""
        # Load active parameters
        if PARAMS_FILE.exists():
            try:
                with open(PARAMS_FILE) as f:
                    data = json.load(f)
                    for key, value in data.get("parameters", {}).items():
                        if hasattr(self.params, key):
                            setattr(self.params, key, value)
                    self.change_history = [
                        ParameterChange(**c) for c in data.get("history", [])
                    ]
                logger.info("Loaded adaptive parameters")
            except Exception as e:
                logger.error(f"Error loading parameters: {e}")
        
        # Load pending suggestions
        if PENDING_FILE.exists():
            try:
                with open(PENDING_FILE) as f:
                    data = json.load(f)
                    self.pending_changes = [
                        ParameterChange(**c) for c in data.get("pending", [])
                    ]
                logger.info(f"Loaded {len(self.pending_changes)} pending suggestions")
            except Exception as e:
                logger.error(f"Error loading pending suggestions: {e}")
    
    def _save(self) -> None:
        """Save parameters and history to file."""
        try:
            PARAMS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(PARAMS_FILE, "w") as f:
                json.dump({
                    "parameters": asdict(self.params),
                    "history": [asdict(c) for c in self.change_history[-50:]],  # Keep last 50
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving parameters: {e}")
    
    def _save_pending(self) -> None:
        """Save pending suggestions to file."""
        try:
            PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(PENDING_FILE, "w") as f:
                json.dump({
                    "pending": [asdict(c) for c in self.pending_changes],
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving pending suggestions: {e}")
    
    def suggest_change(
        self,
        parameter: str,
        suggested_value: float,
        reason: str,
        failures_addressed: int = 0,
    ) -> ParameterChange:
        """Create a new parameter change suggestion."""
        current_value = getattr(self.params, parameter, 0)
        change_pct = ((suggested_value - current_value) / current_value * 100) if current_value else 0
        
        change = ParameterChange(
            id=f"{parameter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.now().isoformat(),
            parameter=parameter,
            current_value=current_value,
            suggested_value=suggested_value,
            change_percent=change_pct,
            reason=reason,
            based_on_failures=failures_addressed,
        )
        
        self.pending_changes.append(change)
        self._save_pending()
        
        logger.info(f"Suggested change: {parameter} {current_value} -> {suggested_value}")
        return change
    
    def generate_suggestions_from_audit(
        self,
        accuracy: float,
        common_failures: list[str],
        weight_adjustments: dict[str, float],
    ) -> list[ParameterChange]:
        """Generate parameter suggestions from variance audit."""
        suggestions = []
        
        # Confidence threshold adjustments
        if accuracy < 50:
            suggestions.append(self.suggest_change(
                "strong_buy_threshold",
                min(95, self.params.strong_buy_threshold + 5),
                f"Accuracy at {accuracy:.0f}% - tighten strong buy threshold",
                failures_addressed=5,
            ))
            suggestions.append(self.suggest_change(
                "buy_threshold",
                min(85, self.params.buy_threshold + 5),
                f"Accuracy at {accuracy:.0f}% - tighten buy threshold",
                failures_addressed=5,
            ))
        
        # Weight adjustments based on failures
        weight_map = {
            "vwap": "vwap_weight",
            "volume": "volume_weight",
            "overextended": "overextension_weight",
            "not_overextended": "overextension_weight",
            "dilution": "dilution_weight",
            "morning": "morning_settled_weight",
            "support": "support_weight",
            "momentum": "momentum_weight",
            "volatility": "volatility_weight",
        }
        
        for key, adjustment in weight_adjustments.items():
            param_name = None
            for pattern, param in weight_map.items():
                if pattern in key.lower():
                    param_name = param
                    break
            
            if param_name and abs(adjustment) >= 2:
                current = getattr(self.params, param_name)
                # Increase weight if condition failures led to losses
                new_value = max(1, min(10, current + int(adjustment / 2)))
                
                if new_value != current:
                    suggestions.append(self.suggest_change(
                        param_name,
                        new_value,
                        f"Failures related to {key} - adjust weight",
                        failures_addressed=int(abs(adjustment)),
                    ))
        
        # Overextension limit
        if "extended" in str(common_failures).lower() or "overextended" in str(common_failures).lower():
            suggestions.append(self.suggest_change(
                "overextension_limit",
                max(5, self.params.overextension_limit - 2),
                "Chasing extended moves causing losses - tighten limit",
                failures_addressed=3,
            ))
        
        # VWAP buffer
        if "vwap" in str(common_failures).lower():
            suggestions.append(self.suggest_change(
                "vwap_buffer",
                min(1.0, self.params.vwap_buffer + 0.2),
                "VWAP rejections causing losses - require more buffer",
                failures_addressed=3,
            ))
        
        # Volume threshold
        if "volume" in str(common_failures).lower():
            suggestions.append(self.suggest_change(
                "volume_min_ratio",
                min(1.2, self.params.volume_min_ratio + 0.1),
                "Volume-related failures - require stronger volume",
                failures_addressed=2,
            ))
        
        return suggestions
    
    def approve_change(self, change_id: str) -> bool:
        """Approve and apply a pending change."""
        for change in self.pending_changes:
            if change.id == change_id:
                # Apply the change
                if hasattr(self.params, change.parameter):
                    setattr(self.params, change.parameter, change.suggested_value)
                    self.params.last_updated = datetime.now().isoformat()
                    self.params.version += 1
                    
                    # Update change status
                    change.status = "approved"
                    change.approved_date = datetime.now().isoformat()
                    
                    # Move to history
                    self.change_history.append(change)
                    self.pending_changes.remove(change)
                    
                    # Save
                    self._save()
                    self._save_pending()
                    
                    logger.info(f"Approved change: {change.parameter} -> {change.suggested_value}")
                    return True
        return False
    
    def reject_change(self, change_id: str) -> bool:
        """Reject a pending change."""
        for change in self.pending_changes:
            if change.id == change_id:
                change.status = "rejected"
                self.change_history.append(change)
                self.pending_changes.remove(change)
                
                self._save()
                self._save_pending()
                
                logger.info(f"Rejected change: {change.parameter}")
                return True
        return False
    
    def approve_all(self) -> int:
        """Approve all pending changes."""
        count = 0
        for change in list(self.pending_changes):
            if self.approve_change(change.id):
                count += 1
        return count
    
    def reject_all(self) -> int:
        """Reject all pending changes."""
        count = 0
        for change in list(self.pending_changes):
            if self.reject_change(change.id):
                count += 1
        return count
    
    def get_pending_summary(self) -> str:
        """Get summary of pending changes for Discord."""
        if not self.pending_changes:
            return "📋 No pending parameter suggestions."
        
        lines = [
            f"📋 **Pending Parameter Suggestions** ({len(self.pending_changes)} total)",
            "",
        ]
        
        for i, change in enumerate(self.pending_changes, 1):
            direction = "↑" if change.change_percent > 0 else "↓"
            lines.append(
                f"**{i}. {change.parameter}**\n"
                f"   {change.current_value} → {change.suggested_value} ({direction}{abs(change.change_percent):.1f}%)\n"
                f"   📝 {change.reason}\n"
                f"   ID: `{change.id}`"
            )
        
        lines.append("")
        lines.append("**Commands:**")
        lines.append("`!approve ID` - Approve specific change")
        lines.append("`!approveall` - Approve all changes")
        lines.append("`!reject ID` - Reject specific change")
        lines.append("`!rejectall` - Reject all changes")
        
        return "\n".join(lines)
    
    def get_current_params_summary(self) -> str:
        """Get summary of current parameters for Discord."""
        lines = [
            f"⚙️ **Current Parameters** (v{self.params.version})",
            "",
            "**Confidence Thresholds:**",
            f"• Strong Buy: {self.params.strong_buy_threshold}%",
            f"• Buy: {self.params.buy_threshold}%",
            f"• Wait: {self.params.wait_threshold}%",
            "",
            "**Condition Weights:**",
            f"• VWAP: {self.params.vwap_weight}/10",
            f"• Volume: {self.params.volume_weight}/10",
            f"• Overextension: {self.params.overextension_weight}/10",
            f"• Dilution: {self.params.dilution_weight}/10",
            "",
            "**Filter Thresholds:**",
            f"• Overextension Limit: {self.params.overextension_limit}%",
            f"• Min Volume Ratio: {self.params.volume_min_ratio}x",
            f"• VWAP Buffer: {self.params.vwap_buffer}%",
            f"• Earnings Lockout: {self.params.earnings_lockout_days} days",
            "",
            f"*Last updated: {self.params.last_updated or 'Never'}*",
        ]
        
        return "\n".join(lines)


# Global instance
_manager: AdaptiveParameterManager | None = None


def get_param_manager() -> AdaptiveParameterManager:
    """Get or create the parameter manager."""
    global _manager
    if _manager is None:
        _manager = AdaptiveParameterManager()
    return _manager


def get_params() -> AdaptiveParameters:
    """Get current parameters."""
    return get_param_manager().params
