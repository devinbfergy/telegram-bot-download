#!/usr/bin/env python3
"""Deprecated. Use scripts/instagram_session/refresh_session.py instead."""

import sys

print(
    "get_instagram_cookie.py is deprecated.\n"
    "Run this instead (elevated PowerShell on Windows):\n"
    "  uv run scripts/instagram_session/refresh_session.py\n"
    "To schedule it:\n"
    "  .\\scripts\\instagram_session\\register_task.ps1",
    file=sys.stderr,
)
sys.exit(1)
