from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile

@contextmanager
def temp_workspace(prefix: str = "work_"):
    path = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)

def create_temp_dir(prefix: str = "work_") -> Path:
    """Creates a temporary directory and returns its Path."""
    return Path(tempfile.mkdtemp(prefix=prefix))

def safe_cleanup(path: Path) -> None:
    """Safely removes files or directories, handling missing files gracefully."""
    try:
        if path.is_file():
            path.unlink(missing_ok=True)  # type: ignore[arg-type]
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass

def safe_unlink(p: Path):
    try:
        p.unlink(missing_ok=True)  # type: ignore[arg-type]
    except Exception:
        pass
