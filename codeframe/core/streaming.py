"""Streaming infrastructure for real-time execution output.

This module provides:
1. File-based streaming for `cf work follow`:
   - RunOutputLogger: Writes agent output to a log file
   - tail_run_output: Tails a log file for real-time streaming
   - get_latest_lines: Reads buffered output (for --tail N)

2. Event-based streaming for SSE/WebSocket:
   - EventPublisher: Async event distribution with subscription support

Output files are stored at: .codeframe/runs/<run_id>/output.log

This module is headless - no FastAPI or HTTP dependencies.
"""

import asyncio
import logging
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    AsyncIterator,
    Dict,
    Iterator,
    List,
    Optional,
    TYPE_CHECKING,
)

from codeframe.core.workspace import Workspace

if TYPE_CHECKING:
    from codeframe.core.models import ExecutionEvent

logger = logging.getLogger(__name__)

# Configuration via environment variables
SSE_TIMEOUT_SECONDS = int(os.getenv("SSE_TIMEOUT_SECONDS", "30"))
SSE_MAX_QUEUE_SIZE = int(os.getenv("SSE_MAX_QUEUE_SIZE", "1000"))
SSE_OUTPUT_MAX_CHARS = int(os.getenv("SSE_OUTPUT_MAX_CHARS", "2000"))


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


# =============================================================================
# Event-based streaming for SSE/WebSocket
# =============================================================================


class _Subscription:
    """Internal subscription handle for tracking async iterators."""

    # Sentinel value to signal end of stream
    END_OF_STREAM = object()

    def __init__(self, task_id: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self.task_id = task_id
        self.queue = queue
        self.loop = loop  # Event loop for thread-safe operations
        self.active = True


class EventPublisher:
    """Async event publisher for real-time streaming.

    Provides publish/subscribe functionality for ExecutionEvents,
    used by SSE and WebSocket endpoints.

    Features:
    - Multiple subscribers per task
    - Event isolation by task_id
    - Graceful stream closure on task completion
    - Thread-safe for concurrent access
    - Sync publishing support for non-async code (e.g., agent)

    Usage:
        publisher = EventPublisher()

        # Subscribe (in SSE/WebSocket handler)
        async for event in publisher.subscribe(task_id):
            yield f"data: {event.model_dump_json()}\\n\\n"

        # Publish async (in async code)
        await publisher.publish(task_id, ProgressEvent(...))

        # Publish sync (in sync code like agent)
        publisher.publish_sync(task_id, ProgressEvent(...))

        # Signal completion (closes all subscribers)
        await publisher.complete_task(task_id)

    Configuration (via environment variables):
        SSE_TIMEOUT_SECONDS: Timeout for waiting on events (default: 30)
        SSE_MAX_QUEUE_SIZE: Max events per subscriber queue (default: 1000)
    """

    def __init__(self, timeout: Optional[float] = None, max_queue_size: Optional[int] = None):
        """Initialize the event publisher.

        Args:
            timeout: Timeout for waiting on events (default: SSE_TIMEOUT_SECONDS env var)
            max_queue_size: Max events per queue (default: SSE_MAX_QUEUE_SIZE env var)
        """
        # Map task_id -> list of subscriber queues
        self._subscribers: Dict[str, List[_Subscription]] = defaultdict(list)
        # Lock for thread-safe subscriber management
        self._lock = asyncio.Lock()
        # Thread lock for sync publishing
        self._thread_lock = threading.Lock()
        # Configuration
        self._timeout = timeout if timeout is not None else SSE_TIMEOUT_SECONDS
        self._max_queue_size = max_queue_size if max_queue_size is not None else SSE_MAX_QUEUE_SIZE

    async def subscribe(self, task_id: str) -> AsyncIterator["ExecutionEvent"]:
        """Subscribe to events for a task.

        Creates an async iterator that yields events as they are published.
        The iterator exits when the task completes (receives END_OF_STREAM sentinel).

        Args:
            task_id: Task ID to subscribe to

        Yields:
            ExecutionEvent objects as they are published
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
        loop = asyncio.get_running_loop()
        subscription = _Subscription(task_id, queue, loop)

        async with self._lock:
            self._subscribers[task_id].append(subscription)

        try:
            while True:
                try:
                    # Wait for events with configurable timeout
                    item = await asyncio.wait_for(queue.get(), timeout=self._timeout)

                    # Check for end-of-stream sentinel
                    if item is _Subscription.END_OF_STREAM:
                        break

                    yield item
                except asyncio.TimeoutError:
                    # Check if we should exit (task completed but no sentinel received)
                    if not subscription.active:
                        break
                    # Log if queue is getting full (backpressure warning)
                    if queue.qsize() > self._max_queue_size * 0.8:
                        logger.warning(
                            f"Event queue for task {task_id} is {queue.qsize()}/{self._max_queue_size} full"
                        )
                    # Otherwise continue waiting
                    continue
        finally:
            # Clean up subscription
            async with self._lock:
                if subscription in self._subscribers[task_id]:
                    self._subscribers[task_id].remove(subscription)
                # Clean up empty task entries
                if not self._subscribers[task_id]:
                    del self._subscribers[task_id]

    async def publish(self, task_id: str, event: "ExecutionEvent") -> None:
        """Publish an event to all subscribers of a task.

        If there are no subscribers, the event is silently dropped.
        If a subscriber's queue is full, the event is dropped for that subscriber
        with a warning logged.

        Args:
            task_id: Task ID to publish to
            event: Event to publish
        """
        async with self._lock:
            subscribers = self._subscribers.get(task_id, [])
            for subscription in subscribers:
                if subscription.active:
                    try:
                        subscription.queue.put_nowait(event)
                    except asyncio.QueueFull:
                        logger.warning(
                            f"Event queue full for task {task_id}, dropping event: {event.event_type}"
                        )

    def publish_sync(self, task_id: str, event: "ExecutionEvent") -> None:
        """Publish an event synchronously (for use from non-async code).

        This method is designed for use from the synchronous agent code.
        Uses run_coroutine_threadsafe to delegate to the async publish() method,
        ensuring single lock discipline (only _lock is used for subscriber access).

        If there are no subscribers, the event is silently dropped.

        Args:
            task_id: Task ID to publish to
            event: Event to publish
        """
        # Get any active subscription's event loop to run the coroutine
        with self._thread_lock:
            subscribers = self._subscribers.get(task_id, [])
            if not subscribers:
                return  # No subscribers, nothing to do
            # Use the first active subscriber's loop
            loop = None
            for subscription in subscribers:
                if subscription.active:
                    loop = subscription.loop
                    break
            if loop is None:
                return  # No active subscribers

        # Delegate to async publish() using run_coroutine_threadsafe
        # This ensures we use the same _lock for all subscriber access
        try:
            # Fire and forget - don't wait for the result to avoid blocking sync caller
            asyncio.run_coroutine_threadsafe(self.publish(task_id, event), loop)
        except RuntimeError:
            # Event loop may be closed
            logger.warning(f"Event loop closed for task {task_id}")

    def complete_task_sync(self, task_id: str) -> None:
        """Signal task completion synchronously (for use from non-async code).

        Uses run_coroutine_threadsafe to delegate to the async complete_task() method,
        ensuring single lock discipline (only _lock is used for subscriber access).

        Args:
            task_id: Task ID that completed
        """
        # Get any active subscription's event loop to run the coroutine
        with self._thread_lock:
            subscribers = self._subscribers.get(task_id, [])
            if not subscribers:
                return  # No subscribers, nothing to do
            # Use the first subscriber's loop (even if inactive, loop should still work)
            loop = subscribers[0].loop

        # Delegate to async complete_task() using run_coroutine_threadsafe
        # This ensures we use the same _lock for all subscriber access
        try:
            # Fire and forget - don't wait for the result
            asyncio.run_coroutine_threadsafe(self.complete_task(task_id), loop)
        except RuntimeError:
            # Event loop may be closed
            logger.warning(f"Event loop closed for task {task_id}")

    async def complete_task(self, task_id: str) -> None:
        """Signal that a task is complete, closing all subscriber streams.

        This should be called when task execution finishes (success or failure)
        to allow SSE/WebSocket connections to close gracefully.

        All queued events will be delivered before the stream closes.

        Args:
            task_id: Task ID that completed
        """
        async with self._lock:
            subscribers = self._subscribers.get(task_id, [])
            for subscription in subscribers:
                subscription.active = False
                # Send end-of-stream sentinel so subscribers exit gracefully
                # after processing all queued events
                await subscription.queue.put(_Subscription.END_OF_STREAM)

    async def unsubscribe(
        self, task_id: str, iterator: AsyncIterator["ExecutionEvent"]
    ) -> None:
        """Manually unsubscribe an iterator.

        Typically not needed as subscriptions clean up automatically,
        but can be used for explicit cleanup.

        Args:
            task_id: Task ID of the subscription
            iterator: The async iterator returned by subscribe()
        """
        # The iterator cleanup happens in the finally block of subscribe()
        # This method is provided for explicit control if needed
        async with self._lock:
            for subscription in self._subscribers.get(task_id, []):
                subscription.active = False

    def subscriber_count(self, task_id: str) -> int:
        """Get the number of active subscribers for a task.

        Args:
            task_id: Task ID to check

        Returns:
            Number of active subscribers
        """
        # Note: This is a sync method for convenience, but accesses
        # shared state. For production, consider making this async.
        subscribers = self._subscribers.get(task_id, [])
        return sum(1 for s in subscribers if s.active)
