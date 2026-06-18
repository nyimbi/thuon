# thuon.spec — PyInstaller build spec for Thuon.app
#
# Build:  uv run pyinstaller --clean --noconfirm thuon.spec
# Or:     make build
#
# The entry script is thuon_platform/app_entry.py.
# pathex includes thuon_platform/ so imports like `from core.bundle import …`
# resolve without the thuon_platform. prefix.

block_cipher = None

a = Analysis(
    ['thuon_platform/app_entry.py'],
    pathex=['thuon_platform'],
    binaries=[],
    datas=[
        # Web UI assets
        ('thuon_platform/interfaces/templates', 'interfaces/templates'),
        ('thuon_platform/interfaces/static',    'interfaces/static'),
        # Skills directory
        ('thuon_platform/skills',               'skills'),
        # Pipeline definitions (read-only)
        ('thuon_platform/data/pipelines',       'data/pipelines'),
        # Company KB seed templates
        ('thuon_platform/data/company',         'data/company'),
        # Default config
        ('thuon_platform/config',               'config'),
    ],
    hiddenimports=[
        # PyObjC — not auto-discovered by PyInstaller
        'AppKit',
        'Foundation',
        'objc',
        'Cocoa',
        # pywebview
        'webview',
        'webview.platforms.cocoa',
        # Flask + Jinja2
        'flask',
        'jinja2',
        'jinja2.ext',
        'markupsafe',
        'werkzeug',
        'werkzeug.serving',
        # YAML
        'yaml',
        # UUID
        'uuid6',
        # SQLite / stdlib
        'sqlite3',
        # Thuon capabilities — import paths are dynamic via registry
        'capabilities',
        'core',
        'interfaces',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'IPython',
        'jupyter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    collect_submodules=[
        'capabilities',
        'core',
        'interfaces',
    ],
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Thuon',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Thuon',
)

app = BUNDLE(
    coll,
    name='Thuon.app',
    icon=None,          # replace with 'assets/icon.icns' once designed
    bundle_identifier='com.thuon.app',
    info_plist={
        # Hide from Dock — pure menu-bar app
        'LSUIElement': True,
        # Retina-ready
        'NSHighResolutionCapable': True,
        # Version
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        # App category (for Spotlight / App Store if ever needed)
        'LSApplicationCategoryType': 'public.app-category.productivity',
        # Disallow quarantine warning from blocking localhost fetch
        'NSAppTransportSecurity': {
            'NSAllowsLocalNetworking': True,
        },
    },
)
