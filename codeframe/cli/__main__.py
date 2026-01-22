"""Entry point for `python -m codeframe.cli` invocation.

This module enables running the CLI via:
    python -m codeframe.cli [command] [options]

The help text will correctly show 'codeframe' as the command name.
"""


def main():
    """Run the CLI with proper program name."""
    from codeframe.cli.app import app

    # Use Typer's prog_name to override the usage line
    # This is more reliable than sys.argv[0] manipulation
    app(prog_name="codeframe")


if __name__ == "__main__":
    main()
