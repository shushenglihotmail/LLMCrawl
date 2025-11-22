"""
Main entry point for Azure DevOps MCP Server.
Supports both stdio (VS Code) and HTTP (LLMCrawl) modes.
"""

import argparse
import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Azure DevOps MCP Server - Dual Mode (stdio/HTTP)"
    )

    parser.add_argument(
        "--mode",
        type=str,
        choices=["stdio", "http"],
        default=os.getenv("MCP_MODE", "stdio"),
        help="Server mode: stdio (VS Code) or http (LLMCrawl)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8004")),
        help="HTTP server port (only for HTTP mode)",
    )

    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("MCP_HOST", "0.0.0.0"),
        help="HTTP server host (only for HTTP mode)",
    )

    parser.add_argument(
        "--organization",
        type=str,
        default=os.getenv("AZURE_DEVOPS_ORG", "microsoft"),
        help="Azure DevOps organization",
    )

    parser.add_argument(
        "--project",
        type=str,
        default=os.getenv("AZURE_DEVOPS_PROJECT", "OS"),
        help="Azure DevOps project",
    )

    parser.add_argument(
        "--repository",
        type=str,
        default=os.getenv("AZURE_DEVOPS_REPO", "os.2020"),
        help="Azure DevOps repository",
    )

    parser.add_argument(
        "--branch",
        type=str,
        default=os.getenv("AZURE_DEVOPS_BRANCH", "main"),
        help="Default branch for file operations",
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=int(os.getenv("AZURE_DEVOPS_MAX_RESULTS", "50")),
        help="Maximum number of results to return",
    )

    parser.add_argument(
        "--auth-mode",
        type=str,
        choices=["interactive", "pat"],
        default=os.getenv("AZURE_DEVOPS_AUTH_MODE", "interactive"),
        help="Authentication mode: interactive (OAuth) or pat (Personal Access Token)",
    )

    parser.add_argument(
        "--pat",
        type=str,
        default=os.getenv("AZURE_DEVOPS_PAT"),
        help="Personal Access Token (required if --auth-mode=pat)",
    )

    return parser.parse_args()


async def run_stdio_mode(
    organization: str,
    project: str,
    repository: str,
    pat: str = None,
    branch: str = "main",
    max_results: int = 50,
):
    """Run server in stdio mode for VS Code."""
    from .server import AzureDevOpsMCPServer

    logger.info(f"Starting Azure DevOps MCP Server in stdio mode")
    logger.info(f"Organization: {organization}")
    logger.info(f"Project: {project}")
    logger.info(f"Repository: {repository}")
    logger.info(f"Branch: {branch}")
    logger.info(f"Max Results: {max_results}")

    server = AzureDevOpsMCPServer(
        organization, project, repository, pat, branch, max_results
    )

    # Initialize with interactive auth by default in stdio mode
    use_interactive = pat is None
    if not await server.initialize(use_interactive_auth=use_interactive):
        logger.error("Failed to initialize server")
        sys.exit(1)

    logger.info("Server initialized successfully")
    await server.run_stdio()


def run_http_mode(host: str, port: int):
    """Run server in HTTP mode for LLMCrawl."""
    import uvicorn

    from .http_server import create_http_app

    logger.info(f"Starting Azure DevOps MCP Server in HTTP mode")
    logger.info(f"Listening on {host}:{port}")

    app = create_http_app()
    uvicorn.run(app, host=host, port=port)


def main():
    """Main entry point."""
    args = parse_args()

    # Validate PAT if required
    if args.auth_mode == "pat" and not args.pat:
        logger.error("Personal Access Token is required when using --auth-mode=pat")
        logger.error("Set AZURE_DEVOPS_PAT environment variable or use --pat argument")
        sys.exit(1)

    # Set environment variables for child processes
    os.environ["AZURE_DEVOPS_ORG"] = args.organization
    os.environ["AZURE_DEVOPS_PROJECT"] = args.project
    os.environ["AZURE_DEVOPS_REPO"] = args.repository
    os.environ["AZURE_DEVOPS_BRANCH"] = args.branch
    os.environ["AZURE_DEVOPS_MAX_RESULTS"] = str(args.max_results)
    os.environ["AZURE_DEVOPS_AUTH_MODE"] = args.auth_mode
    if args.pat:
        os.environ["AZURE_DEVOPS_PAT"] = args.pat

    if args.mode == "stdio":
        asyncio.run(
            run_stdio_mode(
                args.organization,
                args.project,
                args.repository,
                args.pat,
                args.branch,
                args.max_results,
            )
        )
    else:
        run_http_mode(args.host, args.port)


if __name__ == "__main__":
    main()
