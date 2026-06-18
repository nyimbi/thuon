# core/login_item.py
"""
macOS login item management via LaunchAgent plist.
Only functional when running as a bundled .app — no-ops in dev.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PLIST_ID   = 'com.thuon.app'
_PLIST_PATH = Path.home() / 'Library' / 'LaunchAgents' / f'{_PLIST_ID}.plist'
_APP_PATH   = '/Applications/Thuon.app/Contents/MacOS/Thuon'

_PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{executable}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{log_dir}/thuon-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/thuon-stderr.log</string>
</dict>
</plist>
"""


def _is_bundle() -> bool:
    return getattr(sys, 'frozen', False)


def _executable() -> str:
    if _is_bundle():
        return sys.executable
    return _APP_PATH


def is_enabled() -> bool:
    return _PLIST_PATH.exists()


def enable() -> None:
    if not _is_bundle():
        return
    log_dir = Path.home() / 'Library' / 'Logs' / 'Thuon'
    log_dir.mkdir(parents=True, exist_ok=True)
    plist = _PLIST_TEMPLATE.format(
        label=_PLIST_ID,
        executable=_executable(),
        log_dir=log_dir,
    )
    _PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PLIST_PATH.write_text(plist, encoding='utf-8')
    subprocess.run(
        ['launchctl', 'load', '-w', str(_PLIST_PATH)],
        capture_output=True,
    )


def disable() -> None:
    if not _is_bundle():
        return
    if _PLIST_PATH.exists():
        subprocess.run(
            ['launchctl', 'unload', '-w', str(_PLIST_PATH)],
            capture_output=True,
        )
        _PLIST_PATH.unlink(missing_ok=True)


def toggle() -> bool:
    """Toggle login item. Returns True if now enabled."""
    if is_enabled():
        disable()
        return False
    else:
        enable()
        return True
