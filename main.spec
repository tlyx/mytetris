# -*- mode: python ; coding: utf-8 -*-
import os

# ---------- 创建本地化资源文件 ----------
LOCALES_DIR = "locales"
os.makedirs(LOCALES_DIR, exist_ok=True)

EN_LPROJ = os.path.join(LOCALES_DIR, "en.lproj")
ZH_LPROJ = os.path.join(LOCALES_DIR, "zh_CN.lproj")
os.makedirs(EN_LPROJ, exist_ok=True)
os.makedirs(ZH_LPROJ, exist_ok=True)

# en.lproj/InfoPlist.strings
with open(os.path.join(EN_LPROJ, "InfoPlist.strings"), "w", encoding="utf-8") as f:
    f.write('CFBundleDisplayName = "Tetris";\n')

# zh_CN.lproj/InfoPlist.strings
with open(os.path.join(ZH_LPROJ, "InfoPlist.strings"), "w", encoding="utf-8") as f:
    f.write('CFBundleDisplayName = "俄罗斯方块";\n')
# ----------------------------------------

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'Resources/assets'),
        # 将整个 .lproj 目录添加到打包文件系统中的 Resources 目录下
        ('locales/en.lproj', 'Resources/en.lproj'),
        ('locales/zh_CN.lproj', 'Resources/zh_CN.lproj'),
    ],
    hiddenimports=[
        'pygame._sdl2.audio',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Tetris',
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
    onedir=True,            # 使用 onedir 模式，完全避免 onefile 警告
)
app = BUNDLE(
    exe,
    name='Tetris.app',
    icon='assets/logo.png',
    bundle_identifier='org.tlyx.tetris',
    info_plist={
        'CFBundleShortVersionString': '0.8.2',
        'CFBundleVersion': '0.8.2',
        'NSHighResolutionCapable': True,
        'CFBundleDevelopmentRegion': 'en',
        'CFBundleLocalizations': ['en', 'zh_CN'],
        'CFBundleDisplayName': 'Tetris',
    },
)
