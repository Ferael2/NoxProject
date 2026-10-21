# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_all

datas = [
    ('icono.png', '.'),
    ('icono.ico', '.'),
    ('openrouter.key.ejemplo', '.'),
    ('config_local.json.ejemplo', '.'),
]
binaries = []
hiddenimports = [
    'PIL._tkinter_finder',
    'sounddevice',
    'bs4',
    'requests',
    'numpy',
    'pathvalidate',
    'ddgs',
]

datas += collect_data_files('customtkinter')

for pkg in ('piper', 'faster_whisper', 'ctranslate2', 'onnxruntime'):
    try:
        tmp = collect_all(pkg)
        datas += tmp[0]
        binaries += tmp[1]
        hiddenimports += tmp[2]
    except Exception as e:
        print(f"Aviso al recolectar {pkg}: {e}")

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'torch', 'torchaudio', 'torchvision'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Nox',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icono.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Nox',
)
