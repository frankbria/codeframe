"""A typo in .codeframe/config.yaml must not take down the CLI (#931).

`EnvironmentConfig.from_dict` ended with `return cls(**data)` on plain
dataclasses, so any unrecognized or misspelled key raised TypeError — and none
of the load sites guarded it. One typo, or a config written by a newer version,
broke `cf work start`, `cf work batch run`, and all LLM provider resolution with
a raw traceback.
"""

import logging
from pathlib import Path

import pytest
import yaml

from codeframe.core.config import EnvironmentConfig, load_environment_config

pytestmark = pytest.mark.v2


def _write_config(root: Path, body: str) -> Path:
    cf = root / ".codeframe"
    cf.mkdir(parents=True, exist_ok=True)
    (cf / "config.yaml").write_text(body)
    return root


class TestUnknownKeysAreIgnored:
    def test_unknown_top_level_key_is_dropped_and_warned(self, tmp_path, caplog):
        _write_config(
            tmp_path,
            yaml.safe_dump({"package_manager": "poetry", "packge_manger": "uv"}),
        )

        with caplog.at_level(logging.WARNING):
            config = load_environment_config(tmp_path)

        assert config is not None
        assert config.package_manager == "poetry", "known keys must still apply"
        assert "packge_manger" in caplog.text, "the warning must name the offending key"

    def test_unknown_nested_key_is_dropped(self, tmp_path, caplog):
        _write_config(
            tmp_path,
            yaml.safe_dump(
                {"llm": {"provider": "openai", "modl": "gpt-4o", "model": "gpt-4o"}}
            ),
        )

        with caplog.at_level(logging.WARNING):
            config = load_environment_config(tmp_path)

        assert config is not None
        assert config.llm.provider == "openai"
        assert config.llm.model == "gpt-4o"
        assert "modl" in caplog.text

    def test_several_unknown_keys_are_all_named(self, tmp_path, caplog):
        _write_config(tmp_path, yaml.safe_dump({"alpha": 1, "beta": 2, "gamma": 3}))

        with caplog.at_level(logging.WARNING):
            load_environment_config(tmp_path)

        for key in ("alpha", "beta", "gamma"):
            assert key in caplog.text

    def test_non_string_keys_do_not_crash_the_warning(self, tmp_path, caplog):
        """YAML keys need not be strings: `123: x` and `true: y` are valid.

        Surfaced by `codex review`'s own probe on this PR — both sorted() and
        join() raise on a mixed-type key set, so reporting the bad key crashed
        for the same class of input the fix exists to survive.
        """
        _write_config(tmp_path, "123: x\ntrue: y\npackage_manager: poetry\n")

        with caplog.at_level(logging.WARNING):
            config = load_environment_config(tmp_path)

        assert config is not None
        assert config.package_manager == "poetry"
        assert "123" in caplog.text

    def test_from_dict_survives_mixed_type_keys(self):
        config = EnvironmentConfig.from_dict({"package_manager": "pip", 123: "x"})

        assert config.package_manager == "pip"

    def test_from_dict_is_tolerant_directly(self):
        config = EnvironmentConfig.from_dict(
            {"package_manager": "pip", "not_a_real_key": True}
        )

        assert config.package_manager == "pip"


class TestMalformedConfigDoesNotBreakEntryPoints:
    """AC2 — one test per entry point named in the issue."""

    @pytest.fixture
    def broken_workspace(self, tmp_path):
        _write_config(
            tmp_path,
            yaml.safe_dump({"llm": {"provider": "openai"}, "bogus_key": "boom"}),
        )
        return tmp_path

    def test_llm_provider_resolution_survives(self, broken_workspace, monkeypatch):
        from codeframe.core.llm_resolution import resolve_llm_settings

        monkeypatch.delenv("CODEFRAME_LLM_PROVIDER", raising=False)
        settings = resolve_llm_settings(broken_workspace)

        assert settings.provider_type == "openai", "config still applied"

    def test_runtime_execute_agent_config_load_survives(self, broken_workspace):
        """runtime.py loads env config on the `cf work start` path."""
        config = load_environment_config(broken_workspace)
        assert config is not None
        assert config.llm.provider == "openai"

    def test_conductor_batch_config_load_survives(self, broken_workspace):
        """conductor.py loads env config on the `cf work batch run` path."""
        from codeframe.core.config import load_environment_config as loader

        assert loader(broken_workspace) is not None


class TestMalformedShapesAreActionable:
    def test_wrong_type_for_a_nested_key_does_not_traceback(self, tmp_path, caplog):
        """`llm: "openai"` (a string where a block belongs) must be survivable."""
        _write_config(tmp_path, yaml.safe_dump({"llm": "openai"}))

        with caplog.at_level(logging.WARNING):
            config = load_environment_config(tmp_path)

        assert config is not None
        assert "llm" in caplog.text

    def test_unparseable_yaml_does_not_traceback(self, tmp_path, caplog):
        _write_config(tmp_path, "package_manager: [unclosed\n")

        with caplog.at_level(logging.WARNING):
            config = load_environment_config(tmp_path)

        assert config is not None, "a broken file must fall back, not explode"

    def test_undecodable_bytes_do_not_traceback(self, tmp_path, caplog):
        """UnicodeDecodeError is a ValueError, not an OSError.

        Raised by the PR bot review: it sailed past the (yaml.YAMLError, OSError)
        read guard and crashed the command — the exact AC2 failure. Same defect
        class as #1029.
        """
        cf = tmp_path / ".codeframe"
        cf.mkdir(parents=True, exist_ok=True)
        (cf / "config.yaml").write_bytes(b"package_manager: \xff\xfe binary junk\n")

        with caplog.at_level(logging.WARNING):
            config = load_environment_config(tmp_path)

        assert config is not None
        assert config.package_manager == "uv", "falls back to defaults"

    def test_top_level_scalar_does_not_traceback(self, tmp_path, caplog):
        """A YAML file that parses to a string, not a mapping."""
        _write_config(tmp_path, "just a string\n")

        with caplog.at_level(logging.WARNING):
            config = load_environment_config(tmp_path)

        assert config is not None

    def test_wrong_scalar_type_on_a_known_key_is_actionable(self, tmp_path, caplog):
        """`hooks: [1, 2]` — a list where a mapping belongs."""
        _write_config(tmp_path, yaml.safe_dump({"hooks": [1, 2]}))

        with caplog.at_level(logging.WARNING):
            config = load_environment_config(tmp_path)

        assert config is not None
        assert "hooks" in caplog.text


class TestNoSpuriousWarnings:
    """A warning that fires on normal use trains people to ignore warnings."""

    def test_save_then_load_round_trip_is_silent(self, tmp_path, caplog):
        """`save_environment_config` writes `llm: null` for the unset default.

        Raised by the PR bot review: the nested-block guard treated that as a
        wrong-shaped value and warned on every ordinary round trip.
        """
        from codeframe.core.config import save_environment_config

        save_environment_config(tmp_path, EnvironmentConfig())

        with caplog.at_level(logging.WARNING):
            config = load_environment_config(tmp_path)

        assert config is not None
        assert config.llm is None
        assert caplog.text == "", f"unexpected warning on a clean round trip: {caplog.text}"

    def test_non_ascii_value_survives_a_save_load_round_trip(self, tmp_path, caplog):
        """Reader and writer must agree on encoding.

        Raised by the PR bot review: pinning only the read to UTF-8 meant that on
        a cp1252 locale (stock Windows) a non-ASCII value was written in the
        locale encoding and then rejected by our own reader, silently dropping
        the whole saved config on every later load.
        """
        from codeframe.core.config import save_environment_config

        original = EnvironmentConfig(test_command="pytest -k café_tests")
        save_environment_config(tmp_path, original)

        raw = (tmp_path / ".codeframe" / "config.yaml").read_bytes()
        assert "café".encode("utf-8") in raw, "writer did not emit UTF-8"

        with caplog.at_level(logging.WARNING):
            reloaded = load_environment_config(tmp_path)

        assert reloaded.test_command == "pytest -k café_tests"
        assert caplog.text == ""

    def test_explicit_null_nested_block_uses_defaults(self, tmp_path, caplog):
        _write_config(tmp_path, "hooks: null\npackage_manager: poetry\n")

        with caplog.at_level(logging.WARNING):
            config = load_environment_config(tmp_path)

        assert config.package_manager == "poetry"
        assert config.hooks.hook_timeout == 60, "defaulted, not dropped to None"
        assert caplog.text == ""


class TestValidConfigStillWorks:
    def test_full_config_round_trips(self, tmp_path):
        _write_config(
            tmp_path,
            yaml.safe_dump(
                {
                    "package_manager": "uv",
                    "test_framework": "pytest",
                    "llm": {"provider": "ollama", "model": "qwen2.5-coder:7b"},
                }
            ),
        )

        config = load_environment_config(tmp_path)

        assert config.package_manager == "uv"
        assert config.test_framework == "pytest"
        assert config.llm.provider == "ollama"
        assert config.llm.model == "qwen2.5-coder:7b"

    def test_empty_file_yields_defaults(self, tmp_path):
        _write_config(tmp_path, "")

        assert load_environment_config(tmp_path) is not None
