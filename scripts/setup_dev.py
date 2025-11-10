#!/usr/bin/env python3
"""
Development environment setup script for LLMCrawl project.
This script sets up a local Python development environment with all dependencies.
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd, check=True):
    """Run a shell command and print output."""
    print(f"Running: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        if e.stderr:
            print(f"Error output: {e.stderr}")
        sys.exit(1)


def create_venv():
    """Create Python virtual environment."""
    if not os.path.exists("venv"):
        print("Creating Python virtual environment...")
        run_command(f"{sys.executable} -m venv venv")
    else:
        print("Virtual environment already exists.")


def get_pip_command():
    """Get the correct pip command based on OS."""
    if os.name == 'nt':  # Windows
        return "venv\\Scripts\\pip"
    else:  # Unix/Linux/macOS
        return "venv/bin/pip"


def get_python_command():
    """Get the correct python command based on OS."""
    if os.name == 'nt':  # Windows
        return "venv\\Scripts\\python"
    else:  # Unix/Linux/macOS
        return "venv/bin/python"


def install_requirements():
    """Install all Python dependencies."""
    pip_cmd = get_pip_command()
    
    # Upgrade pip first
    run_command(f"{pip_cmd} install --upgrade pip")
    
    # Install requirements in order
    requirements_files = [
        "requirements/gateway.txt",
        "requirements/crawler.txt", 
        "requirements/indexer.txt",
        "requirements/test.txt",
        "requirements/dev.txt"
    ]
    
    for req_file in requirements_files:
        if os.path.exists(req_file):
            print(f"Installing dependencies from {req_file}...")
            run_command(f"{pip_cmd} install -r {req_file}")


def install_playwright():
    """Install Playwright browsers."""
    python_cmd = get_python_command()
    print("Installing Playwright browsers...")
    run_command(f"{python_cmd} -m playwright install")
    run_command(f"{python_cmd} -m playwright install-deps")


def setup_pre_commit():
    """Setup pre-commit hooks."""
    python_cmd = get_python_command()
    if os.path.exists(".pre-commit-config.yaml"):
        print("Setting up pre-commit hooks...")
        run_command(f"{python_cmd} -m pre_commit install")


def create_env_file():
    """Create .env file from example if it doesn't exist."""
    if not os.path.exists(".env") and os.path.exists(".env.example"):
        print("Creating .env file from .env.example...")
        import shutil
        shutil.copy(".env.example", ".env")
        print("Please edit .env file with your API keys and configuration.")


def main():
    """Main setup function."""
    print("🚀 Setting up LLMCrawl development environment...")
    
    # Check Python version
    if sys.version_info < (3, 10):
        print("❌ Python 3.10+ is required!")
        sys.exit(1)
    
    # Change to project root directory (parent of scripts)
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    # Setup steps
    create_venv()
    install_requirements()
    install_playwright()
    setup_pre_commit()
    create_env_file()
    
    print("\n✅ Development environment setup complete!")
    print("\nNext steps:")
    print("1. Edit .env file with your API keys")
    print("2. Run 'make dev-up' to start development services") 
    print("3. Run 'make health' to verify all services are running")
    
    if os.name == 'nt':  # Windows
        print("4. Activate environment: venv\\Scripts\\activate")
    else:  # Unix/Linux/macOS
        print("4. Activate environment: source venv/bin/activate")


if __name__ == "__main__":
    main()