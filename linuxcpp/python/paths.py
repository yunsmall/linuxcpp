"""构建脚本共用的目录布局。"""

from pathlib import Path

PY_DIR = Path(__file__).resolve().parent
LIB_DIR = PY_DIR.parent
INCLUDE_DIR = LIB_DIR / "include"
SRC_DIR = LIB_DIR / "src"
