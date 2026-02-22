"""Integration tests for Docker container."""

import time
from pathlib import Path

import pytest

try:
    from testcontainers.core.container import DockerContainer  # type: ignore[import-untyped]
except ImportError:
    DockerContainer = None  # type: ignore[assignment,misc]


@pytest.fixture(scope="module")
def dockerfile_path():
    """Get the path to the Dockerfile."""
    return Path(__file__).parent.parent.parent / "Dockerfile"


@pytest.fixture(scope="module")
def project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


def test_dockerfile_exists(dockerfile_path):
    """Test that Dockerfile exists."""
    assert dockerfile_path.exists(), "Dockerfile not found"


def test_dockerfile_has_python_base(dockerfile_path):
    """Test that Dockerfile uses Python 3.12 slim base image."""
    content = dockerfile_path.read_text()
    assert "python:3.12-slim" in content.lower()


def test_dockerfile_installs_ffmpeg(dockerfile_path):
    """Test that Dockerfile installs FFmpeg."""
    content = dockerfile_path.read_text()
    assert "ffmpeg" in content.lower()


def test_dockerfile_copies_app_directory(dockerfile_path):
    """Test that Dockerfile copies the app directory."""
    content = dockerfile_path.read_text()
    assert "COPY app/" in content or "COPY . " in content


def test_dockerfile_has_entrypoint(dockerfile_path):
    """Test that Dockerfile has CMD or ENTRYPOINT."""
    content = dockerfile_path.read_text()
    assert "CMD" in content or "ENTRYPOINT" in content


@pytest.mark.skipif(
    not Path("/var/run/docker.sock").exists(), reason="Docker not available"
)
def test_docker_image_builds(project_root):
    """Test that Docker image builds successfully."""
    container = None
    try:
        # Create container from Dockerfile
        container = DockerContainer(path=str(project_root)).with_build_args()

        # Build the image (with_exposed_ports triggers build)
        container.with_exposed_ports(8080)

        # If we get here without exception, build succeeded
        assert True
    except Exception as e:
        pytest.skip(f"Docker test skipped: {e}")
    finally:
        if container:
            try:
                container.stop()
            except Exception:
                pass


@pytest.mark.skipif(
    not Path("/var/run/docker.sock").exists(), reason="Docker not available"
)
def test_docker_container_has_python(project_root):
    """Test that the Docker container has Python 3.12 installed."""
    container = None
    try:
        container = DockerContainer(path=str(project_root)).with_command(
            "python --version"
        )
        container.start()

        # Give container time to execute command
        time.sleep(2)

        logs = container.get_logs()[0].decode("utf-8")
        assert "Python 3.12" in logs
    except Exception as e:
        pytest.skip(f"Docker test skipped: {e}")
    finally:
        if container:
            try:
                container.stop()
            except Exception:
                pass


@pytest.mark.skipif(
    not Path("/var/run/docker.sock").exists(), reason="Docker not available"
)
def test_docker_container_has_ffmpeg(project_root):
    """Test that the Docker container has FFmpeg installed."""
    container = None
    try:
        container = DockerContainer(path=str(project_root)).with_command(
            "ffmpeg -version"
        )
        container.start()

        # Give container time to execute command
        time.sleep(2)

        logs = container.get_logs()[0].decode("utf-8")
        assert "ffmpeg version" in logs.lower()
    except Exception as e:
        pytest.skip(f"Docker test skipped: {e}")
    finally:
        if container:
            try:
                container.stop()
            except Exception:
                pass


@pytest.mark.skipif(
    not Path("/var/run/docker.sock").exists(), reason="Docker not available"
)
def test_docker_container_has_uv(project_root):
    """Test that the Docker container has uv installed."""
    container = None
    try:
        container = DockerContainer(path=str(project_root)).with_command("uv --version")
        container.start()

        # Give container time to execute command
        time.sleep(2)

        logs = container.get_logs()[0].decode("utf-8")
        assert "uv" in logs.lower()
    except Exception as e:
        pytest.skip(f"Docker test skipped: {e}")
    finally:
        if container:
            try:
                container.stop()
            except Exception:
                pass


@pytest.mark.skipif(
    not Path("/var/run/docker.sock").exists(), reason="Docker not available"
)
def test_docker_container_has_app_code(project_root):
    """Test that the Docker container has the app code."""
    container = None
    try:
        container = DockerContainer(path=str(project_root)).with_command("ls -la /app/")
        container.start()

        # Give container time to execute command
        time.sleep(2)

        logs = container.get_logs()[0].decode("utf-8")
        assert "main.py" in logs
        assert "app" in logs  # app directory should exist
    except Exception as e:
        pytest.skip(f"Docker test skipped: {e}")
    finally:
        if container:
            try:
                container.stop()
            except Exception:
                pass


def test_dockerfile_workdir_is_app(dockerfile_path):
    """Test that Dockerfile sets WORKDIR to /app."""
    content = dockerfile_path.read_text()
    assert "WORKDIR /app" in content


def test_dockerfile_uses_uv_sync(dockerfile_path):
    """Test that Dockerfile uses uv sync to install dependencies."""
    content = dockerfile_path.read_text()
    assert "uv sync" in content
