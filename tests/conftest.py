# conftest.py — pytest 全局配置
#
# 此文件主要负责：
#  - 将 src/ 加入 sys.path，使测试中的 `from engine import ...` 等导入
#    在项目 src 目录下解析（src-layout，无 sys.path bootstrap 补丁）

import os
import sys

# 代码位于 src/ 目录：把 src 加进 sys.path（优先于其他路径），
# 使测试中的 `from engine import ...` 等导入在项目的 src 下解析。
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")

# Insert at front so tests import the workspace copy of the package first.
if SRC not in sys.path:
    sys.path.insert(0, SRC)
