"""libc_port 的静态头和按内核生成的头能被 C 编译器使用。"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY_DIR = ROOT / "linuxcpp" / "python"
INCLUDE = ROOT / "linuxcpp" / "libc_port" / "include"


class LibcHeadersTest(unittest.TestCase):
    def test_generate_and_compile(self):
        kdir = f"/lib/modules/{os.uname().release}/build"
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [sys.executable, str(PY_DIR / "gen_libc_headers.py"),
                 "--kdir", kdir, "--out-dir", tmp],
                check=True)
            gccinc = subprocess.check_output(
                ["gcc", "-print-file-name=include"], text=True).strip()
            source = Path(tmp) / "test.c"
            source.write_text(
                "#include <stdint.h>\n"
                "#include <limits.h>\n"
                "#include <bits/types.h>\n"
                "#include <errno.h>\n"
                '_Static_assert(sizeof(int8_t) == 1, "int8");\n'
                '_Static_assert(sizeof(uint64_t) == 8, "uint64");\n'
                '_Static_assert(sizeof(intptr_t) == sizeof(void *), "intptr");\n'
                '_Static_assert(INT_MAX == 2147483647, "int max");\n'
                '_Static_assert(CHAR_MIN == 0, "unsigned char min");\n'
                '_Static_assert(CHAR_MAX == 255, "unsigned char max");\n'
                '_Static_assert(sizeof(time_t) == 8, "time_t");\n'
                '_Static_assert(EPERM == 1 && ENOENT == 2 && EINVAL == 22, "errno");\n',
                encoding="utf-8")
            subprocess.run(
                ["gcc", "-std=gnu11", "-nostdinc", "-isystem", gccinc,
                 "-funsigned-char", "-I", tmp, "-I", str(INCLUDE),
                 "-fsyntax-only", str(source)],
                check=True)


if __name__ == "__main__":
    unittest.main()
