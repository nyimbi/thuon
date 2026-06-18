.PHONY: build dmg install uninstall login-enable login-disable clean dev test

APP     = Thuon
BUNDLE  = dist/$(APP).app
DMG     = dist/$(APP).dmg
SPEC    = thuon.spec
LAUNCHAGENT = $(HOME)/Library/LaunchAgents/com.thuon.app.plist

# ── Development ───────────────────────────────────────────────────────────────

dev:
	cd thuon_platform && uv run python main.py desktop

test:
	cd thuon_platform && uv run pytest tests/ci -q

# ── Build ─────────────────────────────────────────────────────────────────────

build:
	uv run pyinstaller --clean --noconfirm $(SPEC)
	@echo "Built: $(BUNDLE)"

dmg: build
	@rm -f $(DMG)
	hdiutil create \
	  -volname "$(APP)" \
	  -srcfolder "$(BUNDLE)" \
	  -ov \
	  -format UDZO \
	  "$(DMG)"
	@echo "DMG ready: $(DMG)"

# ── Installation ──────────────────────────────────────────────────────────────

install: build
	@if [ -d "/Applications/$(APP).app" ]; then \
	  echo "Removing existing installation…"; \
	  rm -rf "/Applications/$(APP).app"; \
	fi
	cp -R "$(BUNDLE)" /Applications/
	@echo "Installed: /Applications/$(APP).app"

uninstall:
	@$(MAKE) login-disable 2>/dev/null || true
	rm -rf "/Applications/$(APP).app"
	@echo "Removed /Applications/$(APP).app"

# ── Login item (LaunchAgent) ──────────────────────────────────────────────────

login-enable:
	@if [ ! -f "/Applications/$(APP).app/Contents/MacOS/$(APP)" ]; then \
	  echo "ERROR: /Applications/$(APP).app not found — run 'make install' first"; \
	  exit 1; \
	fi
	@mkdir -p "$(dir $(LAUNCHAGENT))"
	@printf '<?xml version="1.0" encoding="UTF-8"?>\n\
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"\n\
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n\
<plist version="1.0">\n\
<dict>\n\
    <key>Label</key>\n\
    <string>com.thuon.app</string>\n\
    <key>ProgramArguments</key>\n\
    <array>\n\
        <string>/Applications/$(APP).app/Contents/MacOS/$(APP)</string>\n\
    </array>\n\
    <key>RunAtLoad</key>\n\
    <true/>\n\
    <key>KeepAlive</key>\n\
    <false/>\n\
</dict>\n\
</plist>\n' > "$(LAUNCHAGENT)"
	launchctl load -w "$(LAUNCHAGENT)"
	@echo "Login item enabled — Thuon will start at login"

login-disable:
	@if [ -f "$(LAUNCHAGENT)" ]; then \
	  launchctl unload -w "$(LAUNCHAGENT)" 2>/dev/null || true; \
	  rm -f "$(LAUNCHAGENT)"; \
	  echo "Login item disabled"; \
	else \
	  echo "Login item not installed"; \
	fi

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	rm -rf build/ dist/ thuon_platform/__pycache__
	find thuon_platform -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned"
