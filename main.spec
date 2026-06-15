# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Specification File for Tetris Professional (macOS Application)
Architecture: macOS Standard Bundle (onedir mode for compliant sandboxing)

This configuration handles the multi-layered bundle structure required by macOS,
ensuring clean separation between application-level assets and system-level localizations.
"""

import os
import subprocess

# =========================================================================
# 0. DYNAMIC GIT VERSIONING ENGINE (Git 动态版本注入与代码生成)
# =========================================================================
def get_git_version(base_version="0.8.5"):
    try:
        # 获取当前提交的 7 位短哈希 (例如: f918cde)
        short_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], 
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        return f"{base_version}-{short_sha}"
    except Exception:
        return base_version

# 执行版本捕获
APP_VERSION = get_git_version("0.8.5")
print(f"📦 [BUILD LOG] Successfully fetched Dynamic Git Version: {APP_VERSION}")

# 将生成的动态版本号写入 build 缓存目录，避免污染项目根目录
BUILD_DIR = "build"
os.makedirs(BUILD_DIR, exist_ok=True)
VERSION_FILE = os.path.join(BUILD_DIR, "_version.py")

with open(VERSION_FILE, "w", encoding="utf-8") as f:
    f.write(f'__version__ = "{APP_VERSION}"\n')


# =========================================================================
# 1. LOCALIZATION PREPARATION LAYER (构建本地化缓存层)
# =========================================================================
# 将临时资源目录定向至 build 缓存目录，避免污染项目根目录及 Git 工作树。
LOCALES_DIR = os.path.join(BUILD_DIR, "locales")
os.makedirs(LOCALES_DIR, exist_ok=True)

EN_LPROJ = os.path.join(LOCALES_DIR, "en.lproj")
ZH_LPROJ = os.path.join(LOCALES_DIR, "zh_CN.lproj")
os.makedirs(EN_LPROJ, exist_ok=True)
os.makedirs(ZH_LPROJ, exist_ok=True)

# 动态生成符合 CoreFoundation 规范的本地化字符串文件
with open(os.path.join(EN_LPROJ, "InfoPlist.strings"), "w", encoding="utf-8") as f:
    f.write('CFBundleDisplayName = "Tetris";\n')

with open(os.path.join(ZH_LPROJ, "InfoPlist.strings"), "w", encoding="utf-8") as f:
    f.write('CFBundleDisplayName = "俄罗斯方块";\n')


# =========================================================================
# 2. ANALYSIS LAYER (静态代码与依赖分析层)
# =========================================================================
a = Analysis(
    ['main.py'],
    pathex=[BUILD_DIR],      # 🎯 将 build 目录加入搜索路径，让 PyInstaller 顺利打包 _version.py
    binaries=[],
    datas=[
        # 全部直接释放到 .app/Contents/Resources/ 正下方
        ('assets', 'assets'),
        (EN_LPROJ, 'en.lproj'),
        (ZH_LPROJ, 'zh_CN.lproj'),
    ],
    hiddenimports=[
        'pygame._sdl2.audio',  # 显式引入 Pygame 社区版音频驱动的底层依赖
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)


# =========================================================================
# 3. EXECUTABLE LAYER (二进制生成层)
# =========================================================================
# 使用 exclude_binaries=True 强制解绑单文件压缩模式，
# 从而彻底杜绝 macOS 7957 安全规范下的 Deprecation 警告。
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name='Tetris',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # 隐藏终端黑窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)


# =========================================================================
# 4. APPLICATION BUNDLE LAYER (苹果沙盒应用封装层)
# =========================================================================
# 在此处完成二进制、依赖库和多层级资源向标准的 Tetris.app/ 目录的组装。
app = BUNDLE(
    exe,
    a.binaries,
    a.datas,
    name='Tetris.app',
    icon='assets/logo.png',
    bundle_identifier='org.tlyx.tetris',
    info_plist={
        'CFBundleShortVersionString': APP_VERSION,  # 🎯 动态同步系统显示版本号
        'CFBundleVersion': APP_VERSION,             # 🎯 动态同步内部构建版本号
        'NSHighResolutionCapable': True,            # 显式声明启用 Retina 高分辨率自适应支持
        'CFBundleDevelopmentRegion': 'en',
        'CFBundleLocalizations': ['en', 'zh_CN'],
        'CFBundleDisplayName': 'Tetris',
    },
)
