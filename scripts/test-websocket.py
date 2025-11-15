#!/usr/bin/env python3
"""
WebSocket Connection Test Script

Tests WebSocket connectivity both directly to backend and through nginx proxy.
Use this to verify WebSocket configuration after deployment.

Usage:
    python scripts/test-websocket.py [--proxy-url WS_URL] [--direct-url WS_URL]

Examples:
    # Test both direct and proxy connections (default)
    python scripts/test-websocket.py

    # Test only proxy connection
    python scripts/test-websocket.py --proxy-url ws://api.codeframe.home.frankbria.net/ws

    # Test custom URLs
    python scripts/test-websocket.py \\
        --proxy-url ws://api.example.com/ws \\
        --direct-url ws://localhost:14200/ws
"""

import argparse
import json
import sys
import time
from typing import Optional

try:
    import websocket
except ImportError:
    print("❌ ERROR: websocket-client not installed")
    print("   Install with: pip install websocket-client")
    sys.exit(1)


class Colors:
    """ANSI color codes for terminal output."""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def print_header(message: str):
    """Print a formatted header."""
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'=' * 70}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{message:^70}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 70}{Colors.ENDC}\n")


def print_success(message: str):
    """Print a success message."""
    print(f"{Colors.OKGREEN}✅ {message}{Colors.ENDC}")


def print_error(message: str):
    """Print an error message."""
    print(f"{Colors.FAIL}❌ {message}{Colors.ENDC}")


def print_warning(message: str):
    """Print a warning message."""
    print(f"{Colors.WARNING}⚠️  {message}{Colors.ENDC}")


def print_info(message: str):
    """Print an info message."""
    print(f"{Colors.OKCYAN}ℹ️  {message}{Colors.ENDC}")


def test_websocket_connection(ws_url: str, connection_name: str, timeout: int = 10) -> bool:
    """
    Test WebSocket connection to a given URL.

    Args:
        ws_url: WebSocket URL to connect to
        connection_name: Human-readable name for this connection
        timeout: Connection timeout in seconds

    Returns:
        True if test passed, False otherwise
    """
    print(f"\n{Colors.BOLD}Testing {connection_name}:{Colors.ENDC}")
    print(f"  URL: {ws_url}")

    # Step 1: Attempt connection
    print(f"\n  {Colors.OKCYAN}[1/4] Attempting connection...{Colors.ENDC}")
    try:
        ws = websocket.create_connection(ws_url, timeout=timeout)
    except Exception as e:
        print_error(f"Connection failed: {str(e)}")
        print_info("This usually means:")
        print_info("  • Backend is not running")
        print_info("  • Nginx is not forwarding WebSocket upgrade headers")
        print_info("  • Firewall is blocking the connection")
        return False

    if not ws.connected:
        print_error("Connection established but not in connected state")
        return False

    print_success("Connected successfully")

    # Step 2: Send ping message
    print(f"\n  {Colors.OKCYAN}[2/4] Sending ping message...{Colors.ENDC}")
    ping_msg = json.dumps({"type": "ping"})
    try:
        ws.send(ping_msg)
        print_success(f"Sent: {ping_msg}")
    except Exception as e:
        print_error(f"Failed to send message: {str(e)}")
        ws.close()
        return False

    # Step 3: Receive pong response
    print(f"\n  {Colors.OKCYAN}[3/4] Waiting for pong response...{Colors.ENDC}")
    try:
        response = ws.recv()
        print_success(f"Received: {response}")

        # Validate response
        try:
            response_data = json.loads(response)
            if response_data.get("type") == "pong":
                print_success("Pong response validated")
            else:
                print_warning(f"Unexpected response type: {response_data.get('type')}")
        except json.JSONDecodeError:
            print_warning("Response is not valid JSON")

    except Exception as e:
        print_error(f"Failed to receive response: {str(e)}")
        ws.close()
        return False

    # Step 4: Clean disconnect
    print(f"\n  {Colors.OKCYAN}[4/4] Closing connection...{Colors.ENDC}")
    try:
        ws.close()
        print_success("Disconnected cleanly")
    except Exception as e:
        print_warning(f"Disconnect warning: {str(e)}")

    return True


def test_connection_stability(ws_url: str, connection_name: str, duration: int = 60) -> bool:
    """
    Test WebSocket connection stability over time.

    Args:
        ws_url: WebSocket URL to connect to
        connection_name: Human-readable name for this connection
        duration: How long to keep connection open (seconds)

    Returns:
        True if connection stayed alive, False otherwise
    """
    print(f"\n{Colors.BOLD}Testing {connection_name} Stability:{Colors.ENDC}")
    print(f"  URL: {ws_url}")
    print(f"  Duration: {duration}s")

    try:
        ws = websocket.create_connection(ws_url, timeout=10)
    except Exception as e:
        print_error(f"Connection failed: {str(e)}")
        return False

    print_success("Connected")

    # Keep connection alive and send periodic pings
    start_time = time.time()
    ping_interval = 10  # Send ping every 10 seconds

    try:
        while time.time() - start_time < duration:
            elapsed = int(time.time() - start_time)
            print(f"  {elapsed}s elapsed... ", end="", flush=True)

            # Send ping
            ws.send(json.dumps({"type": "ping"}))

            # Wait for pong
            response = ws.recv()
            print(f"✓ (pong received)")

            # Wait before next ping
            if elapsed + ping_interval < duration:
                time.sleep(ping_interval)
            else:
                break

        ws.close()
        print_success(f"Connection remained stable for {duration}s")
        return True

    except Exception as e:
        print_error(f"Connection died after {int(time.time() - start_time)}s: {str(e)}")
        try:
            ws.close()
        except:
            pass
        return False


def main():
    """Main test orchestrator."""
    parser = argparse.ArgumentParser(
        description="Test WebSocket connectivity for CodeFRAME deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test both direct and proxy connections (default)
  python scripts/test-websocket.py

  # Test only proxy connection
  python scripts/test-websocket.py --proxy-url ws://api.codeframe.home.frankbria.net/ws

  # Test custom URLs
  python scripts/test-websocket.py \\
      --proxy-url ws://api.example.com/ws \\
      --direct-url ws://localhost:14200/ws

  # Skip stability test (faster)
  python scripts/test-websocket.py --no-stability
        """,
    )

    parser.add_argument(
        "--proxy-url",
        default="ws://api.codeframe.home.frankbria.net/ws",
        help="WebSocket URL through proxy (default: ws://api.codeframe.home.frankbria.net/ws)",
    )

    parser.add_argument(
        "--direct-url",
        default="ws://localhost:14200/ws",
        help="WebSocket URL direct to backend (default: ws://localhost:14200/ws)",
    )

    parser.add_argument(
        "--no-stability",
        action="store_true",
        help="Skip stability test (faster, only tests connection/ping/pong)",
    )

    parser.add_argument(
        "--stability-duration",
        type=int,
        default=60,
        help="How long to test stability in seconds (default: 60)",
    )

    args = parser.parse_args()

    print_header("CodeFRAME WebSocket Connection Test")

    # Test results tracking
    results = {}

    # Test 1: Direct backend connection (control test)
    print_header("Test 1: Direct Backend Connection")
    print_info("This tests the backend WebSocket endpoint without nginx proxy")
    print_info("This should ALWAYS work if the backend is running")

    results["direct"] = test_websocket_connection(args.direct_url, "Direct Backend")

    # Test 2: Proxy connection (the actual deployment)
    print_header("Test 2: Nginx Proxy Connection")
    print_info("This tests the WebSocket through nginx reverse proxy")
    print_info("This requires proper nginx WebSocket configuration")

    results["proxy"] = test_websocket_connection(args.proxy_url, "Nginx Proxy")

    # Test 3: Connection stability (optional)
    if not args.no_stability and results["proxy"]:
        print_header("Test 3: Connection Stability")
        print_info("This tests if WebSocket stays alive over time")
        print_info("Ensures nginx timeout configuration is correct")

        results["stability"] = test_connection_stability(
            args.proxy_url, "Nginx Proxy", duration=args.stability_duration
        )
    elif args.no_stability:
        results["stability"] = None  # Skipped
    else:
        results["stability"] = False  # Proxy failed, can't test stability

    # Print summary
    print_header("Test Summary")

    # Direct connection
    if results["direct"]:
        print_success("Direct Backend Connection: PASSED")
    else:
        print_error("Direct Backend Connection: FAILED")
        print_info("  → Backend may not be running")
        print_info("  → Check: pm2 list | grep backend")
        print_info("  → Start: pm2 restart codeframe-staging-backend")

    # Proxy connection
    if results["proxy"]:
        print_success("Nginx Proxy Connection: PASSED")
    else:
        print_error("Nginx Proxy Connection: FAILED")
        if results["direct"]:
            print_info("  → Backend works but proxy doesn't")
            print_info("  → Nginx WebSocket configuration missing")
            print_info("  → See: docs/nginx-websocket-config.md")
        else:
            print_info("  → Backend is not running (see above)")

    # Stability
    if results["stability"] is None:
        print_warning("Connection Stability: SKIPPED")
    elif results["stability"]:
        print_success("Connection Stability: PASSED")
    elif results["proxy"]:
        print_error("Connection Stability: FAILED")
        print_info("  → Connection closes prematurely")
        print_info("  → Nginx timeout too short")
        print_info("  → Add: proxy_read_timeout 86400s;")

    # Exit code
    print()
    if results["proxy"]:
        print_success("ALL CRITICAL TESTS PASSED ✓")
        print_info("WebSocket is working correctly through nginx proxy")
        sys.exit(0)
    else:
        print_error("CRITICAL TESTS FAILED ✗")
        print_info("WebSocket is not working correctly")
        print_info("See error messages above for troubleshooting steps")
        sys.exit(1)


if __name__ == "__main__":
    main()
