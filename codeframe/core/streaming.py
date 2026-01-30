"""Streaming infrastructure for real-time execution output.

This module provides file-based streaming for `cf work follow`:
- RunOutputLogger: Writes agent output to a log file
- tail_run_output: Tails a log file for real-time streaming
- get_latest_lines: Reads buffered output (for --tail N)

Output files are stored at: .codeframe/runs/<run_id>/output.log

This module is headless - no FastAPI or HTTP dependencies.
"""

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from codeframe.core.workspace import Workspace


def get_run_output_path(workspace: Workspace, run_id: str) -> Path:
    """Get the path for a run's output log file.

    Args:
        workspace: Target workspace
        run_id: Run identifier

    Returns:
        Path to the output log file
    """
    return workspace.repo_path / ".codeframe" / "runs" / run_id / "output.log"


def run_output_exists(workspace: Workspace, run_id: str) -> bool:
    """Check if a run's output log exists.

    Args:
        workspace: Target workspace
        run_id: Run identifier

    Returns:
        True if the output file exists
    """
    return get_run_output_path(workspace, run_id).exists()


class RunOutputLogger:
    """Logger that writes agent output to a file for streaming.

    This class is used by the Agent to write verbose output to a log file
    that can be tailed by `cf work follow`.

    Usage:
        with RunOutputLogger(workspace, run_id) as logger:
            logger.write("Processing step 1...")
            logger.write_timestamped("Step completed")

    The log file is flushed after each write to enable real-time streaming.
    """

    def __init__(self, workspace: Workspace, run_id: str):
        """Initialize the logger.

        Args:
            workspace: Target workspace
            run_id: Run identifier
        """
        self.workspace = workspace
        self.run_id = run_id
        self.log_path = get_run_output_path(workspace, run_id)
        self._file = None  # Initialize before potential mkdir/open failure

        # Ensure directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Open file in append mode
        self._file = open(self.log_path, "a", encoding="utf-8")

    def write(self, message: str) -> None:
        """Write a message to the log file.

        The file is flushed after each write to enable real-time streaming.

        Args:
            message: Message to write (should include newline if desired)
        """
        self._file.write(message)
        self._file.flush()

    def write_timestamped(self, message: str) -> None:
        """Write a message with a timestamp prefix.

        Format: [HH:MM:SS] message

        Args:
            message: Message to write
        """
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.write(f"[{timestamp}] {message}\n")

    def close(self) -> None:
        """Close the log file."""
        if hasattr(self, "_file") and self._file and not self._file.closed:
            self._file.close()

    def __enter__(self) -> "RunOutputLogger":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - close the file."""
        self.close()


def get_latest_lines(workspace: Workspace, run_id: str, count: int) -> list[str]:
    """Get the last N lines from a run's output log.

    Used by `cf work follow --tail N` to show buffered output.

    Args:
        workspace: Target workspace
        run_id: Run identifier
        count: Number of lines to return

    Returns:
        List of the last N lines (or fewer if file has less)
    """
    lines, _ = get_latest_lines_with_count(workspace, run_id, count)
    return lines


def get_latest_lines_with_count(
    workspace: Workspace, run_id: str, count: int
) -> tuple[list[str], int]:
    """Get the last N lines and total line count from a run's output log.

    Args:
        workspace: Target workspace
        run_id: Run identifier
        count: Number of lines to return

    Returns:
        Tuple of (last N lines, total line count)
    """
    log_path = get_run_output_path(workspace, run_id)

    if not log_path.exists():
        return [], 0

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        total = len(all_lines)

        if count >= total:
            return all_lines, total

        return all_lines[-count:], total

    except Exception:
        return [], 0


def tail_run_output(
    workspace: Workspace,
    run_id: str,
    since_line: int = 0,
    poll_interval: float = 0.5,
    max_iterations: Optional[int] = None,
    max_wait: Optional[float] = None,
) -> Iterator[str]:
    """Tail a run's output log file, yielding new lines.

    This generator polls the log file and yields new lines as they appear.
    It's designed to be used with `cf work follow` for real-time streaming.

    Args:
        workspace: Target workspace
        run_id: Run identifier
        since_line: Start after this line number (0-based)
        poll_interval: How often to check for new lines (seconds)
        max_iterations: Stop after this many poll iterations (for testing)
        max_wait: Maximum total wait time in seconds (for testing)

    Yields:
        Lines from the log file as they appear
    """
    log_path = get_run_output_path(workspace, run_id)
    current_line = since_line
    iterations = 0
    start_time = time.time()

    while True:
        # Check termination conditions
        if max_iterations is not None and iterations >= max_iterations:
            break

        if max_wait is not None and (time.time() - start_time) >= max_wait:
            break

        # Check if file exists
        if not log_path.exists():
            time.sleep(poll_interval)
            iterations += 1
            continue

        try:
            with open(log_path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()

            # Yield new lines
            while current_line < len(all_lines):
                yield all_lines[current_line]
                current_line += 1

        except Exception:
            pass  # File might be temporarily unavailable

        time.sleep(poll_interval)
        iterations += 1
