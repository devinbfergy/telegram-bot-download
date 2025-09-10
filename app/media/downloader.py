from __future__ import annotations
from pathlib import Path
from typing import List, Callable, Any
import subprocess, json, shutil
from app.utils.concurrency import run_blocking
from app.media import ytdlp_profiles
from app.core.types import DownloadResult, MediaKind
from app.core.exceptions import ExtractionFailed

Strategy = Callable[[], dict]

def _run_ytdlp(url: str, workdir: Path, opts: dict) -> dict:
    cmd = ["yt-dlp", "-J", url]
    for k, v in opts.items():
        if isinstance(v, bool):
            if v: cmd.append(f"--{k}")
        elif isinstance(v, (int, float, str)):
            cmd.extend([f"--{k.replace('_','-')}", str(v)])
        # complex keys (postprocessors etc.) skipped for metadata stage
    try:
        meta_raw = subprocess.check_output(cmd, cwd=workdir, stderr=subprocess.STDOUT, timeout=300)
    except subprocess.CalledProcessError as e:
        raise ExtractionFailed(e.output.decode(errors="ignore")) from e
    meta = json.loads(meta_raw)
    # Actual download pass
    out_tmpl = workdir / "%(title).80s.%(ext)s"
    dl_cmd = ["yt-dlp", "-o", str(out_tmpl)]
    for k, v in opts.items():
        if isinstance(v, bool):
            if v: dl_cmd.append(f"--{k}")
        elif isinstance(v, (int, float, str)):
            dl_cmd.extend([f"--{k.replace('_','-')}", str(v)])
        elif k == "postprocessors":
            # rely on yt-dlp config by passing through JSON via temp file? simplified: ignore here
            pass
    dl_cmd.append(url)
    subprocess.check_call(dl_cmd, cwd=workdir)
    return meta

async def download_url(url: str, workdir: Path) -> DownloadResult:
    strategies: list[tuple[str, Strategy]] = [
        ("video_best", ytdlp_profiles.video_best_profile),
        ("lightweight", ytdlp_profiles.lightweight_profile),
    ]
    last_error: Exception | None = None
    for name, builder in strategies:
        try:
            meta = await run_blocking(_run_ytdlp, url, workdir, builder())
            files = sorted(workdir.glob('*'))
            media_kind = MediaKind.VIDEO if any(f.suffix.lower() in {'.mp4','.mkv','.webm','.mov'} for f in files) else MediaKind.OTHER
            return DownloadResult(
                source_url=url,
                kind=media_kind,
                files=files,
                title=meta.get('title'),
                duration=meta.get('duration'),
                width=meta.get('width'),
                height=meta.get('height'),
            )
        except Exception as e:  # noqa: BLE001
            last_error = e
    raise ExtractionFailed(str(last_error) if last_error else "Unknown download failure")
