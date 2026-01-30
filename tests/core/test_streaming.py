"""Tests for the streaming module (work follow functionality).

This module tests the file-based streaming infrastructure used by
`cf work follow` to stream real-time execution output.
"""

import pytest
import time
import threading
from pathlib import Path

from codeframe.core.workspace import Workspace


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Workspace:
    """Create a temporary workspace for testing."""
    from codeframe.core.workspace import create_or_load_workspace

    workspace = create_or_load_workspace(tmp_path)
    return workspace


@pytest.fixture
def run_id() -> str:
    """Generate a test run ID."""
    return "test-run-12345678"


class TestRunOutputPath:
    """Tests for run output path generation."""

    def test_get_run_output_path_returns_expected_structure(
        self, temp_workspace: Workspace, run_id: str
    ):
        """Output path should follow .codeframe/runs/<run_id>/output.log pattern."""
        from codeframe.core.streaming import get_run_output_path

        path = get_run_output_path(temp_workspace, run_id)

        assert path.name == "output.log"
        assert path.parent.name == run_id
        assert path.parent.parent.name == "runs"
        assert ".codeframe" in str(path)

    def test_get_run_output_path_is_within_workspace(
        self, temp_workspace: Workspace, run_id: str
    ):
        """Output path should be within the workspace directory."""
        from codeframe.core.streaming import get_run_output_path

        path = get_run_output_path(temp_workspace, run_id)

        assert str(path).startswith(str(temp_workspace.repo_path))


class TestRunOutputLogger:
    """Tests for the RunOutputLogger class."""

    def test_create_logger_creates_directory(
        self, temp_workspace: Workspace, run_id: str
    ):
        """Creating a logger should create the output directory."""
        from codeframe.core.streaming import RunOutputLogger

        logger = RunOutputLogger(temp_workspace, run_id)

        assert logger.log_path.parent.exists()
        logger.close()

    def test_logger_writes_to_file(
        self, temp_workspace: Workspace, run_id: str
    ):
        """Logger should write messages to the log file."""
        from codeframe.core.streaming import RunOutputLogger

        logger = RunOutputLogger(temp_workspace, run_id)
        logger.write("Test message\n")
        logger.close()

        content = logger.log_path.read_text()
        assert "Test message" in content

    def test_logger_flushes_immediately(
        self, temp_workspace: Workspace, run_id: str
    ):
        """Logger should flush after each write for real-time streaming."""
        from codeframe.core.streaming import RunOutputLogger

        logger = RunOutputLogger(temp_workspace, run_id)
        logger.write("First message\n")

        # Read before close - content should be available
        content = logger.log_path.read_text()
        assert "First message" in content
        logger.close()

    def test_logger_handles_context_manager(
        self, temp_workspace: Workspace, run_id: str
    ):
        """Logger should work as context manager."""
        from codeframe.core.streaming import RunOutputLogger, get_run_output_path

        with RunOutputLogger(temp_workspace, run_id) as logger:
            logger.write("Context message\n")

        path = get_run_output_path(temp_workspace, run_id)
        content = path.read_text()
        assert "Context message" in content

    def test_logger_writes_with_timestamp_option(
        self, temp_workspace: Workspace, run_id: str
    ):
        """Logger should optionally include timestamps."""
        from codeframe.core.streaming import RunOutputLogger

        with RunOutputLogger(temp_workspace, run_id) as logger:
            logger.write_timestamped("Timestamped message")

        content = logger.log_path.read_text()
        # Should contain timestamp pattern [HH:MM:SS]
        assert "[" in content and "]" in content
        assert "Timestamped message" in content


class TestTailRunOutput:
    """Tests for tailing run output files."""

    def test_tail_yields_existing_lines(
        self, temp_workspace: Workspace, run_id: str
    ):
        """Tail should yield lines that exist in the file."""
        from codeframe.core.streaming import RunOutputLogger, tail_run_output

        # Create log with content
        with RunOutputLogger(temp_workspace, run_id) as logger:
            logger.write("Line 1\n")
            logger.write("Line 2\n")

        # Tail should yield these lines
        lines = list(tail_run_output(temp_workspace, run_id, max_iterations=1))

        assert len(lines) == 2
        assert "Line 1" in lines[0]
        assert "Line 2" in lines[1]

    def test_tail_with_since_line_skips_old_content(
        self, temp_workspace: Workspace, run_id: str
    ):
        """Tail with since_line should skip already-seen lines."""
        from codeframe.core.streaming import RunOutputLogger, tail_run_output

        # Create log with content
        with RunOutputLogger(temp_workspace, run_id) as logger:
            logger.write("Line 1\n")
            logger.write("Line 2\n")
            logger.write("Line 3\n")

        # Tail from line 2 (0-indexed, so skip first 2)
        lines = list(tail_run_output(temp_workspace, run_id, since_line=2, max_iterations=1))

        assert len(lines) == 1
        assert "Line 3" in lines[0]

    def test_tail_yields_new_lines_from_concurrent_writer(
        self, temp_workspace: Workspace, run_id: str
    ):
        """Tail should yield new lines as they're written by another process."""
        from codeframe.core.streaming import RunOutputLogger, tail_run_output

        # Start with empty log
        logger = RunOutputLogger(temp_workspace, run_id)

        collected_lines = []
        stop_event = threading.Event()

        def tail_collector():
            for line in tail_run_output(
                temp_workspace, run_id, poll_interval=0.1, max_wait=2.0
            ):
                collected_lines.append(line)
                if "Final" in line:
                    stop_event.set()
                    break

        # Start tailing in background
        tail_thread = threading.Thread(target=tail_collector)
        tail_thread.start()

        # Write lines with small delays
        time.sleep(0.2)
        logger.write("First line\n")
        time.sleep(0.2)
        logger.write("Second line\n")
        time.sleep(0.2)
        logger.write("Final line\n")
        logger.close()

        # Wait for tail to finish
        stop_event.wait(timeout=3.0)
        tail_thread.join(timeout=1.0)

        assert len(collected_lines) >= 3
        assert any("First" in line for line in collected_lines)
        assert any("Final" in line for line in collected_lines)

    def test_tail_handles_missing_file_gracefully(
        self, temp_workspace: Workspace
    ):
        """Tail should handle missing file by waiting for it to appear."""
        from codeframe.core.streaming import tail_run_output

        # File doesn't exist yet
        lines = list(tail_run_output(
            temp_workspace,
            "nonexistent-run",
            max_iterations=1,
            max_wait=0.5
        ))

        assert len(lines) == 0  # No lines, but no exception


class TestGetLatestRunLines:
    """Tests for reading buffered output (--tail N functionality)."""

    def test_get_latest_lines_returns_last_n_lines(
        self, temp_workspace: Workspace, run_id: str
    ):
        """Should return the last N lines from the log file."""
        from codeframe.core.streaming import RunOutputLogger, get_latest_lines

        # Create log with 10 lines
        with RunOutputLogger(temp_workspace, run_id) as logger:
            for i in range(10):
                logger.write(f"Line {i}\n")

        # Get last 3 lines
        lines = get_latest_lines(temp_workspace, run_id, count=3)

        assert len(lines) == 3
        assert "Line 7" in lines[0]
        assert "Line 8" in lines[1]
        assert "Line 9" in lines[2]

    def test_get_latest_lines_returns_all_if_fewer_than_n(
        self, temp_workspace: Workspace, run_id: str
    ):
        """Should return all lines if fewer than N exist."""
        from codeframe.core.streaming import RunOutputLogger, get_latest_lines

        # Create log with 2 lines
        with RunOutputLogger(temp_workspace, run_id) as logger:
            logger.write("Line 1\n")
            logger.write("Line 2\n")

        # Ask for 10 lines
        lines = get_latest_lines(temp_workspace, run_id, count=10)

        assert len(lines) == 2
        assert "Line 1" in lines[0]
        assert "Line 2" in lines[1]

    def test_get_latest_lines_returns_empty_for_missing_file(
        self, temp_workspace: Workspace
    ):
        """Should return empty list if file doesn't exist."""
        from codeframe.core.streaming import get_latest_lines

        lines = get_latest_lines(temp_workspace, "nonexistent", count=5)

        assert lines == []

    def test_get_latest_lines_returns_line_count(
        self, temp_workspace: Workspace, run_id: str
    ):
        """Should return the total line count along with lines."""
        from codeframe.core.streaming import RunOutputLogger, get_latest_lines_with_count

        # Create log with 10 lines
        with RunOutputLogger(temp_workspace, run_id) as logger:
            for i in range(10):
                logger.write(f"Line {i}\n")

        lines, total = get_latest_lines_with_count(temp_workspace, run_id, count=3)

        assert len(lines) == 3
        assert total == 10


class TestRunOutputExists:
    """Tests for checking if run output exists."""

    def test_output_exists_returns_false_for_missing_file(
        self, temp_workspace: Workspace
    ):
        """Should return False if output file doesn't exist."""
        from codeframe.core.streaming import run_output_exists

        assert run_output_exists(temp_workspace, "nonexistent") is False

    def test_output_exists_returns_true_for_existing_file(
        self, temp_workspace: Workspace, run_id: str
    ):
        """Should return True if output file exists."""
        from codeframe.core.streaming import RunOutputLogger, run_output_exists

        with RunOutputLogger(temp_workspace, run_id) as logger:
            logger.write("Test\n")

        assert run_output_exists(temp_workspace, run_id) is True
