"""Port validation and availability checking utilities."""

import socket
from typing import Tuple


def is_port_available(port: int, host: str = "0.0.0.0") -> bool:
    """
    Check if a port is available for binding.

    Args:
        port: Port number to check
        host: Host address to bind to (default: 0.0.0.0)

    Returns:
        True if port is available, False otherwise
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
            return True
    except OSError:
        return False


def check_port_availability(port: int, host: str = "0.0.0.0") -> Tuple[bool, str]:
    """
    Check if a port is available and return a helpful message if not.

    Args:
        port: Port number to check
        host: Host address to bind to (default: 0.0.0.0)

    Returns:
        Tuple of (available: bool, message: str)
        If available, message is empty string.
        If not available, message contains helpful error text.

    Note:
        There is a small time window (~100ms) between this check and actual server
        startup where another process could bind to the port (TOCTOU race condition).
        This is inherent to pre-flight port checking. If this rare case occurs, the
        server will fail to start and uvicorn will display the appropriate error.
    """
    if port < 1024:
        return (
            False,
            f"Port {port} requires elevated privileges. Use a port ≥1024 (try --port {8080})",
        )

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
            return (True, "")
    except OSError as e:
        # Common error codes for "address already in use"
        # errno 48 (macOS), 98 (Linux), 10048 (Windows)
        if e.errno in (48, 98, 10048):
            suggested_port = port + 1
            return (
                False,
                f"Port {port} is already in use. Try --port {suggested_port}",
            )
        else:
            return (False, f"Cannot bind to port {port}: {e}")


def validate_port_range(port: int) -> Tuple[bool, str]:
    """
    Validate that port is in acceptable range.

    Args:
        port: Port number to validate

    Returns:
        Tuple of (valid: bool, message: str)
        If valid, message is empty string.
        If invalid, message contains error text.
    """
    if port < 1024:
        return (
            False,
            f"Port {port} requires elevated privileges. Use a port ≥1024",
        )
    if port > 65535:
        return (False, f"Port {port} is out of range. Maximum port is 65535")

    return (True, "")
