"""
Tests for QualityTracker (enforcement module) - generic quality tracking.
"""

from datetime import datetime
from codeframe.enforcement import QualityTracker, QualityMetrics


class TestQualityTracker:
    """Test quality tracking across languages."""

    def test_records_quality_metrics(self, tmp_path):
        """Test recording quality checkpoints"""
        tracker = QualityTracker(str(tmp_path))

        metrics = QualityMetrics(
            timestamp=datetime.now().isoformat(),
            response_count=5,
            test_pass_rate=95.0,
            coverage_percentage=87.5,
            total_tests=100,
            passed_tests=95,
            failed_tests=5,
            language="python",
            framework="pytest",
        )

        tracker.record(metrics)

        history = tracker.load_history()
        assert len(history) == 1
        assert history[0]["test_pass_rate"] == 95.0

    def test_detects_degradation(self, tmp_path):
        """Test degradation detection"""
        tracker = QualityTracker(str(tmp_path))

        # Record peak quality
        tracker.record(
            QualityMetrics(
                timestamp=datetime.now().isoformat(),
                response_count=1,
                test_pass_rate=100.0,
                coverage_percentage=90.0,
                total_tests=100,
                passed_tests=100,
                failed_tests=0,
                language="python",
                framework="pytest",
            )
        )

        # Record degraded quality
        tracker.record(
            QualityMetrics(
                timestamp=datetime.now().isoformat(),
                response_count=2,
                test_pass_rate=85.0,  # 15% drop
                coverage_percentage=75.0,  # 15% drop
                total_tests=100,
                passed_tests=85,
                failed_tests=15,
                language="python",
                framework="pytest",
            )
        )

        degradation = tracker.check_degradation(threshold_percent=10.0)
        assert degradation["has_degradation"] is True

    def test_works_with_any_language(self, tmp_path):
        """Test language-agnostic tracking"""
        tracker = QualityTracker(str(tmp_path))

        # Track Go project
        tracker.record(
            QualityMetrics(
                timestamp=datetime.now().isoformat(),
                response_count=1,
                test_pass_rate=100.0,
                coverage_percentage=85.0,
                total_tests=50,
                passed_tests=50,
                failed_tests=0,
                language="go",
                framework="go test",
            )
        )

        # Track JavaScript project
        tracker.record(
            QualityMetrics(
                timestamp=datetime.now().isoformat(),
                response_count=2,
                test_pass_rate=95.0,
                coverage_percentage=88.0,
                total_tests=75,
                passed_tests=71,
                failed_tests=4,
                language="javascript",
                framework="jest",
            )
        )

        history = tracker.load_history()
        assert len(history) == 2
        assert history[0]["language"] == "go"
        assert history[1]["language"] == "javascript"

    def test_get_stats(self, tmp_path):
        """Test statistics calculation"""
        tracker = QualityTracker(str(tmp_path))

        tracker.record(
            QualityMetrics(
                timestamp=datetime.now().isoformat(),
                response_count=1,
                test_pass_rate=100.0,
                coverage_percentage=90.0,
                total_tests=100,
                passed_tests=100,
                failed_tests=0,
                language="python",
            )
        )

        stats = tracker.get_stats()
        assert stats["has_data"] is True
        assert stats["total_checkpoints"] == 1
        assert stats["current"]["test_pass_rate"] == 100.0

    def test_reset_clears_history(self, tmp_path):
        """Test reset functionality"""
        tracker = QualityTracker(str(tmp_path))

        tracker.record(
            QualityMetrics(
                timestamp=datetime.now().isoformat(),
                response_count=1,
                test_pass_rate=100.0,
                coverage_percentage=90.0,
                total_tests=100,
                passed_tests=100,
                failed_tests=0,
                language="python",
            )
        )

        tracker.reset()

        history = tracker.load_history()
        assert len(history) == 0
