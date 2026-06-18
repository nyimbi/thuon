# app_entry.py
"""
Frozen entry point for the macOS .app bundle.

PyInstaller calls this script; it is never invoked directly in development
(use `uv run python main.py desktop` instead).

Steps:
  1. Ensure _MEIPASS is in sys.path so package imports resolve
  2. Seed user data dir on first launch (config, company templates, etc.)
  3. Hand off to the desktop app runner
"""
import sys
import os

if getattr(sys, 'frozen', False):
    _meipass = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    if _meipass not in sys.path:
        sys.path.insert(0, _meipass)

from core.bundle import ensure_first_run
ensure_first_run()

from interfaces.desktop_app import run_desktop_app
run_desktop_app()
