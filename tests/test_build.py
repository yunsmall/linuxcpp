"""build.py 纯函数测试：编译器推导、flags 转换、配置合并。"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "linuxcpp" / "python"))

import build
from linuxcppgen import decls


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

    def test_device_model_preset_merges(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "module.toml"
            path.write_text(
                '[module]\nname = "demo"\n[bindings]\n'
                'preset = "device_model"\n'
                'roots = ["extra_type"]\n'
                'extern = ["extra_func"]\n'
                'macro = ["EXTRA_MACRO"]\n'
                'headers = ["linux/extra.h"]\n',
                encoding="utf-8")
            config = build.load_config(Path(tmp))
            self.assertEqual(config["preset"], "device_model")
            for name in ("device", "bus_type", "platform_driver"):
                self.assertIn(name, config["roots"])
            self.assertIn("extra_type", config["roots"])
            self.assertIn("device_register", config["extern"])
            self.assertIn("platform_device_put", config["extern"])
            self.assertIn("extra_func", config["extern"])
            self.assertIn("PAGE_SIZE", config["macro"])
            self.assertIn("EXTRA_MACRO", config["macro"])
            self.assertIn("linux/device.h", config["headers"])
            self.assertIn("linux/extra.h", config["headers"])

    def test_unknown_preset_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "module.toml"
            path.write_text(
                '[module]\nname = "demo"\n[bindings]\npreset = "nope"\n',
                encoding="utf-8")
            with self.assertRaises(SystemExit):
                build.load_config(Path(tmp))

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

    def test_init_creates_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "my_module"
            build.init_module(module)
            toml = (module / "module.toml").read_text(encoding="utf-8")
            makefile = (module / "Makefile").read_text(encoding="utf-8")
            driver = (module / "driver.cpp").read_text(encoding="utf-8")
            self.assertIn('name = "my_module"', toml)
            self.assertIn("obj-m := my_module.o", makefile)
            self.assertIn("my_module-y := driver.o", makefile)
            self.assertIn("include $(LINUXCPP)/libcxx.mk", makefile)
            self.assertIn("LCPP_MODULE_RAW", driver)
            # 第二次创建必须拒绝，不能覆盖用户已经改过的文件
            with self.assertRaises(SystemExit):
                build.init_module(module)

    def test_existing_makefile_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp)
            makefile = module / "Makefile"
            original = "obj-m := keep.o\nkeep-y := keep.o\n"
            makefile.write_text(original, encoding="utf-8")
            build.write_makefile(module, {"name": "demo"}, "/k",
                                 "entry_gen.o", ["driver.o"])
            self.assertEqual(makefile.read_text(encoding="utf-8"), original)

    def test_init_rejects_invalid_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                build.init_module(Path(tmp) / "1bad")

    def test_kernel_exported_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Module.symvers").write_text(
                "0x12345678\tmisc_register\tvmlinux\tEXPORT_SYMBOL\n"
                "0x9abcdef0\tcopy_to_iter\tvmlinux\tEXPORT_SYMBOL_GPL\n",
                encoding="utf-8")
            symbols = decls.kernel_exported_symbols(tmp)
            self.assertEqual(symbols, {"misc_register", "copy_to_iter"})

    def test_kernel_exported_symbols_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(decls.kernel_exported_symbols(tmp))


if __name__ == "__main__":
    unittest.main()
