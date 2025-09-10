from __future__ import annotations
import os, asyncio
from app.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

try:  # optional dependency
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None  # type: ignore

_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

async def ai_truth_check(text: str) -> str:  # noqa: D401
    if not settings.GEMINI_API_KEY or not settings.AI_TRUTH_CHECK_ENABLED:
        return ""
    if genai is None:
        log.debug("ai.gemini_unavailable")
        return ""
    try:
        def _run():
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel(_MODEL_NAME)
            prompt = ("Provide a concise (<=25 words) factuality note: if obvious misinformation or unverifiable claim, say 'Potentially unreliable', else 'No major issues'. Text: " + text[:1000])
            resp = model.generate_content(prompt)
            return getattr(resp, 'text', '').strip()[:120]
        result = await asyncio.to_thread(_run)
        if result:
            return f"\nAI note: {result}"
    except Exception:  # noqa: BLE001
        log.debug("ai.truth_check_fail")
    return ""