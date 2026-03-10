# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ctk_datas  = collect_data_files('customtkinter', include_py_files=False)
ctk_hidden = collect_submodules('customtkinter')
dnd_datas  = collect_data_files('tkinterdnd2')
dnd_hidden = collect_submodules('tkinterdnd2')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=ctk_datas + dnd_datas,
    hiddenimports=['customtkinter', 'PIL', 'tkinterdnd2'] + ctk_hidden + dnd_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='GorselDonusturucu',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
