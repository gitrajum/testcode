"""
EmailMcp CLI Tool

Manage infrastructure and deployment for EmailMcp MCP server.

Usage:
    email-mcp-cli docker [COMMAND]  # Docker image management
    email-mcp-cli infra [COMMAND]   # Infrastructure operations
"""

import typer
from rich.console import Console

from .commands import docker, iac

console = Console()

app = typer.Typer(
    name="email-mcp-cli",
    help="CLI tool for EmailMcp MCP server infrastructure and deployment",
    add_completion=False,
)

# Register commands
app.add_typer(docker.app, name="docker", help="🐳 Docker image management")
app.add_typer(iac.app, name="infra", help="🏗️  Infrastructure operations (Terraform)")

# Keep legacy name for backward compatibility
app.add_typer(iac.app, name="iac", help="[DEPRECATED] Use 'infra' instead", hidden=True)


@app.command()
def version():
    """Show CLI version."""
    from . import __version__

    console.print(f"email-mcp-cli version {__version__}")


if __name__ == "__main__":
    app()
