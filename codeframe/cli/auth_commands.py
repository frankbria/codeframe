"""CLI authentication commands (login, logout, register, whoami, credentials).

This module provides commands for:
- Logging in with email/password
- Logging out (clearing credentials)
- Registering a new account
- Viewing current user info
- Managing API credentials (setup, list, validate, rotate, remove)

Usage:
    codeframe auth login --email user@example.com --password secret
    codeframe auth logout
    codeframe auth register --email new@example.com --password secret
    codeframe auth whoami
    codeframe auth setup --provider anthropic --value sk-ant-...
    codeframe auth list
    codeframe auth validate anthropic
    codeframe auth rotate anthropic --value sk-ant-new-...
    codeframe auth remove anthropic --yes
"""

import logging
from typing import Optional, Tuple

import requests
import typer
from rich.table import Table

from codeframe.cli.auth import store_token, clear_token, is_authenticated
from codeframe.cli.api_client import APIClient, AuthenticationError, get_api_base_url
from codeframe.cli.helpers import console
from codeframe.core.credentials import (
    CredentialManager,
    CredentialProvider,
    CredentialSource,
)

logger = logging.getLogger(__name__)


# Provider name aliases for CLI convenience
PROVIDER_ALIASES = {
    # Anthropic
    "anthropic": CredentialProvider.LLM_ANTHROPIC,
    "claude": CredentialProvider.LLM_ANTHROPIC,
    "llm_anthropic": CredentialProvider.LLM_ANTHROPIC,
    # OpenAI
    "openai": CredentialProvider.LLM_OPENAI,
    "gpt": CredentialProvider.LLM_OPENAI,
    "gpt4": CredentialProvider.LLM_OPENAI,
    "llm_openai": CredentialProvider.LLM_OPENAI,
    # GitHub
    "github": CredentialProvider.GIT_GITHUB,
    "gh": CredentialProvider.GIT_GITHUB,
    "git_github": CredentialProvider.GIT_GITHUB,
    # GitLab
    "gitlab": CredentialProvider.GIT_GITLAB,
    "gl": CredentialProvider.GIT_GITLAB,
    "git_gitlab": CredentialProvider.GIT_GITLAB,
    # CI/CD
    "cicd": CredentialProvider.CICD_GENERIC,
    "ci": CredentialProvider.CICD_GENERIC,
    "cicd_generic": CredentialProvider.CICD_GENERIC,
    # Database
    "database": CredentialProvider.DATABASE,
    "db": CredentialProvider.DATABASE,
}


def resolve_provider_name(name: str) -> CredentialProvider:
    """Resolve a provider name/alias to CredentialProvider enum.

    Args:
        name: Provider name or alias (case-insensitive)

    Returns:
        CredentialProvider enum value

    Raises:
        ValueError: If name doesn't match any known provider
    """
    normalized = name.lower().strip()

    if normalized in PROVIDER_ALIASES:
        return PROVIDER_ALIASES[normalized]

    # Try direct enum lookup
    try:
        return CredentialProvider[name.upper()]
    except KeyError:
        pass

    valid_names = sorted(set(PROVIDER_ALIASES.keys()))
    raise ValueError(
        f"Unknown provider: '{name}'. Valid providers: {', '.join(valid_names)}"
    )


def validate_anthropic_credential(api_key: str) -> Tuple[bool, str]:
    """Validate Anthropic API key by making a test request.

    Args:
        api_key: The API key to validate

    Returns:
        Tuple of (is_valid, message)
    """
    try:
        from anthropic import Anthropic, AuthenticationError as AnthropicAuthError
        from anthropic import APIConnectionError, RateLimitError, APIStatusError

        client = Anthropic(api_key=api_key)
        # Make a minimal request to validate
        client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        return True, "API key is valid"
    except AnthropicAuthError:
        return False, "Invalid API key - authentication failed"
    except APIConnectionError as e:
        return False, f"Unable to validate - network error: {e}"
    except RateLimitError:
        # Rate limited but key is valid (they wouldn't rate limit invalid keys)
        return True, "API key appears valid (rate limited)"
    except APIStatusError as e:
        return False, f"Unable to validate - API error (HTTP {e.status_code})"
    except ImportError:
        return False, "Unable to validate - anthropic package not installed"
    except Exception as e:
        return False, f"Unable to validate - unexpected error: {type(e).__name__}: {e}"


def validate_openai_credential(api_key: str) -> Tuple[bool, str]:
    """Validate OpenAI API key by making a test request.

    Args:
        api_key: The API key to validate

    Returns:
        Tuple of (is_valid, message)
    """
    try:
        from openai import OpenAI, AuthenticationError as OpenAIAuthError
        from openai import APIConnectionError, RateLimitError, APIStatusError

        client = OpenAI(api_key=api_key)
        # List models is a cheap validation
        client.models.list()
        return True, "API key is valid"
    except OpenAIAuthError:
        return False, "Invalid API key - authentication failed"
    except APIConnectionError as e:
        return False, f"Unable to validate - network error: {e}"
    except RateLimitError:
        # Rate limited but key is valid
        return True, "API key appears valid (rate limited)"
    except APIStatusError as e:
        return False, f"Unable to validate - API error (HTTP {e.status_code})"
    except ImportError:
        return False, "Unable to validate - openai package not installed"
    except Exception as e:
        return False, f"Unable to validate - unexpected error: {type(e).__name__}: {e}"


def validate_github_credential(token: str) -> Tuple[bool, str]:
    """Validate GitHub token by making a test request.

    Args:
        token: The GitHub token to validate

    Returns:
        Tuple of (is_valid, message)
    """
    try:
        response = requests.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=10,
        )
        if response.status_code == 200:
            user = response.json()
            return True, f"Token valid for user: {user.get('login', 'unknown')}"
        elif response.status_code == 401:
            return False, "Invalid token - authentication failed"
        elif response.status_code == 403:
            # Forbidden - token may be valid but rate limited or lacking permissions
            return False, "Token rejected - rate limited or insufficient permissions"
        elif response.status_code == 429:
            # Rate limited but token format was accepted
            return True, "Token appears valid (rate limited)"
        else:
            return False, f"Unable to validate - GitHub API returned HTTP {response.status_code}"
    except requests.ConnectionError:
        return False, "Unable to validate - network error (cannot reach GitHub)"
    except requests.Timeout:
        return False, "Unable to validate - request timed out"
    except requests.RequestException as e:
        return False, f"Unable to validate - request error: {e}"
    except Exception as e:
        return False, f"Unable to validate - unexpected error: {type(e).__name__}: {e}"

auth_app = typer.Typer(
    name="auth",
    help="Authentication commands",
    no_args_is_help=True,
)


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


# =============================================================================
# Credential Management Commands
# =============================================================================


@auth_app.command("setup")
def setup_credential(
    provider: Optional[str] = typer.Option(
        None, "--provider", "-p", help="Provider name (e.g., anthropic, github, openai)"
    ),
    value: Optional[str] = typer.Option(
        None, "--value", "-v", help="Credential value (API key or token)", hide_input=True
    ),
):
    """Configure a credential for a provider.

    Securely stores API keys and tokens for LLM providers, Git services,
    and other integrations. Credentials are stored in the system keyring
    or an encrypted file.

    Examples:

        codeframe auth setup  # Interactive mode

        codeframe auth setup --provider anthropic --value sk-ant-...

        codeframe auth setup -p github -v ghp_...
    """
    manager = CredentialManager()

    # Interactive provider selection if not provided
    if not provider:
        console.print("\n[bold]Select a provider to configure:[/bold]\n")
        providers = [
            ("1", "anthropic", "Anthropic (Claude) - LLM API"),
            ("2", "openai", "OpenAI (GPT) - LLM API"),
            ("3", "github", "GitHub - Git integration"),
            ("4", "gitlab", "GitLab - Git integration"),
        ]
        for num, _, desc in providers:
            console.print(f"  {num}. {desc}")

        choice = typer.prompt("\nEnter number or provider name", default="1")

        # Map number to provider
        choice_map = {p[0]: p[1] for p in providers}
        provider = choice_map.get(choice, choice)

    # Resolve provider name
    try:
        provider_enum = resolve_provider_name(provider)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Prompt for value if not provided
    if not value:
        console.print(f"\nConfiguring [bold]{provider_enum.display_name}[/bold]")

        # Show environment variable hint
        env_hint = f"(or set {provider_enum.env_var} environment variable)"
        console.print(f"[dim]{env_hint}[/dim]\n")

        value = typer.prompt(
            "Enter credential value",
            hide_input=True,
        )

    # Reject empty or whitespace-only values
    if not value or not value.strip():
        console.print("[red]Error:[/red] Credential value cannot be empty")
        raise typer.Exit(1)

    # Validate format
    if not manager.validate_credential_format(provider_enum, value):
        console.print("[red]Error:[/red] Invalid credential format")
        console.print("Please check the value and try again.")
        raise typer.Exit(1)

    # Store credential
    manager.set_credential(provider_enum, value)
    console.print(f"[green]Successfully stored credential for {provider_enum.display_name}[/green]")


@auth_app.command("list")
def list_credentials():
    """List all configured credentials.

    Shows credentials from both environment variables and secure storage.
    Values are masked for security.

    Example:

        codeframe auth list
    """
    manager = CredentialManager()
    credentials = manager.list_credentials()

    if not credentials:
        console.print("\n[yellow]No credentials configured.[/yellow]")
        console.print("Use 'codeframe auth setup' to configure credentials.\n")
        return

    # Create table
    table = Table(title="Configured Credentials")
    table.add_column("Provider", style="cyan")
    table.add_column("Source", style="green")
    table.add_column("Value (masked)", style="dim")
    table.add_column("Status")

    for cred in credentials:
        source_str = "env" if cred.source == CredentialSource.ENVIRONMENT else "stored"

        if cred.is_expired:
            status = "[red]expired[/red]"
        else:
            status = "[green]valid[/green]"

        table.add_row(
            cred.provider.display_name,
            source_str,
            cred.masked_value or "***",
            status,
        )

    console.print()
    console.print(table)
    console.print()


@auth_app.command("validate")
def validate_credential(
    provider: str = typer.Argument(..., help="Provider to validate (e.g., anthropic, github)"),
):
    """Validate a credential by testing it with the provider.

    Makes a minimal API call to verify the credential is working.

    Examples:

        codeframe auth validate anthropic

        codeframe auth validate github
    """
    manager = CredentialManager()

    # Resolve provider
    try:
        provider_enum = resolve_provider_name(provider)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Get credential
    value = manager.get_credential(provider_enum)
    if not value:
        console.print(f"[red]Error:[/red] No credential configured for {provider_enum.display_name}")
        console.print("Use 'codeframe auth setup' to configure it, or set the environment variable.")
        raise typer.Exit(1)

    console.print(f"Validating {provider_enum.display_name} credential...")

    # Validate based on provider type
    if provider_enum == CredentialProvider.LLM_ANTHROPIC:
        valid, message = validate_anthropic_credential(value)
    elif provider_enum == CredentialProvider.LLM_OPENAI:
        valid, message = validate_openai_credential(value)
    elif provider_enum == CredentialProvider.GIT_GITHUB:
        valid, message = validate_github_credential(value)
    else:
        # Generic format validation for unsupported providers
        valid = manager.validate_credential_format(provider_enum, value)
        message = "Format appears valid" if valid else "Invalid format"

    if valid:
        console.print(f"[green]{message}[/green]")
    else:
        console.print(f"[red]Error:[/red] {message}")
        raise typer.Exit(1)


@auth_app.command("rotate")
def rotate_credential(
    provider: str = typer.Argument(..., help="Provider to rotate credential for"),
    value: Optional[str] = typer.Option(
        None, "--value", "-v", help="New credential value", hide_input=True
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip API validation of new credential"
    ),
):
    """Rotate a credential with a new value.

    Validates the new credential before storing (unless --force is used).
    The old credential is only replaced after successful validation.

    Examples:

        codeframe auth rotate anthropic --value sk-ant-new-...

        codeframe auth rotate github -v ghp_new_token --force
    """
    manager = CredentialManager()

    # Resolve provider
    try:
        provider_enum = resolve_provider_name(provider)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Check if credential exists
    source = manager.get_credential_source(provider_enum)
    if source == CredentialSource.NOT_FOUND:
        console.print(f"[yellow]Note:[/yellow] No existing credential for {provider_enum.display_name}")
        console.print("Use 'codeframe auth setup' to create a new credential.")
        raise typer.Exit(1)

    # Prompt for new value if not provided
    if not value:
        value = typer.prompt("Enter new credential value", hide_input=True)

    # Validate format
    if not manager.validate_credential_format(provider_enum, value):
        console.print("[red]Error:[/red] Invalid credential format")
        raise typer.Exit(1)

    # Validate with API unless --force
    if not force:
        console.print("Validating new credential...")

        if provider_enum == CredentialProvider.LLM_ANTHROPIC:
            valid, message = validate_anthropic_credential(value)
        elif provider_enum == CredentialProvider.LLM_OPENAI:
            valid, message = validate_openai_credential(value)
        elif provider_enum == CredentialProvider.GIT_GITHUB:
            valid, message = validate_github_credential(value)
        else:
            valid = True
            message = "Skipping API validation for this provider type"

        if not valid:
            console.print(f"[red]Error:[/red] {message}")
            console.print("Use --force to skip validation.")
            raise typer.Exit(1)

    # Rotate credential
    manager.rotate_credential(provider_enum, value)
    console.print(f"[green]Successfully rotated credential for {provider_enum.display_name}[/green]")


@auth_app.command("remove")
def remove_credential(
    provider: str = typer.Argument(..., help="Provider to remove credential for"),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompt"
    ),
):
    """Remove a stored credential.

    Note: This only removes credentials from secure storage.
    Environment variables are not affected.

    Examples:

        codeframe auth remove anthropic

        codeframe auth remove github --yes
    """
    manager = CredentialManager()

    # Resolve provider
    try:
        provider_enum = resolve_provider_name(provider)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Check if credential exists in storage (not just environment)
    source = manager.get_credential_source(provider_enum)
    if source != CredentialSource.STORED:
        if source == CredentialSource.ENVIRONMENT:
            console.print(
                f"[yellow]Credential for {provider_enum.display_name} is set via environment "
                f"variable ({provider_enum.env_var}) and cannot be removed by this command[/yellow]"
            )
        else:
            console.print(f"[yellow]No stored credential found for {provider_enum.display_name}[/yellow]")
        return

    # Confirm deletion
    if not yes:
        confirm = typer.confirm(
            f"Remove stored credential for {provider_enum.display_name}?"
        )
        if not confirm:
            console.print("Cancelled.")
            return

    # Delete credential
    manager.delete_credential(provider_enum)
    console.print(f"[green]Removed stored credential for {provider_enum.display_name}[/green]")
