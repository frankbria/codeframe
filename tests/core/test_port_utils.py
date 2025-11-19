"""Tests for port utility functions."""

from unittest.mock import patch, Mock


from codeframe.core.port_utils import (
    is_port_available,
    check_port_availability,
    validate_port_range,
)


class TestIsPortAvailable:
    """Test is_port_available function."""

    def test_port_available(self):
        """Test that function returns True for available port."""
        # Use a high random port that's likely to be available
        result = is_port_available(59999, "127.0.0.1")
        assert result is True

    @patch("socket.socket")
    def test_port_unavailable(self, mock_socket):
        """Test that function returns False when port is in use."""
        # Mock socket to raise OSError (port in use)
        mock_sock_instance = Mock()
        mock_sock_instance.__enter__ = Mock(return_value=mock_sock_instance)
        mock_sock_instance.__exit__ = Mock(return_value=None)
        mock_sock_instance.bind.side_effect = OSError("Address already in use")
        mock_socket.return_value = mock_sock_instance

        result = is_port_available(8080, "127.0.0.1")
        assert result is False


class TestCheckPortAvailability:
    """Test check_port_availability function."""

    def test_privileged_port_rejected(self):
        """Test that port <1024 is rejected with helpful message."""
        available, msg = check_port_availability(80, "127.0.0.1")

        assert available is False
        assert "elevated privileges" in msg.lower()
        assert "8080" in msg  # Should suggest alternative port

    def test_available_port_returns_true(self):
        """Test that available port returns (True, '')."""
        available, msg = check_port_availability(59998, "127.0.0.1")

        assert available is True
        assert msg == ""

    @patch("socket.socket")
    def test_port_in_use_returns_helpful_message(self, mock_socket):
        """Test helpful error message when port is in use."""
        # Mock socket to raise OSError with errno 98 (Linux: Address already in use)
        mock_sock_instance = Mock()
        mock_sock_instance.__enter__ = Mock(return_value=mock_sock_instance)
        mock_sock_instance.__exit__ = Mock(return_value=None)
        mock_error = OSError("Address already in use")
        mock_error.errno = 98
        mock_sock_instance.bind.side_effect = mock_error
        mock_socket.return_value = mock_sock_instance

        available, msg = check_port_availability(8080, "127.0.0.1")

        assert available is False
        assert "8080" in msg
        assert "already in use" in msg.lower()
        assert "8081" in msg  # Should suggest port+1

    @patch("socket.socket")
    def test_other_os_error_returns_error_message(self, mock_socket):
        """Test that other OSErrors return descriptive message."""
        # Mock socket to raise OSError with different errno
        mock_sock_instance = Mock()
        mock_sock_instance.__enter__ = Mock(return_value=mock_sock_instance)
        mock_sock_instance.__exit__ = Mock(return_value=None)
        mock_error = OSError("Some other error")
        mock_error.errno = 999  # Not a known errno
        mock_sock_instance.bind.side_effect = mock_error
        mock_socket.return_value = mock_sock_instance

        available, msg = check_port_availability(8080, "127.0.0.1")

        assert available is False
        assert "Cannot bind" in msg
        assert "8080" in msg


class TestValidatePortRange:
    """Test validate_port_range function."""

    def test_valid_port_returns_true(self):
        """Test that valid port (1024-65535) returns (True, '')."""
        for port in [1024, 8080, 65535]:
            valid, msg = validate_port_range(port)
            assert valid is True, f"Port {port} should be valid"
            assert msg == "", f"Port {port} should have empty message"

    def test_privileged_port_rejected(self):
        """Test that port <1024 is rejected."""
        for port in [1, 80, 443, 1023]:
            valid, msg = validate_port_range(port)
            assert valid is False, f"Port {port} should be invalid"
            assert "elevated privileges" in msg.lower()

    def test_port_above_max_rejected(self):
        """Test that port >65535 is rejected."""
        for port in [65536, 100000]:
            valid, msg = validate_port_range(port)
            assert valid is False, f"Port {port} should be invalid"
            assert "out of range" in msg.lower()
            assert "65535" in msg
