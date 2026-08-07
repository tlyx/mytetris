# utils.py — 通用工具函数
#
# 此文件主要负责：
#  - resource_path：兼容 PyInstaller 打包的资源路径解析

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(relative_path: str) -> str:
    """获取资源文件的绝对路径，同时兼容 PyInstaller 打包后的路径。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(base / relative_path)
