"""Integration tests for Docker container."""

from pathlib import Path

import pytest

try:
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.image import DockerImage

    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False
    DockerContainer = None  # type: ignore[assignment,misc]
    DockerImage = None  # type: ignore[assignment,misc]


def docker_available() -> bool:
    """Check if Docker is available."""
    if not TESTCONTAINERS_AVAILABLE:
        return False
    if not Path("/var/run/docker.sock").exists():
        return False
    return True


@pytest.fixture(scope="module")
def dockerfile_path():
    """Get the path to the Dockerfile."""
    return Path(__file__).parent.parent.parent / "Dockerfile"


@pytest.fixture(scope="module")
def project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def built_image(project_root):
    """Build the Docker image once for all tests that need it."""
    if not docker_available():
        pytest.skip("Docker not available")

    image = DockerImage(
        path=str(project_root),
        tag="telegram-bot-test:latest",
        clean_up=True,
    )
    image.build()
    yield str(image)
    image.remove()


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


@pytest.mark.skipif(not docker_available(), reason="Docker not available")
def test_docker_image_builds(built_image):
    """Test that Docker image builds successfully."""
    assert built_image is not None
    assert "telegram-bot-test" in built_image


@pytest.mark.skipif(not docker_available(), reason="Docker not available")
def test_docker_container_has_python(built_image):
    """Test that the Docker container has Python 3.12 installed."""
    container = DockerContainer(built_image).with_command("sleep infinity")
    container.start()
    try:
        result = container.exec("python --version")
        assert result.exit_code == 0
        assert "Python 3.12" in result.output.decode("utf-8")
    finally:
        container.stop()


@pytest.mark.skipif(not docker_available(), reason="Docker not available")
def test_docker_container_has_ffmpeg(built_image):
    """Test that the Docker container has FFmpeg installed."""
    container = DockerContainer(built_image).with_command("sleep infinity")
    container.start()
    try:
        result = container.exec("ffmpeg -version")
        assert result.exit_code == 0
        assert "ffmpeg version" in result.output.decode("utf-8").lower()
    finally:
        container.stop()


@pytest.mark.skipif(not docker_available(), reason="Docker not available")
def test_docker_container_has_uv(built_image):
    """Test that the Docker container has uv installed."""
    container = DockerContainer(built_image).with_command("sleep infinity")
    container.start()
    try:
        result = container.exec("uv --version")
        assert result.exit_code == 0
        assert "uv" in result.output.decode("utf-8").lower()
    finally:
        container.stop()


@pytest.mark.skipif(not docker_available(), reason="Docker not available")
def test_docker_container_has_app_code(built_image):
    """Test that the Docker container has the app code."""
    container = DockerContainer(built_image).with_command("sleep infinity")
    container.start()
    try:
        result = container.exec("ls -la /app/")
        assert result.exit_code == 0
        output_str = result.output.decode("utf-8")
        assert "main.py" in output_str
        assert "app" in output_str
    finally:
        container.stop()


def test_dockerfile_workdir_is_app(dockerfile_path):
    """Test that Dockerfile sets WORKDIR to /app."""
    content = dockerfile_path.read_text()
    assert "WORKDIR /app" in content


def test_dockerfile_uses_uv_sync(dockerfile_path):
    """Test that Dockerfile uses uv sync to install dependencies."""
    content = dockerfile_path.read_text()
    assert "uv sync" in content
