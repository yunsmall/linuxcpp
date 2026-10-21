"""gen_libc_shim.py 生成的标准头能用 gcc 编译，类型宽度正确。"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "linuxcpp" / "python"))

import gen_libc_shim


class ShimTest(unittest.TestCase):
    def test_generate_and_compile(self):
        with tempfile.TemporaryDirectory() as tmp:
            macros = gen_libc_shim.collect_macros("gcc")
            for name, generator in gen_libc_shim.GENERATORS.items():
                text = (generator(macros)
                        if generator in (gen_libc_shim.gen_stdint, gen_libc_shim.gen_limits)
                        else generator())
                (Path(tmp) / name).write_text(text, encoding="utf-8")
            gccinc = subprocess.check_output(
                ["gcc", "-print-file-name=include"], text=True).strip()
            source = Path(tmp) / "test.c"
            source.write_text(
                "#include <stdint.h>\n#include <limits.h>\n"
                '_Static_assert(sizeof(int8_t) == 1, "int8");\n'
                '_Static_assert(sizeof(uint64_t) == 8, "uint64");\n'
                '_Static_assert(sizeof(intptr_t) == sizeof(void *), "intptr");\n'
                '_Static_assert(INT_MAX == 2147483647, "int max");\n'
                '_Static_assert(CHAR_MIN == 0, "char min");\n'
                '_Static_assert(CHAR_MAX == 255, "char max");\n',
                encoding="utf-8")
            subprocess.run(
                ["gcc", "-std=gnu11", "-nostdinc", "-isystem", gccinc,
                 "-I", tmp, "-fsyntax-only", str(source)],
                check=True)


if __name__ == "__main__":
    unittest.main()
