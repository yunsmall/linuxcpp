"""build.py 纯函数测试：编译器推导、flags 转换、配置合并。"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "linuxcpp" / "python"))

import build


class BuildTest(unittest.TestCase):
    def test_is_compiler_token(self):
        for token in ("gcc", "gcc-12", "/usr/bin/gcc-12", "clang", "clang-18",
                      "/usr/bin/clang++", "cc", "c++"):
            self.assertTrue(build.is_compiler_token(token), token)
        for token in ("ccache", "distcc", "ld", "gcc-ar", "clangd"):
            self.assertFalse(build.is_compiler_token(token), token)

    def test_cxx_compiler(self):
        self.assertEqual(build.cxx_compiler({"cxx": ""}, "gcc"), "g++")
        self.assertIn(build.cxx_compiler({"cxx": ""}, "clang-22"),
                      ("clang++-22", "clang++"))
        self.assertEqual(build.cxx_compiler({"cxx": "clang++-22"}, "gcc"), "clang++-22")

    def test_to_cxx_flags(self):
        flags = build.to_cxx_flags([
            "gcc", "-c", "-o", "x.o", "-I/inc", "-include", "k.h",
            "-Wmissing-prototypes", "-Werror=missing-prototypes",
            "-Werror=implicit-int", "-Werror=incompatible-pointer-types",
            "-Werror=int-conversion", "-Werror=return-type",
            "-std=gnu11", "-nostdinc",
            "-fpatchable-function-entry=16,16", "-pg",
        ])
        self.assertIn("-std=gnu++20", flags)
        self.assertIn("-fms-extensions", flags)
        self.assertIn("-Werror=return-type", flags)
        for dropped in ("-Wmissing-prototypes", "-Werror=missing-prototypes",
                        "-Werror=implicit-int", "-Werror=incompatible-pointer-types",
                        "-Werror=int-conversion", "-std=gnu11", "-nostdinc",
                        "-pg", "gcc", "-c",
                        "-fpatchable-function-entry=16,16", "-I/inc", "k.h"):
            self.assertNotIn(dropped, flags)

    def test_load_config_defaults_and_cxx(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "module.toml"
            path.write_text(
                '[module]\nname = "demo"\n[build]\ncxx = "clang++-22"\n',
                encoding="utf-8")
            config = build.load_config(Path(tmp))
            self.assertEqual(config["name"], "demo")
            self.assertEqual(config["cxx"], "clang++-22")
            self.assertEqual(config["roots"], build.DEFAULTS["roots"])

    @staticmethod
    def module_config(entry=""):
        return {
            "name": "demo", "description": "demo", "license": "GPL",
            "entry": entry, "device": "demo", "mode": "0666",
        }

    def test_reject_linuxcpp_c(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp)
            (module / "generated").mkdir()
            (module / "linuxcpp.c").write_text("//\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                build.generate_sources(module, self.module_config())

    def test_stale_entry_gen_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp)
            (module / "generated").mkdir()
            (module / "my_entry.c").write_text("//\n", encoding="utf-8")
            (module / "entry_gen.c").write_text("// stale\n", encoding="utf-8")
            build.generate_sources(module, self.module_config("my_entry.c"))
            kbuild = (module / "Kbuild").read_text(encoding="utf-8")
            self.assertNotIn("entry_gen.o", kbuild)

    def test_bad_mode_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp)
            (module / "generated").mkdir()
            config = self.module_config()
            config["mode"] = "999"
            with self.assertRaises(SystemExit):
                build.generate_sources(module, config)

    def test_reserved_generated_object_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp)
            (module / "generated").mkdir()
            (module / "layout_check.cpp").write_text("//\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                build.generate_sources(module, self.module_config())

    def test_entry_and_cpp_object_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp)
            (module / "generated").mkdir()
            (module / "my_entry.c").write_text("//\n", encoding="utf-8")
            (module / "my_entry.cpp").write_text("//\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                build.generate_sources(module, self.module_config("my_entry.c"))


if __name__ == "__main__":
    unittest.main()
