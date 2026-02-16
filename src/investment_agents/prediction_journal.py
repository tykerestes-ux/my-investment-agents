"""Prediction Journal - Tracks predictions and outcomes for self-improvement."""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

JOURNAL_FILE = Path("data/prediction_journal.json")
AUDIT_FILE = Path("data/variance_audit.json")


class PredictionType(Enum):
    ENTRY_SIGNAL = "entry_signal"
    RISK_AUDIT = "risk_audit"
    VWAP_INTEGRITY = "vwap_integrity"
    HYPE_ALERT = "hype_alert"


class Outcome(Enum):
    PENDING = "pending"
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"


@dataclass
class Prediction:
    """A single prediction entry."""
    id: str
    timestamp: str
    symbol: str
    prediction_type: str
    signal: str  # e.g., "BUY", "AVOID", "HYPE_WARNING"
    confidence: int  # 0-100
    entry_price: float | None
    target_price: float | None
    stop_loss: float | None
    reasoning: str
    conditions_met: list[str]
    conditions_failed: list[str]
    outcome: str = "pending"
    outcome_price: float | None = None
    outcome_date: str | None = None
    outcome_notes: str | None = None
    pnl_percent: float | None = None
    lesson_learned: str | None = None


@dataclass
class VarianceAudit:
    """Daily variance analysis."""
    date: str
    predictions_made: int
    correct: int
    incorrect: int
    partial: int
    accuracy_rate: float
    biggest_win: dict | None
    biggest_loss: dict | None
    common_failures: list[str]
    weight_adjustments: dict[str, float]
    recommendations: list[str]


class PredictionJournal:
    """Manages prediction tracking and outcome analysis."""

    def __init__(self) -> None:
        self.predictions: list[Prediction] = []
        self.audits: list[VarianceAudit] = []
        self._load()

    def _load(self) -> None:
        """Load journal from file."""
        if JOURNAL_FILE.exists():
            try:
                with open(JOURNAL_FILE) as f:
                    data = json.load(f)
                    self.predictions = [Prediction(**p) for p in data.get("predictions", [])]
                logger.info(f"Loaded {len(self.predictions)} predictions from journal")
            except Exception as e:
                logger.error(f"Error loading journal: {e}")
                self.predictions = []

        if AUDIT_FILE.exists():
            try:
                with open(AUDIT_FILE) as f:
                    data = json.load(f)
                    self.audits = [VarianceAudit(**a) for a in data.get("audits", [])]
                logger.info(f"Loaded {len(self.audits)} audits")
            except Exception as e:
                logger.error(f"Error loading audits: {e}")
                self.audits = []

    def _save(self) -> None:
        """Save journal to file."""
        try:
            JOURNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(JOURNAL_FILE, "w") as f:
                json.dump({"predictions": [asdict(p) for p in self.predictions]}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving journal: {e}")

    def _save_audits(self) -> None:
        """Save audits to file."""
        try:
            AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(AUDIT_FILE, "w") as f:
                json.dump({"audits": [asdict(a) for a in self.audits]}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving audits: {e}")

    def log_prediction(
        self,
        symbol: str,
        prediction_type: PredictionType,
        signal: str,
        confidence: int,
        reasoning: str,
        conditions_met: list[str],
        conditions_failed: list[str],
        entry_price: float | None = None,
        target_price: float | None = None,
        stop_loss: float | None = None,
    ) -> str:
        """Log a new prediction."""
        pred_id = f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        prediction = Prediction(
            id=pred_id,
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            prediction_type=prediction_type.value,
            signal=signal,
            confidence=confidence,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss=stop_loss,
            reasoning=reasoning,
            conditions_met=conditions_met,
            conditions_failed=conditions_failed,
        )

        self.predictions.append(prediction)
        self._save()
        logger.info(f"Logged prediction: {pred_id} - {signal} for {symbol}")
        return pred_id

    def update_outcome(
        self,
        pred_id: str,
        outcome: Outcome,
        outcome_price: float,
        notes: str = "",
    ) -> bool:
        """Update prediction with actual outcome."""
        for pred in self.predictions:
            if pred.id == pred_id:
                pred.outcome = outcome.value
                pred.outcome_price = outcome_price
                pred.outcome_date = datetime.now().isoformat()
                pred.outcome_notes = notes

                # Calculate P&L if entry price exists
                if pred.entry_price and outcome_price:
                    pred.pnl_percent = ((outcome_price - pred.entry_price) / pred.entry_price) * 100

                    # Determine lesson learned
                    if outcome == Outcome.INCORRECT:
                        pred.lesson_learned = self._analyze_failure(pred)

                self._save()
                return True
        return False

    def _analyze_failure(self, pred: Prediction) -> str:
        """Analyze why a prediction failed."""
        lessons = []

        if pred.conditions_failed:
            lessons.append(f"Ignored warnings: {', '.join(pred.conditions_failed[:3])}")

        if pred.confidence < 70:
            lessons.append("Entered with low confidence - wait for better setup")

        if pred.pnl_percent and pred.pnl_percent < -5:
            lessons.append("Stop loss may have been too wide")

        if "VWAP" in str(pred.conditions_failed):
            lessons.append("VWAP rejection - institutional selling pressure")

        if "Overextended" in str(pred.conditions_failed):
            lessons.append("Chased extended move - wait for pullback")

        return "; ".join(lessons) if lessons else "Requires manual review"

    def get_pending_predictions(self, older_than_hours: int = 24) -> list[Prediction]:
        """Get predictions that need outcome updates."""
        cutoff = datetime.now() - timedelta(hours=older_than_hours)
        pending = []

        for pred in self.predictions:
            if pred.outcome == "pending":
                pred_time = datetime.fromisoformat(pred.timestamp)
                if pred_time < cutoff:
                    pending.append(pred)

        return pending

    def run_variance_analysis(self) -> VarianceAudit:
        """Run daily variance analysis and generate audit report."""
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        # Get yesterday's predictions that have outcomes
        relevant = [
            p for p in self.predictions
            if p.outcome != "pending"
            and datetime.fromisoformat(p.timestamp).date() >= yesterday
        ]

        if not relevant:
            # Look at last 7 days if no recent data
            week_ago = today - timedelta(days=7)
            relevant = [
                p for p in self.predictions
                if p.outcome != "pending"
                and datetime.fromisoformat(p.timestamp).date() >= week_ago
            ]

        correct = [p for p in relevant if p.outcome == "correct"]
        incorrect = [p for p in relevant if p.outcome == "incorrect"]
        partial = [p for p in relevant if p.outcome == "partial"]

        accuracy = len(correct) / len(relevant) * 100 if relevant else 0

        # Find biggest win/loss
        biggest_win = None
        biggest_loss = None

        for p in correct:
            if p.pnl_percent and (biggest_win is None or p.pnl_percent > biggest_win.get("pnl", 0)):
                biggest_win = {"symbol": p.symbol, "pnl": p.pnl_percent, "signal": p.signal}

        for p in incorrect:
            if p.pnl_percent and (biggest_loss is None or p.pnl_percent < biggest_loss.get("pnl", 0)):
                biggest_loss = {"symbol": p.symbol, "pnl": p.pnl_percent, "signal": p.signal}

        # Analyze common failures
        failure_reasons = []
        for p in incorrect:
            if p.lesson_learned:
                failure_reasons.append(p.lesson_learned)

        # Count failure patterns
        failure_counts: dict[str, int] = {}
        for reason in failure_reasons:
            for part in reason.split(";"):
                part = part.strip()
                if part:
                    failure_counts[part] = failure_counts.get(part, 0) + 1

        common_failures = sorted(failure_counts.keys(), key=lambda x: failure_counts[x], reverse=True)[:5]

        # Calculate weight adjustments based on failures
        weight_adjustments = self._calculate_weight_adjustments(incorrect)

        # Generate recommendations
        recommendations = self._generate_recommendations(common_failures, accuracy)

        audit = VarianceAudit(
            date=today.isoformat(),
            predictions_made=len(relevant),
            correct=len(correct),
            incorrect=len(incorrect),
            partial=len(partial),
            accuracy_rate=accuracy,
            biggest_win=biggest_win,
            biggest_loss=biggest_loss,
            common_failures=common_failures,
            weight_adjustments=weight_adjustments,
            recommendations=recommendations,
        )

        self.audits.append(audit)
        self._save_audits()

        return audit

    def _calculate_weight_adjustments(self, incorrect: list[Prediction]) -> dict[str, float]:
        """Calculate suggested weight adjustments based on failures."""
        adjustments: dict[str, float] = {}

        for pred in incorrect:
            # If we ignored a failed condition and lost, increase its weight
            for condition in pred.conditions_failed:
                key = condition.lower().replace(" ", "_")
                adjustments[key] = adjustments.get(key, 0) + 2.5  # Increase weight

            # If conditions were met but still failed, consider decreasing
            if not pred.conditions_failed and pred.conditions_met:
                for condition in pred.conditions_met[:2]:
                    key = condition.lower().replace(" ", "_")
                    adjustments[key] = adjustments.get(key, 0) - 1.0  # Slight decrease

        return adjustments

    def _generate_recommendations(self, common_failures: list[str], accuracy: float) -> list[str]:
        """Generate actionable recommendations."""
        recs = []

        if accuracy < 50:
            recs.append("CRITICAL: Accuracy below 50%. Consider reducing position sizes until patterns stabilize.")

        if accuracy < 70:
            recs.append("Increase confidence threshold from 70% to 80% before entering trades.")

        if "VWAP" in str(common_failures):
            recs.append("VWAP failures detected. Add requirement: Price must hold VWAP for 30+ minutes before entry.")

        if "Overextended" in str(common_failures) or "extended" in str(common_failures).lower():
            recs.append("Chasing extended moves. Add filter: No entry if 7-day gain > 8%.")

        if "confidence" in str(common_failures).lower():
            recs.append("Low-confidence trades failing. Only enter STRONG_BUY signals for next 5 days.")

        if "stop" in str(common_failures).lower():
            recs.append("Consider tighter stop losses. Current stops may be too wide for volatility.")

        if not recs:
            if accuracy >= 70:
                recs.append("System performing well. Maintain current parameters.")
            else:
                recs.append("Review individual trade notes for specific improvement areas.")

        return recs

    def get_stats(self, days: int = 30) -> dict[str, Any]:
        """Get performance statistics."""
        cutoff = datetime.now() - timedelta(days=days)
        relevant = [
            p for p in self.predictions
            if datetime.fromisoformat(p.timestamp) >= cutoff
        ]

        total = len(relevant)
        resolved = [p for p in relevant if p.outcome != "pending"]
        correct = len([p for p in resolved if p.outcome == "correct"])
        incorrect = len([p for p in resolved if p.outcome == "incorrect"])

        total_pnl = sum(p.pnl_percent or 0 for p in resolved if p.pnl_percent)
        avg_pnl = total_pnl / len(resolved) if resolved else 0

        return {
            "period_days": days,
            "total_predictions": total,
            "resolved": len(resolved),
            "pending": total - len(resolved),
            "correct": correct,
            "incorrect": incorrect,
            "accuracy": correct / len(resolved) * 100 if resolved else 0,
            "total_pnl_percent": total_pnl,
            "avg_pnl_percent": avg_pnl,
        }

    def get_recent_predictions(self, limit: int = 10) -> list[Prediction]:
        """Get most recent predictions."""
        return sorted(self.predictions, key=lambda x: x.timestamp, reverse=True)[:limit]

    def format_prediction_discord(self, pred: Prediction) -> str:
        """Format a prediction for Discord."""
        outcome_emoji = {
            "pending": "⏳",
            "correct": "✅",
            "incorrect": "❌",
            "partial": "🟡",
        }

        emoji = outcome_emoji.get(pred.outcome, "❓")
        lines = [
            f"{emoji} **{pred.symbol}** - {pred.signal} ({pred.confidence}%)",
            f"Type: {pred.prediction_type} | {pred.timestamp[:10]}",
        ]

        if pred.entry_price:
            lines.append(f"Entry: ${pred.entry_price:.2f}")

        if pred.outcome != "pending" and pred.pnl_percent is not None:
            pnl_emoji = "📈" if pred.pnl_percent > 0 else "📉"
            lines.append(f"{pnl_emoji} P&L: {pred.pnl_percent:+.1f}%")

        if pred.lesson_learned:
            lines.append(f"📝 Lesson: {pred.lesson_learned}")

        return "\n".join(lines)

    def format_audit_discord(self, audit: VarianceAudit) -> str:
        """Format variance audit for Discord."""
        lines = [
            f"📊 **Variance Audit - {audit.date}**",
            "",
            f"**Performance:**",
            f"• Predictions: {audit.predictions_made}",
            f"• Accuracy: {audit.accuracy_rate:.1f}%",
            f"• ✅ Correct: {audit.correct} | ❌ Incorrect: {audit.incorrect}",
        ]

        if audit.biggest_win:
            lines.append(f"• 🏆 Best: {audit.biggest_win['symbol']} +{audit.biggest_win['pnl']:.1f}%")

        if audit.biggest_loss:
            lines.append(f"• 💀 Worst: {audit.biggest_loss['symbol']} {audit.biggest_loss['pnl']:.1f}%")

        if audit.common_failures:
            lines.append("")
            lines.append("**Common Failures:**")
            for failure in audit.common_failures[:3]:
                lines.append(f"• {failure}")

        if audit.recommendations:
            lines.append("")
            lines.append("**Recommendations:**")
            for rec in audit.recommendations[:3]:
                lines.append(f"• {rec}")

        return "\n".join(lines)


# Global instance
_journal: PredictionJournal | None = None


def get_journal() -> PredictionJournal:
    """Get or create the prediction journal."""
    global _journal
    if _journal is None:
        _journal = PredictionJournal()
    return _journal
