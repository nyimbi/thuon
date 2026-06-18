# interfaces/desktop_app.py
"""
macOS menu-bar app for Thuon.

Architecture:
  • Flask serves the web UI in a daemon thread (port 5099)
  • pywebview runs the WKWebView + Cocoa event loop on the main thread
  • NSStatusBar icon is created via PyObjC inside pywebview's `started` callback,
    sharing the same Cocoa run loop — no second NSApplication needed
  • Click the status bar icon to toggle the panel; the menu provides quick nav

Form factor mirrors Claude Desktop / Perplexity Mac:
  • No Dock icon (NSApplicationActivationPolicyAccessory)
  • Floating window, always on top
  • Icon: "T" text badge (set _ICON_PATH to a .png once you have one)

Usage:
  uv run python main.py desktop
"""

from __future__ import annotations

import logging
import sys
import threading
import time
import urllib.request

logger = logging.getLogger('thuon.desktop')

_PORT       = 5099
_URL        = f'http://localhost:{_PORT}'
_WIN_W      = 1040
_WIN_H      = 740
_ICON_PATH  = None   # set to '/path/to/icon.png' to use a real icon


# ── helpers ───────────────────────────────────────────────────────────────────

def _wait_for_server(timeout: float = 20.0) -> bool:
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		try:
			urllib.request.urlopen(f'{_URL}/health', timeout=1)
			return True
		except Exception:
			time.sleep(0.25)
	return False


def _start_flask() -> None:
	from interfaces.web_app import run_app
	run_app(port=_PORT, debug=False)


# ── NSStatusBar controller ────────────────────────────────────────────────────

def _setup_statusbar(win) -> tuple:
	"""
	Create the menu-bar icon and wire it to the webview window.
	Must be called from the main thread (inside pywebview's started callback).
	Returns (status_item, handler) — caller must keep these alive to prevent GC.
	"""
	from AppKit import (
		NSApp,
		NSApplicationActivationPolicyAccessory,
		NSImage,
		NSMenu,
		NSMenuItem,
		NSStatusBar,
		NSVariableStatusItemLength,
	)
	from Foundation import NSObject
	import objc

	# Hide from Dock and Cmd-Tab switcher — pure menubar accessory
	NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

	class _MenuHandler(NSObject):
		def initWithWindow_(self, window):
			self = objc.super(_MenuHandler, self).init()
			if self is None:
				return None
			self._win     = window
			self._visible = True
			return self

		def toggleWindow_(self, sender):
			if self._visible:
				self._win.hide()
			else:
				self._win.show()
			self._visible = not self._visible

		def openHome_(self, sender):
			self._win.load_url(_URL)
			self._ensure_visible()

		def openRFPs_(self, sender):
			self._win.load_url(f'{_URL}/rfps')
			self._ensure_visible()

		def openContent_(self, sender):
			self._win.load_url(f'{_URL}/content')
			self._ensure_visible()

		def openCompanyKB_(self, sender):
			self._win.load_url(f'{_URL}/settings/company')
			self._ensure_visible()

		def toggleLoginItem_(self, sender):
			from core.login_item import toggle as _toggle
			_toggle()

		def quitApp_(self, sender):
			sys.exit(0)

		def _ensure_visible(self):
			if not self._visible:
				self._win.show()
				self._visible = True

	handler = _MenuHandler.alloc().initWithWindow_(win)

	status_bar  = NSStatusBar.systemStatusBar()
	status_item = status_bar.statusItemWithLength_(NSVariableStatusItemLength)

	# Icon: file or text badge fallback
	if _ICON_PATH:
		try:
			img = NSImage.alloc().initWithContentsOfFile_(_ICON_PATH)
			if img:
				img.setSize_((18, 18))
				status_item.button().setImage_(img)
		except Exception:
			pass
	if not (_ICON_PATH and status_item.button().image()):
		status_item.button().setTitle_(' T ')

	menu = NSMenu.alloc().initWithTitle_('Thuon')

	def _item(title: str, sel: str, key: str = '') -> None:
		mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, sel, key)
		mi.setTarget_(handler)
		menu.addItem_(mi)

	_item('Toggle Thuon',  'toggleWindow:', '')
	menu.addItem_(NSMenuItem.separatorItem())
	_item('Home',          'openHome:',        '')
	_item('RFPs',          'openRFPs:',        '')
	_item('Content',       'openContent:',     '')
	_item('Company KB',    'openCompanyKB:',   '')
	menu.addItem_(NSMenuItem.separatorItem())
	from core.login_item import is_enabled as _li_enabled
	_login_label = '✓ Open at Login' if _li_enabled() else '  Open at Login'
	_item(_login_label,    'toggleLoginItem:', '')
	menu.addItem_(NSMenuItem.separatorItem())
	_item('Quit Thuon',    'quitApp:',         'q')

	status_item.setMenu_(menu)
	return status_item, handler


# ── entry point ───────────────────────────────────────────────────────────────

def run_desktop_app() -> None:
	if sys.platform != 'darwin':
		_fallback_web()
		return

	try:
		import webview
	except ImportError:
		print('pywebview not installed.  Run: uv add pywebview')
		sys.exit(1)

	# 1. Flask in background daemon thread
	threading.Thread(target=_start_flask, daemon=True, name='thuon-flask').start()

	print('Waiting for Thuon server…', flush=True)
	if not _wait_for_server():
		print(f'ERROR: Thuon server did not respond on port {_PORT}')
		sys.exit(1)
	print('Server ready.', flush=True)

	# 2. WebView window — shown immediately on first launch
	win = webview.create_window(
		'Thuon',
		_URL,
		width           = _WIN_W,
		height          = _WIN_H,
		on_top          = True,
		hidden          = False,
		frameless       = False,
		shadow          = True,
		min_size        = (640, 480),
		background_color= '#0d0d0d',   # match Thuon dark theme; prevents flash of white
	)

	# 3. started callback — pywebview calls this from a *background* thread,
	#    so AppKit/NSStatusBar work must be dispatched back to the main thread.
	_refs: list = []   # keep PyObjC objects alive for app lifetime

	def _on_started():
		from Foundation import NSObject
		import objc

		class _MainDispatch(NSObject):
			"""Trampoline: schedules _setup_statusbar on the main run-loop."""
			def runSetup_(self, _):
				try:
					refs = _setup_statusbar(win)
					_refs.extend(refs)
				except Exception as exc:
					logger.warning('Status bar setup failed: %s', exc)

		trampoline = _MainDispatch.alloc().init()
		trampoline.performSelectorOnMainThread_withObject_waitUntilDone_(
			'runSetup:', None, False
		)

	# 4. Cocoa event loop — blocks until quit
	webview.start(_on_started, debug=False)


def _fallback_web() -> None:
	"""Non-macOS: start server and open in the default browser."""
	import webbrowser
	threading.Thread(target=_start_flask, daemon=True).start()
	if _wait_for_server():
		webbrowser.open(_URL)
	try:
		while True:
			time.sleep(60)
	except KeyboardInterrupt:
		pass
