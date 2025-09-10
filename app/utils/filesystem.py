from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import shutil, tempfile

@contextmanager
def temp_workspace(prefix: str = "work_"):
    path = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)

def safe_unlink(p: Path):
    try:
        p.unlink(missing_ok=True)  # type: ignore[arg-type]
    except Exception:
        pass
