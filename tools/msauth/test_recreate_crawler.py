#!/usr/bin/env python3
"""
Tests for recreate_crawler compose file selection logic.

Verifies that the auth tool uses docker-compose.dev.yml in development
environments and docker-compose.yml in production deployments.

Bug context: The auth tool previously hardcoded docker-compose.yml which
maps deploy/crawler/ (empty) instead of ../crawler/ (real source code),
causing the crawler container to fail with "Could not import module
crawler.main" after re-authentication.
"""

import subprocess

# Import the functions under test
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from tools.msauth.authenticate import _get_compose_file, recreate_crawler


class TestGetComposeFile:
    """Test _get_compose_file selects the right compose file."""

    def test_prefers_dev_compose_when_exists(self, tmp_path):
        """When docker-compose.dev.yml exists, use it (dev environment)."""
        (tmp_path / "docker-compose.yml").touch()
        (tmp_path / "docker-compose.dev.yml").touch()
        assert _get_compose_file(tmp_path) == "docker-compose.dev.yml"

    def test_falls_back_to_prod_compose(self, tmp_path):
        """When only docker-compose.yml exists, use it (production)."""
        (tmp_path / "docker-compose.yml").touch()
        assert _get_compose_file(tmp_path) == "docker-compose.yml"

    def test_dev_only_no_prod(self, tmp_path):
        """When only docker-compose.dev.yml exists, use it."""
        (tmp_path / "docker-compose.dev.yml").touch()
        assert _get_compose_file(tmp_path) == "docker-compose.dev.yml"

    def test_neither_exists(self, tmp_path):
        """When neither exists, fall back to docker-compose.yml."""
        assert _get_compose_file(tmp_path) == "docker-compose.yml"


class TestRecreateCrawler:
    """Test recreate_crawler uses the correct compose file and command."""

    @patch("tools.msauth.authenticate.time")
    @patch("tools.msauth.authenticate.subprocess.run")
    def test_uses_dev_compose_in_dev_env(self, mock_run, mock_time, tmp_path):
        """In dev environment, should use docker-compose.dev.yml."""
        (tmp_path / "docker-compose.dev.yml").touch()
        (tmp_path / "docker-compose.yml").touch()
        mock_run.return_value = MagicMock(returncode=0)

        result = recreate_crawler(deploy_dir=tmp_path)

        assert result is True
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "docker-compose.dev.yml" in cmd
        assert "docker" == cmd[0]
        assert "compose" == cmd[1]

    @patch("tools.msauth.authenticate.time")
    @patch("tools.msauth.authenticate.subprocess.run")
    def test_uses_prod_compose_in_prod_env(self, mock_run, mock_time, tmp_path):
        """In production (no dev yml), should use docker-compose.yml."""
        (tmp_path / "docker-compose.yml").touch()
        mock_run.return_value = MagicMock(returncode=0)

        result = recreate_crawler(deploy_dir=tmp_path)

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert "docker-compose.yml" in cmd
        assert "docker-compose.dev.yml" not in cmd

    @patch("tools.msauth.authenticate.subprocess.run")
    def test_nonexistent_deploy_dir_returns_false(self, mock_run, tmp_path):
        """Should return False if deploy dir doesn't exist."""
        fake_dir = tmp_path / "nonexistent"
        result = recreate_crawler(deploy_dir=fake_dir)

        assert result is False
        mock_run.assert_not_called()

    @patch("tools.msauth.authenticate.subprocess.run")
    def test_docker_failure_returns_false(self, mock_run, tmp_path):
        """Should return False if docker compose fails."""
        (tmp_path / "docker-compose.dev.yml").touch()
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        result = recreate_crawler(deploy_dir=tmp_path)

        assert result is False

    @patch("tools.msauth.authenticate.subprocess.run")
    def test_docker_not_found_returns_false(self, mock_run, tmp_path):
        """Should return False if docker is not installed."""
        (tmp_path / "docker-compose.dev.yml").touch()
        mock_run.side_effect = FileNotFoundError("docker not found")

        result = recreate_crawler(deploy_dir=tmp_path)

        assert result is False

    @patch("tools.msauth.authenticate.subprocess.run")
    def test_timeout_returns_false(self, mock_run, tmp_path):
        """Should return False on timeout."""
        (tmp_path / "docker-compose.dev.yml").touch()
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=120)

        result = recreate_crawler(deploy_dir=tmp_path)

        assert result is False

    @patch("tools.msauth.authenticate.time")
    @patch("tools.msauth.authenticate.subprocess.run")
    def test_command_uses_force_recreate(self, mock_run, mock_time, tmp_path):
        """Should pass --force-recreate and target 'crawler' service."""
        (tmp_path / "docker-compose.dev.yml").touch()
        mock_run.return_value = MagicMock(returncode=0)

        recreate_crawler(deploy_dir=tmp_path)

        cmd = mock_run.call_args[0][0]
        assert "--force-recreate" in cmd
        assert "crawler" in cmd
        assert "-d" in cmd
        assert "up" in cmd

    @patch("tools.msauth.authenticate.time")
    @patch("tools.msauth.authenticate.subprocess.run")
    def test_runs_from_deploy_dir(self, mock_run, mock_time, tmp_path):
        """Should set cwd to deploy_dir."""
        (tmp_path / "docker-compose.dev.yml").touch()
        mock_run.return_value = MagicMock(returncode=0)

        recreate_crawler(deploy_dir=tmp_path)

        assert mock_run.call_args[1]["cwd"] == str(tmp_path)


class TestRealDeployDir:
    """Validate the actual project deploy directory has correct compose files."""

    def test_dev_compose_exists_in_project(self):
        """Our project's deploy/ should have docker-compose.dev.yml."""
        deploy_dir = Path(__file__).parent.parent.parent / "deploy"
        assert (
            deploy_dir / "docker-compose.dev.yml"
        ).exists(), "deploy/docker-compose.dev.yml must exist for dev environment"

    def test_dev_compose_selected_for_project(self):
        """_get_compose_file should select dev compose for our project."""
        deploy_dir = Path(__file__).parent.parent.parent / "deploy"
        assert _get_compose_file(deploy_dir) == "docker-compose.dev.yml"

    def test_dev_compose_has_correct_crawler_mount(self):
        """dev compose should mount ../crawler (source), not ./crawler (empty)."""
        deploy_dir = Path(__file__).parent.parent.parent / "deploy"
        dev_compose = deploy_dir / "docker-compose.dev.yml"
        content = dev_compose.read_text()
        # Should reference parent dir for source code mount
        assert (
            "../crawler:/app/crawler" in content
        ), "docker-compose.dev.yml should mount ../crawler for source code"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
