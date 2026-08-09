# conftest.py — pytest 全局配置
#
# 此文件主要负责：
#  - 将项目根目录加入 sys.path

"""Pytest configuration helpers.

This file centralizes test-time configuration and fixtures. Currently it
performs one simple but necessary task: ensure the project root is on
``sys.path`` so test modules can import application code (for example
``from engine import TetrisEngine``) when pytest is executed from the
repository root directory.

Why do this here? Putting the sys.path modification in a single place
(``conftest.py``) is preferred to duplicating the same logic at the top
of each test file. Tests remain cleaner and any future global test
fixtures or environment setup can be added here.

Notes:
 - This change is intended for local development and test runs. In CI
   environments you may prefer to install the package in editable mode
   (``pip install -e .``) so imports work without modifying sys.path.
 - If you later convert the project to a proper package (with a
   package name in pyproject.toml), this shim can be removed.

Usage:
 - Run tests from the repository root:
     pytest -q
 - If you see import errors in CI but not locally, prefer installing the
   package in the CI job rather than relying on this runtime shim.
"""

import os
import sys

# 代码位于 src/ 目录：把 src 加进 sys.path（优先于其他路径），
# 使测试中的 `from engine import ...` 等导入在项目的 src 下解析。
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")

# Insert at front so tests import the workspace copy of the package first.
if SRC not in sys.path:
    sys.path.insert(0, SRC)

