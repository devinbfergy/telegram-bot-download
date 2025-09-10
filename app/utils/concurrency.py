from __future__ import annotations
import asyncio
from typing import Callable, TypeVar, Any

T = TypeVar("T")

async def run_blocking(fn: Callable[..., T], *args, **kwargs) -> T:
    return await asyncio.to_thread(fn, *args, **kwargs)
