# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['app/run.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app/src/templates', 'src/templates'),
        ('app/static', 'static'),
        ('app/.env.example', '.'),
    ],
    hiddenimports=[
        'jinja2.ext',
        'gallery_dl.extractor.pixiv',
        'gallery_dl.postprocessor.ugoira',
        'PIL',
        'PIL.Image',
    ],
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
    name='PixivTracker_v0.0.2',
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
    icon=None,
)
