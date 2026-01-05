"""CLI authentication commands (login, logout, register, whoami).

This module provides commands for:
- Logging in with email/password
- Logging out (clearing credentials)
- Registering a new account
- Viewing current user info

Usage:
    codeframe auth login --email user@example.com --password secret
    codeframe auth logout
    codeframe auth register --email new@example.com --password secret
    codeframe auth whoami
"""

import logging
from typing import Optional

import requests
import typer
from rich.console import Console

from codeframe.cli.auth import store_token, clear_token, get_token, is_authenticated
from codeframe.cli.api_client import APIClient, AuthenticationError, get_api_base_url

logger = logging.getLogger(__name__)

auth_app = typer.Typer(
    name="auth",
    help="Authentication commands",
    no_args_is_help=True,
)
console = Console()


@auth_app.command()
def login(
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Your email address"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Your password", hide_input=True),
):
    """Log in to CodeFRAME.

    Authenticates with the server and stores your JWT token locally.
    You will be prompted for email and password if not provided.

    Examples:

        codeframe auth login

        codeframe auth login --email user@example.com

        codeframe auth login -e user@example.com -p secret
    """
    # Prompt for email if not provided
    if not email:
        email = typer.prompt("Email")

    # Prompt for password if not provided
    if not password:
        password = typer.prompt("Password", hide_input=True)

    # Call login API
    base_url = get_api_base_url()
    login_url = f"{base_url}/auth/jwt/login"

    try:
        # FastAPI Users expects form data, not JSON
        response = requests.post(
            login_url,
            data={
                "username": email,  # FastAPI Users uses 'username' field
                "password": password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")

            if token:
                store_token(token)
                console.print(f"[green]✓ Successfully logged in as {email}[/green]")
            else:
                console.print("[red]Error:[/red] No token received from server")
                raise typer.Exit(1)

        elif response.status_code == 400:
            # Bad credentials
            console.print("[red]Error:[/red] Invalid email or password")
            raise typer.Exit(1)

        elif response.status_code == 422:
            # Validation error
            console.print("[red]Error:[/red] Invalid request format")
            raise typer.Exit(1)

        else:
            console.print(f"[red]Error:[/red] Login failed (HTTP {response.status_code})")
            raise typer.Exit(1)

    except requests.ConnectionError:
        console.print(f"[red]Error:[/red] Cannot connect to server at {base_url}")
        console.print("Make sure the CodeFRAME server is running: codeframe serve")
        raise typer.Exit(1)

    except requests.Timeout:
        console.print("[red]Error:[/red] Request timed out")
        raise typer.Exit(1)


@auth_app.command()
def logout():
    """Log out of CodeFRAME.

    Removes your stored credentials from the local machine.

    Example:

        codeframe auth logout
    """
    clear_token()
    console.print("[green]✓ Logged out successfully[/green]")


@auth_app.command()
def register(
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Your email address"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Your password", hide_input=True),
):
    """Register a new CodeFRAME account.

    Creates a new account and automatically logs you in.

    Examples:

        codeframe auth register

        codeframe auth register --email new@example.com --password secret
    """
    # Prompt for email if not provided
    if not email:
        email = typer.prompt("Email")

    # Prompt for password if not provided
    if not password:
        password = typer.prompt("Password", hide_input=True)
        # Confirm password
        password_confirm = typer.prompt("Confirm password", hide_input=True)
        if password != password_confirm:
            console.print("[red]Error:[/red] Passwords don't match")
            raise typer.Exit(1)

    # Call register API
    base_url = get_api_base_url()
    register_url = f"{base_url}/auth/register"

    try:
        response = requests.post(
            register_url,
            json={
                "email": email,
                "password": password,
            },
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        if response.status_code == 201:
            console.print(f"[green]✓ Account registered successfully for {email}[/green]")

            # Auto-login after registration
            console.print("Logging in...")
            login_url = f"{base_url}/auth/jwt/login"
            login_response = requests.post(
                login_url,
                data={"username": email, "password": password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )

            if login_response.status_code == 200:
                token = login_response.json().get("access_token")
                if token:
                    store_token(token)
                    console.print("[green]✓ Logged in automatically[/green]")
            else:
                console.print("[yellow]Note:[/yellow] Please log in manually: codeframe auth login")

        elif response.status_code == 400:
            error_detail = response.json().get("detail", "")
            if "ALREADY_EXISTS" in str(error_detail).upper():
                console.print("[red]Error:[/red] An account with this email already exists")
            else:
                console.print(f"[red]Error:[/red] Registration failed: {error_detail}")
            raise typer.Exit(1)

        elif response.status_code == 422:
            # Validation error
            error_data = response.json()
            console.print("[red]Error:[/red] Invalid registration data")
            if "detail" in error_data:
                for error in error_data["detail"]:
                    field = error.get("loc", ["", ""])[-1]
                    msg = error.get("msg", "")
                    console.print(f"  - {field}: {msg}")
            raise typer.Exit(1)

        else:
            console.print(f"[red]Error:[/red] Registration failed (HTTP {response.status_code})")
            raise typer.Exit(1)

    except requests.ConnectionError:
        console.print(f"[red]Error:[/red] Cannot connect to server at {base_url}")
        console.print("Make sure the CodeFRAME server is running: codeframe serve")
        raise typer.Exit(1)

    except requests.Timeout:
        console.print("[red]Error:[/red] Request timed out")
        raise typer.Exit(1)


@auth_app.command()
def whoami():
    """Show current logged-in user.

    Displays your email and account information.

    Example:

        codeframe auth whoami
    """
    # Check if authenticated
    if not is_authenticated():
        console.print("[yellow]Not logged in.[/yellow]")
        console.print("Please log in: codeframe auth login")
        raise typer.Exit(1)

    # Get user info
    try:
        client = APIClient()
        user = client.get("/users/me")

        console.print(f"\n[bold]Logged in as:[/bold] {user.get('email', 'Unknown')}")
        if user.get("id"):
            console.print(f"[bold]User ID:[/bold] {user['id']}")
        console.print()

    except AuthenticationError:
        console.print("[yellow]Session expired.[/yellow]")
        console.print("Please log in again: codeframe auth login")
        raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
