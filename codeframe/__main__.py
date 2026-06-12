"""Entry point for `python -m codeframe` invocation.

This module enables running the CLI via:
    python -m codeframe [command] [options]

The help text will correctly show 'codeframe' as the command name.
"""


def main():
    """Run the CLI with proper program name."""
    from codeframe.cli.app import main as app_main

    # The telemetry-aware wrapper invokes the app with prog_name="codeframe",
    # so the usage line shows the right command name here too.
    app_main()


if __name__ == "__main__":
    main()
