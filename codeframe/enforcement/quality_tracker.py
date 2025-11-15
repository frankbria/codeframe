"""
Generic Quality Tracker

Tracks quality metrics across sessions for ANY language, not just Python.
This is the language-agnostic version of scripts/quality-ratchet.py.

Metrics tracked:
- Test pass rate
- Coverage percentage
- Response count (AI conversation length)
- Timestamp

Stored in: .codeframe/quality_history.json (project-specific)
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict


@dataclass
class QualityMetrics:
    """Quality metrics snapshot."""

    timestamp: str  # ISO format timestamp
    response_count: int  # Number of AI responses
    test_pass_rate: float  # Percentage of tests passing (0-100)
    coverage_percentage: float  # Code coverage percentage (0-100)
    total_tests: int  # Total number of tests
    passed_tests: int  # Number of passed tests
    failed_tests: int  # Number of failed tests
    language: Optional[str] = None  # Language being worked on
    framework: Optional[str] = None  # Test framework used


class QualityTracker:
    """
    Track quality metrics across AI conversation sessions.

    Works with ANY language - adapts to whatever the agent is working on.

    Usage:
        tracker = QualityTracker(project_path="/path/to/project")

        # Record a checkpoint
        metrics = QualityMetrics(
            timestamp=datetime.now().isoformat(),
            response_count=5,
            test_pass_rate=95.0,
            coverage_percentage=87.5,
            total_tests=100,
            passed_tests=95,
            failed_tests=5,
            language="python",
            framework="pytest"
        )
        tracker.record(metrics)

        # Check for degradation
        degradation = tracker.check_degradation()
        if degradation["has_degradation"]:
            print("Quality degraded! Recommend context reset.")
    """

    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.history_file = self.project_path / ".codeframe" / "quality_history.json"

    def record(self, metrics: QualityMetrics) -> None:
        """
        Record a quality checkpoint.

        Args:
            metrics: QualityMetrics to record
        """
        history = self.load_history()
        history.append(asdict(metrics))
        self.save_history(history)

    def load_history(self) -> List[Dict]:
        """
        Load quality history from JSON file.

        Returns:
            List of quality checkpoint dictionaries
        """
        if not self.history_file.exists():
            return []

        try:
            with open(self.history_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def save_history(self, history: List[Dict]) -> None:
        """
        Save quality history to JSON file.

        Args:
            history: List of quality checkpoints
        """
        # Ensure directory exists
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.history_file, "w") as f:
            json.dump(history, f, indent=2)

    def check_degradation(self, threshold_percent: float = 10.0) -> Dict:
        """
        Check if quality has degraded from peak.

        Degradation is detected when:
        - Recent metrics < Peak - threshold_percent

        Args:
            threshold_percent: Degradation threshold (default: 10%)

        Returns:
            Dict with has_degradation, issues, recommendations
        """
        history = self.load_history()

        if len(history) < 2:
            return {
                "has_degradation": False,
                "message": "Not enough data (need at least 2 checkpoints)",
            }

        # Find peak quality
        peak = self._find_peak(history)

        # Get recent metrics (last checkpoint or average of last 3)
        if len(history) < 3:
            recent = history[-1]
        else:
            recent = self._calculate_moving_average(history[-3:])

        # Check for degradation
        coverage_drop = peak["coverage_percentage"] - recent["coverage_percentage"]
        pass_rate_drop = peak["test_pass_rate"] - recent["test_pass_rate"]

        has_coverage_degradation = coverage_drop > threshold_percent
        has_pass_rate_degradation = pass_rate_drop > threshold_percent

        if has_coverage_degradation or has_pass_rate_degradation:
            issues = []
            if has_coverage_degradation:
                issues.append(
                    f"Coverage: {recent['coverage_percentage']:.1f}% "
                    f"(peak: {peak['coverage_percentage']:.1f}%, "
                    f"drop: {coverage_drop:.1f}%)"
                )
            if has_pass_rate_degradation:
                issues.append(
                    f"Pass rate: {recent['test_pass_rate']:.1f}% "
                    f"(peak: {peak['test_pass_rate']:.1f}%, "
                    f"drop: {pass_rate_drop:.1f}%)"
                )

            return {
                "has_degradation": True,
                "coverage_drop": coverage_drop,
                "pass_rate_drop": pass_rate_drop,
                "issues": issues,
                "recommendation": "Consider context reset - quality has degraded significantly",
                "peak": peak,
                "recent": recent,
            }

        return {
            "has_degradation": False,
            "message": "Quality stable",
            "peak": peak,
            "recent": recent,
        }

    def get_stats(self) -> Dict:
        """
        Get quality statistics.

        Returns:
            Dict with current, peak, average metrics
        """
        history = self.load_history()

        if not history:
            return {
                "has_data": False,
                "message": "No quality data recorded yet",
            }

        current = history[-1]
        peak = self._find_peak(history)
        average = self._calculate_moving_average(history[-3:] if len(history) >= 3 else history)

        return {
            "has_data": True,
            "total_checkpoints": len(history),
            "current": current,
            "peak": peak,
            "average": average,
            "trend": self._calculate_trend(history),
        }

    def reset(self) -> None:
        """Clear all quality history."""
        self.save_history([])

    def _find_peak(self, history: List[Dict]) -> Dict:
        """
        Find the peak quality checkpoint.

        Peak is defined by highest combined score:
        score = (test_pass_rate + coverage_percentage) / 2

        Args:
            history: List of checkpoints

        Returns:
            Peak checkpoint dictionary
        """

        def score(checkpoint: Dict) -> float:
            return (
                checkpoint.get("test_pass_rate", 0) + checkpoint.get("coverage_percentage", 0)
            ) / 2

        return max(history, key=score)

    def _calculate_moving_average(self, checkpoints: List[Dict]) -> Dict:
        """
        Calculate moving average of metrics.

        Args:
            checkpoints: List of checkpoints to average

        Returns:
            Dict with averaged metrics
        """
        if not checkpoints:
            return {
                "test_pass_rate": 0.0,
                "coverage_percentage": 0.0,
                "total_tests": 0,
            }

        n = len(checkpoints)

        return {
            "test_pass_rate": sum(c.get("test_pass_rate", 0) for c in checkpoints) / n,
            "coverage_percentage": sum(c.get("coverage_percentage", 0) for c in checkpoints) / n,
            "total_tests": int(sum(c.get("total_tests", 0) for c in checkpoints) / n),
            "passed_tests": int(sum(c.get("passed_tests", 0) for c in checkpoints) / n),
            "failed_tests": int(sum(c.get("failed_tests", 0) for c in checkpoints) / n),
        }

    def _calculate_trend(self, history: List[Dict]) -> str:
        """
        Calculate quality trend.

        Args:
            history: List of checkpoints

        Returns:
            "improving", "stable", or "declining"
        """
        if len(history) < 3:
            return "insufficient_data"

        recent_3 = history[-3:]
        scores = [
            (c.get("test_pass_rate", 0) + c.get("coverage_percentage", 0)) / 2 for c in recent_3
        ]

        # Simple trend: compare first and last
        if scores[-1] > scores[0] + 2:
            return "improving"
        elif scores[-1] < scores[0] - 2:
            return "declining"
        else:
            return "stable"

    def should_reset_context(
        self,
        response_count: int,
        max_responses: int = 20,
        check_degradation: bool = True,
    ) -> Dict:
        """
        Determine if context should be reset.

        Reset triggers:
        1. Response count exceeds maximum
        2. Quality degradation detected
        3. Explicit request

        Args:
            response_count: Current response count
            max_responses: Maximum responses before reset (default: 20)
            check_degradation: Whether to check for quality degradation

        Returns:
            Dict with should_reset, reasons
        """
        reasons = []

        # Check response count
        if response_count >= max_responses:
            reasons.append(f"Response count ({response_count}) exceeds maximum ({max_responses})")

        # Check quality degradation
        if check_degradation:
            degradation = self.check_degradation()
            if degradation["has_degradation"]:
                reasons.append(f"Quality degradation detected: {degradation['issues']}")

        return {
            "should_reset": len(reasons) > 0,
            "reasons": reasons,
            "recommendation": ("Context reset recommended" if reasons else "Context can continue"),
        }
