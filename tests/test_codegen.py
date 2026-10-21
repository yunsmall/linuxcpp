"""生成器回归测试。

用固定的小 C 头模拟 vmlinux.h，不依赖真实内核 BTF/bpftool，
覆盖依赖排序、packed、匿名成员、位域、函数指针、数组、typedef 链、
关键字转义、同名 typedef 等边界，并验证生成的 C/C++ 能通过编译。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "linuxcpp" / "python"))

import clang.cindex as ci

from linuxcppgen import btf, codegen, decls, deps, types
from linuxcppgen.config import cpp_field_name

BASE_TYPES = """\
typedef unsigned char __u8;
typedef unsigned short __u16;
typedef unsigned int __u32;
typedef unsigned long long __u64;
typedef signed char __s8;
typedef signed int __s32;
"""

DECLS = """\
typedef void (*fn_t)(void);
typedef int (*handler_t)(void *);
typedef void fn_type(void);
typedef fn_type *fn_ptr;
typedef int matrix_t[2][3];

struct inner {
    __u8 a;
    __u32 b;
} __attribute__((packed));

union value {
    __u32 i;
    __u8 bytes[4];
};

struct node {
    struct node *next;
    union value v;
    __u8 flags : 3;
    int (*callback)(struct node *, __u32);
    int (*handler_array[2])(void);
    union {
        __u64 x;
        struct {
            __u16 lo;
            __u16 hi;
        };
    };
};

typedef struct {
    __u8 data[8];
} array_holder;

typedef array_holder holder_alias;

struct edge {
    __u8 zero[0];
    int (*arr_ptr)[4];
    int (*varargs)(const char *, ...);
    fn_t fp;
    matrix_t m;
    holder_alias alias;
};

enum small {
    SMALL_A,
    SMALL_B,
};

enum big {
    BIG_A = 0xFFFFFFFFFFFFFFFFULL,
};

struct has_enum {
    enum small e;
    __u8 tail;
};

struct packed_bits {
    enum {
        BIT_A,
        BIT_B,
    } kind : 8;
    __u8 tail;
};

struct keyword_fields {
    int class;
    int export;
};

struct same_name {
    struct inner inner;
};

struct holder_inner {
    __u32 value;
};

typedef struct {
    struct holder_inner inner;
} holder_outer;

typedef struct {
    __u8 x;
} *anon_ptr_t;

typedef struct {
    __u8 y;
} anon_arr_t[2];

typedef enum {
    ANON_NEG = -1,
} anon_neg_t;

typedef enum {
    ANON_BIG = 1024,
} anon_big_t;

struct anon_enum_bits {
    enum {
        NEG_BIT = -1,
    } neg : 4;
    enum {
        BIG_BIT = 1024,
    } big : 1;
};

struct btf_pad {
    __u8 a;
    __u8 b;
    __u32 c;
};

typedef struct pair pair;
struct pair {
    struct pair *next;
    int v;
};

typedef enum {
    ANON_A,
    ANON_B,
} anon_enum_t;

enum keyword_consts {
    class = 0,
    new = 1,
    export = 2,
};
"""

ROOTS = [
    "node", "edge", "has_enum", "packed_bits", "keyword_fields", "same_name",
    "pair", "inner", "value", "array_holder", "holder_alias", "matrix_t",
    "fn_type", "fn_ptr", "fn_t", "handler_t", "anon_enum_t",
    "holder_inner", "holder_outer", "anon_ptr_t", "anon_arr_t",
    "anon_neg_t", "anon_big_t", "anon_enum_bits", "btf_pad", "keyword_consts",
]


def write_fixture(directory):
    vmlinux_h = Path(directory) / "vmlinux.h"
    vmlinux_h.write_text(BASE_TYPES + DECLS, encoding="utf-8")
    base_h = Path(directory) / "base.h"
    base_h.write_text(BASE_TYPES, encoding="utf-8")
    return vmlinux_h, base_h


def render(deps, records, order, cpp):
    mapper = types.cpp_type_name if cpp else (lambda name: "lc_" + name)
    field = cpp_field_name if cpp else (lambda name: name)
    const_prefix = "" if cpp else "lc_"
    lines = []
    for name in sorted(deps.fwd_records | deps.want_records):
        decl = records.get(name)
        if decl is None:
            continue
        keyword = "struct" if decl.kind == ci.CursorKind.STRUCT_DECL else "union"
        lines.append(f"{keyword} {mapper(name)};")
    for name in sorted(deps.want_enums):
        lines.append(types.gen_enum(deps.want_enums[name], mapper, cpp, const_prefix))
    for kind, name in order:
        if kind == "typedef" and name in deps.typedefs:
            lines.append(types.gen_typedef(deps.typedefs[name], mapper, field, cpp,
                                           const_prefix))
        elif kind == "record":
            lines.append(types.gen_record(records[name], mapper, field, cpp,
                                          const_prefix))
    return "\n".join(lines)


class CodegenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        vmlinux_h, self.base_h = write_fixture(self.tmp.name)
        self.records, self.typedefs, self.enums = btf.parse_header(str(vmlinux_h))
        types.set_records(self.records)
        types.set_btf_packed(set())
        types.set_btf_layout({}, {}, {}, {})
        self.deps = deps.Dependencies(self.records, self.typedefs, self.enums)
        self.deps.run(ROOTS)
        self.order = types.output_order(self.deps)

    def compile(self, text, cpp):
        source = Path(self.tmp.name) / ("test.cpp" if cpp else "test.c")
        source.write_text(f'#include "{self.base_h}"\n{text}\n', encoding="utf-8")
        if cpp:
            cmd = ["g++", "-std=gnu++20", "-fno-exceptions", "-fno-rtti",
                   "-fms-extensions", "-fsyntax-only", str(source)]
        else:
            cmd = ["gcc", "-std=gnu11", "-fsyntax-only", str(source)]
        subprocess.run(cmd, check=True)

    def test_c_generation_compiles(self):
        text = render(self.deps, self.records, self.order, False)
        for needle in ("__attribute__((packed))", "mode(__SI__)",
                       "(*handler_array[2])(void)", "(*arr_ptr)[4]",
                       "(*varargs)(const char *, ...)", "lc_matrix_t[2][3]",
                       "typedef void lc_fn_type(void);", "typedef lc_fn_type *lc_fn_ptr;",
                       "zero[0]", "struct lc_pair {", "kind : 8",
                       "*lc_anon_ptr_t", "lc_anon_arr_t[2]",
                       "lc_class = 0"):
            self.assertIn(needle, text)
        self.compile(text, False)

    def test_cpp_generation_compiles(self):
        text = render(self.deps, self.records, self.order, True)
        for needle in ("__attribute__((packed))", "class_", "export_",
                       "inner_", "typedef fn_type *fn_ptr;", "struct pair {",
                       "enum : unsigned int", "kind : 8",
                       "enum : int", "class_ = 0", "new_ = 1", "export_ = 2"):
            self.assertIn(needle, text)
        self.compile(text, True)

    def test_btf_json_groups_duplicates(self):
        data = {
            "types": [
                {"id": 1, "kind": "STRUCT", "name": "dup", "size": 4,
                 "members": [{"name": "a", "type_id": 2, "bits_offset": 0}]},
                {"id": 3, "kind": "STRUCT", "name": "dup", "size": 8,
                 "members": [{"name": "b", "type_id": 2, "bits_offset": 0}]},
            ]
        }
        path = Path(self.tmp.name) / "btf.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        info = btf.parse_btf_json(str(path))
        self.assertEqual([entry["size"] for entry in info["dup"]], [4, 8])
        self.assertEqual(codegen.btf_entry("dup", info)["size"], 4)
        self.assertEqual(codegen.btf_entry("dup___2", info)["size"], 8)

    def test_array_typedef_after_record(self):
        # array_holder 是数组元素类型，必须先于持有它的 record 定义
        positions = {name: index for index, (_, name) in enumerate(self.order)}
        self.assertLess(positions["array_holder"], positions["node"])

    def test_same_name_typedef_root_generates_record(self):
        # typedef struct pair pair; 作为 root 时必须生成完整 struct，而不是只留别名
        kinds = {name: kind for kind, name in self.order}
        self.assertEqual(kinds.get("pair"), "record")

    def test_anonymous_typedef_value_dependency_order(self):
        # 匿名 struct typedef 里按值嵌入的 record 必须先完整定义
        positions = {name: index for index, (_, name) in enumerate(self.order)}
        self.assertLess(positions["holder_inner"], positions["holder_outer"])

    def test_btf_layout_repair_inserts_padding(self):
        # bpftool 丢 packed 后 clang 自然布局是 8 字节，BTF 实际是 7 字节：
        # btf_pad.c 必须按 bit offset 补 1 字节再整体 packed
        entry = {
            "id": 100, "kind": "STRUCT", "size": 7,
            "members": [("a", 0, None, 10), ("b", 8, None, 10),
                        ("c", 24, None, 11)],
        }
        by_id = {
            9: {"id": 9, "kind": "INT", "name": "unsigned char", "size": 1,
                "members": []},
            10: {"id": 10, "kind": "TYPEDEF", "name": "__u8", "size": 0,
                 "members": [], "type_id": 9},
            11: {"id": 11, "kind": "INT", "name": "unsigned int", "size": 4,
                 "members": []},
        }
        types.set_btf_layout({"btf_pad": entry}, {}, by_id, {})
        decl = self.records["btf_pad"]
        self.assertTrue(types.layout_needs_repair(decl, entry))
        text = types.gen_record(decl, lambda name: "lc_" + name,
                                lambda name: name, False)
        self.assertIn("__attribute__((packed))", text)
        self.assertIn("unsigned char __lcpp_pad0[1];", text)
        self.compile("typedef unsigned char lc___u8;\n"
                     "typedef unsigned int lc___u32;\n" + text, False)

    def test_c_array_pointer_return(self):
        # int (*f(void))[4] 的返回类型必须把函数名放进 (*...) 里
        source = Path(self.tmp.name) / "fn.c"
        source.write_text("int (*get_rows(void))[4];\n", encoding="utf-8")
        tu = ci.Index.create().parse(str(source))
        cursor = next(child for child in tu.cursor.get_children()
                      if child.kind == ci.CursorKind.FUNCTION_DECL)
        self.assertEqual(decls.c_function_head(cursor, "lc_", ["void"]),
                         "int (*lc_get_rows(void))[4]")

    def test_btf_json_type_ids_and_array_size(self):
        data = {
            "types": [
                {"id": 1, "kind": "INT", "name": "int", "size": 4},
                {"id": 2, "kind": "TYPEDEF", "name": "my_t", "type_id": 1},
                {"id": 3, "kind": "ARRAY", "name": "(anon)", "type_id": 1,
                 "index_type_id": 1, "nr_elems": 3},
                # 缺 id 的条目必须跳过，不能让整个生成器 KeyError
                {"kind": "STRUCT", "name": "broken", "size": 4},
            ]
        }
        path = Path(self.tmp.name) / "raw.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        info = btf.parse_btf_json(str(path))
        types.set_btf_layout({}, {}, info.by_id, info.typedefs)
        self.assertEqual(info.typedefs["my_t"], [1])
        self.assertEqual(info.by_id[3]["type_id"], 1)
        self.assertEqual(types.btf_size_bytes(3), 12)
        self.assertNotIn("broken", info)


if __name__ == "__main__":
    unittest.main()
