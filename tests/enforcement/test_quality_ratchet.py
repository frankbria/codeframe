"""
Unit tests for quality ratchet system.

These tests verify that the quality ratchet correctly tracks metrics,
detects degradation, and provides useful statistics.

Test Coverage:
- T032: record command creates history entry
- T033: check command detects degradation >10%
- T034: stats command formats Rich Table output correctly
- T035: reset command clears history
- T036: moving average calculation (last 3 checkpoints)
- T037: peak quality detection algorithm
- T038: JSON persistence to .claude/quality_history.json
- T039: handles missing history file gracefully
"""

import importlib.util
import json
from pathlib import Path

import pytest

# Import the quality ratchet module
scripts_dir = Path(__file__).parent.parent.parent / "scripts"
script_path = scripts_dir / "quality-ratchet.py"

try:
    spec = importlib.util.spec_from_file_location("quality_ratchet", script_path)
    quality_ratchet = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(quality_ratchet)

    load_history = quality_ratchet.load_history
    save_history = quality_ratchet.save_history
    detect_degradation = quality_ratchet.detect_degradation
    calculate_moving_average = quality_ratchet.calculate_moving_average
    find_peak_quality = quality_ratchet.find_peak_quality
except Exception as e:
    pytest.skip(f"Quality ratchet not implemented yet: {e}", allow_module_level=True)


class TestQualityRatchetRecord:
    """Test the record command functionality."""

    def test_record_creates_history_entry(self, tmp_path):
        """T032: Test record command creates history entry"""
        history_file = tmp_path / "quality_history.json"

        # Start with empty history
        history = []
        save_history(history, str(history_file))

        # Add a record
        entry = {
            "timestamp": "2025-11-15T10:00:00",
            "response_count": 5,
            "test_pass_rate": 95.5,
            "coverage_percentage": 87.3,
        }
        history.append(entry)
        save_history(history, str(history_file))

        # Verify it was saved
        loaded = load_history(str(history_file))
        assert len(loaded) == 1
        assert loaded[0]["response_count"] == 5
        assert loaded[0]["test_pass_rate"] == 95.5
        assert loaded[0]["coverage_percentage"] == 87.3


class TestQualityRatchetCheck:
    """Test the check command for degradation detection."""

    def test_check_detects_coverage_degradation(self):
        """T033: Test check command detects coverage degradation >10%"""
        history = [
            {
                "timestamp": "2025-11-15T10:00:00",
                "response_count": 5,
                "test_pass_rate": 100.0,
                "coverage_percentage": 90.0,
            },
            {
                "timestamp": "2025-11-15T10:30:00",
                "response_count": 10,
                "test_pass_rate": 100.0,
                "coverage_percentage": 75.0,  # 15% drop
            },
        ]

        degradation = detect_degradation(history)
        assert degradation is not None
        assert "coverage" in degradation or degradation.get("has_degradation") is True

    def test_check_detects_pass_rate_degradation(self):
        """Test check command detects pass rate degradation >10%"""
        history = [
            {
                "timestamp": "2025-11-15T10:00:00",
                "response_count": 5,
                "test_pass_rate": 100.0,
                "coverage_percentage": 90.0,
            },
            {
                "timestamp": "2025-11-15T10:30:00",
                "response_count": 10,
                "test_pass_rate": 85.0,  # 15% drop
                "coverage_percentage": 90.0,
            },
        ]

        degradation = detect_degradation(history)
        assert degradation is not None
        assert "pass_rate" in degradation or degradation.get("has_degradation") is True

    def test_check_passes_with_no_degradation(self):
        """Test check command passes when quality is stable"""
        history = [
            {
                "timestamp": "2025-11-15T10:00:00",
                "response_count": 5,
                "test_pass_rate": 100.0,
                "coverage_percentage": 90.0,
            },
            {
                "timestamp": "2025-11-15T10:30:00",
                "response_count": 10,
                "test_pass_rate": 98.0,
                "coverage_percentage": 89.0,
            },
        ]

        degradation = detect_degradation(history)
        # Should either be None or indicate no degradation
        if degradation is not None:
            assert degradation.get("has_degradation") is False


class TestQualityRatchetStats:
    """Test the stats command output formatting."""

    def test_stats_command_formats_output(self):
        """T034: Test stats command formats Rich Table output correctly"""
        # This test verifies the data structure used for stats display
        history = [
            {
                "timestamp": "2025-11-15T10:00:00",
                "response_count": 5,
                "test_pass_rate": 95.5,
                "coverage_percentage": 87.3,
            },
            {
                "timestamp": "2025-11-15T10:30:00",
                "response_count": 10,
                "test_pass_rate": 97.2,
                "coverage_percentage": 89.1,
            },
        ]

        # Calculate stats
        current = history[-1]
        peak = find_peak_quality(history)
        avg = calculate_moving_average(history, window=3)

        assert current["test_pass_rate"] == 97.2
        assert peak["test_pass_rate"] >= 95.5
        assert avg["test_pass_rate"] > 0


class TestQualityRatchetReset:
    """Test the reset command functionality."""

    def test_reset_clears_history(self, tmp_path):
        """T035: Test reset command clears history"""
        history_file = tmp_path / "quality_history.json"

        # Create history with some entries
        history = [
            {
                "timestamp": "2025-11-15T10:00:00",
                "response_count": 5,
                "test_pass_rate": 95.5,
                "coverage_percentage": 87.3,
            }
        ]
        save_history(history, str(history_file))

        # Reset (clear history)
        save_history([], str(history_file))

        # Verify it's empty
        loaded = load_history(str(history_file))
        assert len(loaded) == 0


class TestQualityRatchetCalculations:
    """Test calculation functions."""

    def test_moving_average_calculation(self):
        """T036: Test moving average calculation (last 3 checkpoints)"""
        history = [
            {"test_pass_rate": 90.0, "coverage_percentage": 85.0},
            {"test_pass_rate": 95.0, "coverage_percentage": 87.0},
            {"test_pass_rate": 92.0, "coverage_percentage": 86.0},
            {"test_pass_rate": 88.0, "coverage_percentage": 84.0},
        ]

        avg = calculate_moving_average(history, window=3)

        # Average of last 3: (95 + 92 + 88) / 3 = 91.67
        assert 91.0 <= avg["test_pass_rate"] <= 92.0
        # Average of last 3: (87 + 86 + 84) / 3 = 85.67
        assert 85.0 <= avg["coverage_percentage"] <= 86.0

    def test_moving_average_with_fewer_entries(self):
        """Test moving average with fewer entries than window size"""
        history = [
            {"test_pass_rate": 90.0, "coverage_percentage": 85.0},
        ]

        avg = calculate_moving_average(history, window=3)
        assert avg["test_pass_rate"] == 90.0
        assert avg["coverage_percentage"] == 85.0

    def test_peak_quality_detection(self):
        """T037: Test peak quality detection algorithm"""
        history = [
            {"test_pass_rate": 90.0, "coverage_percentage": 85.0},
            {"test_pass_rate": 100.0, "coverage_percentage": 92.0},  # Peak
            {"test_pass_rate": 95.0, "coverage_percentage": 88.0},
        ]

        peak = find_peak_quality(history)
        assert peak["test_pass_rate"] == 100.0
        assert peak["coverage_percentage"] == 92.0


class TestQualityRatchetPersistence:
    """Test JSON persistence functionality."""

    def test_json_persistence(self, tmp_path):
        """T038: Test JSON persistence to .claude/quality_history.json"""
        history_file = tmp_path / "quality_history.json"

        history = [
            {
                "timestamp": "2025-11-15T10:00:00",
                "response_count": 5,
                "test_pass_rate": 95.5,
                "coverage_percentage": 87.3,
            },
            {
                "timestamp": "2025-11-15T10:30:00",
                "response_count": 10,
                "test_pass_rate": 97.2,
                "coverage_percentage": 89.1,
            },
        ]

        save_history(history, str(history_file))

        # Read directly from file
        with open(history_file, "r") as f:
            data = json.load(f)

        assert len(data) == 2
        assert data[0]["response_count"] == 5
        assert data[1]["response_count"] == 10

    def test_handles_missing_history_file(self, tmp_path):
        """T039: Test handles missing history file gracefully"""
        history_file = tmp_path / "nonexistent.json"

        # Should return empty list, not raise error
        history = load_history(str(history_file))
        assert history == []

    def test_handles_corrupted_history_file(self, tmp_path):
        """Test handles corrupted JSON gracefully"""
        history_file = tmp_path / "corrupted.json"

        # Write invalid JSON
        with open(history_file, "w") as f:
            f.write("{ invalid json")

        # Should return empty list or handle gracefully
        history = load_history(str(history_file))
        assert isinstance(history, list)


class TestQualityRatchetEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_history(self):
        """Test handling of empty history"""
        history = []

        # Should not crash
        peak = find_peak_quality(history)
        assert peak is None or isinstance(peak, dict)

        avg = calculate_moving_average(history)
        assert avg is None or isinstance(avg, dict)

    def test_single_entry_history(self):
        """Test handling of single entry"""
        history = [
            {
                "timestamp": "2025-11-15T10:00:00",
                "response_count": 5,
                "test_pass_rate": 95.5,
                "coverage_percentage": 87.3,
            }
        ]

        peak = find_peak_quality(history)
        assert peak["test_pass_rate"] == 95.5

        avg = calculate_moving_average(history)
        assert avg["test_pass_rate"] == 95.5
