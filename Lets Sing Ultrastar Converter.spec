# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['LetsSingUltrastarConverter.py'],
    pathex=[],
    binaries=[],
    datas=[('config_default.yml', '.'), ('Guide.md', '.'), ('data/repository/data.db', 'data/repository'), ('assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tensorflow', 'crepe', 'librosa', 'soundfile', 'numpy', 'PySide6.QtWebEngineWidgets', 'PySide6.Qt3DCore', 'PySide6.QtMultimedia', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtNetwork', 'PySide6.QtOpenGL', 'PySide6.QtBluetooth', 'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtXml'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Lets Sing Ultrastar Converter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\logo.ico'],
)
