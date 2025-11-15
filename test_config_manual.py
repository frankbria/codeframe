#!/usr/bin/env python3
"""Manual test script for configuration (no pytest required)."""

import os
import sys
import tempfile
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from codeframe.core.config import Config, GlobalConfig, load_environment


def test_default_values():
    """Test default values."""
    print("✓ Testing default values...")
    config = GlobalConfig()
    assert config.database_path == ".codeframe/state.db"
    assert config.api_host == "0.0.0.0"
    assert config.api_port == 8080
    assert config.log_level == "INFO"
    print("  ✓ All defaults correct")


def test_cors_origins():
    """Test CORS origins parsing."""
    print("✓ Testing CORS origins parsing...")
    config = GlobalConfig(cors_origins="http://localhost:3000, http://localhost:5173")
    origins = config.get_cors_origins_list()
    assert len(origins) == 2
    assert "http://localhost:3000" in origins
    print("  ✓ CORS parsing works")


def test_log_level_validation():
    """Test log level validation."""
    print("✓ Testing log level validation...")

    # Valid
    config = GlobalConfig(log_level="DEBUG")
    assert config.log_level == "DEBUG"

    # Case insensitive
    config = GlobalConfig(log_level="info")
    assert config.log_level == "INFO"

    # Invalid should raise
    try:
        GlobalConfig(log_level="INVALID")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "LOG_LEVEL must be one of" in str(e)

    print("  ✓ Log level validation works")


def test_port_validation():
    """Test port validation."""
    print("✓ Testing port validation...")

    # Valid
    config = GlobalConfig(api_port=3000)
    assert config.api_port == 3000

    # Invalid (too low)
    try:
        GlobalConfig(api_port=0)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "API_PORT must be between" in str(e)

    print("  ✓ Port validation works")


def test_sprint_validation():
    """Test sprint validation."""
    print("✓ Testing sprint validation...")

    # With API key - should pass
    config = GlobalConfig(anthropic_api_key="sk-test-key")
    config.validate_required_for_sprint(sprint=1)
    print("  ✓ Validation passes with API key")

    # Without API key - should fail
    config = GlobalConfig()
    try:
        config.validate_required_for_sprint(sprint=1)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "ANTHROPIC_API_KEY is required" in str(e)
    print("  ✓ Validation fails without API key")


def test_ensure_directories():
    """Test directory creation."""
    print("✓ Testing directory creation...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "test_db" / "state.db"
        log_path = tmp_path / "logs" / "test.log"

        config = GlobalConfig(database_path=str(db_path), log_file=str(log_path))
        config.ensure_directories()

        assert db_path.parent.exists()
        assert log_path.parent.exists()
        print("  ✓ Directories created successfully")


def test_config_manager():
    """Test Config manager."""
    print("✓ Testing Config manager...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        config = Config(tmp_path)

        assert config.project_dir == tmp_path
        assert config.config_dir == tmp_path / ".codeframe"
        print("  ✓ Config manager initialized")


def test_environment_loading():
    """Test environment file loading."""
    print("✓ Testing environment file loading...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-test-env-file")

        # Save current directory and change to temp
        original_cwd = Path.cwd()
        original_key = os.getenv("ANTHROPIC_API_KEY")

        try:
            os.chdir(tmp_path)
            load_environment()

            config = GlobalConfig()
            assert config.anthropic_api_key == "sk-test-env-file"
            print("  ✓ Environment loaded from .env file")

        finally:
            os.chdir(original_cwd)
            # Restore or remove environment variable
            if original_key:
                os.environ["ANTHROPIC_API_KEY"] = original_key
            else:
                os.environ.pop("ANTHROPIC_API_KEY", None)


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("CONFIGURATION TESTS")
    print("=" * 70 + "\n")

    try:
        test_default_values()
        test_cors_origins()
        test_log_level_validation()
        test_port_validation()
        test_sprint_validation()
        test_ensure_directories()
        test_config_manager()
        test_environment_loading()

        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70 + "\n")
        return 0

    except Exception as e:
        print("\n" + "=" * 70)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 70 + "\n")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
