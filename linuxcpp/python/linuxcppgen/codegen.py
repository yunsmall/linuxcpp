"""绑定生成流程编排：BTF → 类型闭包 → C/C++ 输出 → 布局校验。"""

import os
import sys

import clang.cindex as ci

from . import btf, decls, types
from .config import (CORE_MACROS, DEFAULT_EXTERN_FUNCS, DEFAULT_HEADERS,
                     MANUAL_THUNK_FUNCS, ROOTS, c_type_name, cpp_field_name,
                     cpp_type_name)
from .deps import Dependencies

# bindings.hpp 已经 include <stddef.h>，这些名字在全局命名空间里已有定义；
# 在 namespace 内重复 typedef 后，using namespace 会让无限定的名字查找产生二义性
CPP_GLOBAL_TYPEDEFS = {
    "bool", "wchar_t", "char8_t", "char16_t", "char32_t",
    "size_t", "ptrdiff_t", "max_align_t", "nullptr_t",
}


def layout_fields(decl):
    """展开匿名 struct/union 的提升字段；位域不能用 offsetof，靠根的 sizeof 校验"""
    for field in decl.type.get_fields():
        if not field.spelling.isidentifier():
            inner = field.type.get_declaration()
            if inner.kind in (ci.CursorKind.STRUCT_DECL, ci.CursorKind.UNION_DECL):
                yield from layout_fields(inner)
            continue
        width = field.get_bitfield_width()
        if width is not None and width >= 0:
            continue
        yield field


def layout_matches(decl, entry):
    """vmlinux.h 里的声明是否与 BTF 布局一致。

    bpftool 会给 BTF 空洞补无名位域，也会把匿名成员命名为 (anon)，
    这些都不是真实字段，比较时必须忽略名字和补位字段。
    """
    fields = [field for field in decl.type.get_fields()
              if not types.is_padding_field(field)]
    if len(fields) != len(entry["members"]):
        return False
    if decl.type.get_size() != entry["size"]:
        return False
    for field, (_, bits, bitfield_size, _) in zip(fields, entry["members"]):
        if field.get_field_offsetof() != bits:
            return False
        # libclang 对非位域字段返回 -1，统一成 None 再比较
        width = field.get_bitfield_width()
        if width is not None and width < 0:
            width = None
        if bitfield_size is None:
            if width is not None:
                return False
        elif width != bitfield_size:
            return False
    return True


def nested_value_records(decl):
    """字段里按值出现的 record 名；指针只需要前向声明，不递归"""
    result = []
    for field in decl.type.get_fields():
        stack = [field.type]
        while stack:
            t = stack.pop()
            if t.kind == ci.TypeKind.POINTER:
                continue
            if t.kind in (ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY):
                stack.append(t.element_type)
            elif t.kind == ci.TypeKind.TYPEDEF:
                stack.append(t.get_declaration().underlying_typedef_type)
            elif t.kind in (ci.TypeKind.ELABORATED, ci.TypeKind.RECORD):
                inner = t.get_declaration()
                if inner.kind == ci.CursorKind.TYPEDEF_DECL:
                    stack.append(inner.underlying_typedef_type)
                elif inner.is_anonymous() and inner.kind in (
                        ci.CursorKind.STRUCT_DECL, ci.CursorKind.UNION_DECL):
                    # 匿名成员里的按值嵌套类型也要参与 type_ok 递归
                    stack.extend(f.type for f in inner.type.get_fields())
                elif inner.spelling:
                    result.append(inner.spelling)
    return result


def btf_entry(name, info):
    """vmlinux.h 的重名类型带 ___2/___3 后缀（bpftool 从 2 开始编号），
    按基名取 BTF 条目，再用序号选对应的一份"""
    # 类型名本身就叫 xxx___2 时优先按原名查，不能误当成 bpftool 的编号
    entries = info.get(name)
    if entries:
        return entries[0]
    if "___" in name:
        base, _, suffix = name.rpartition("___")
        if not suffix.isdigit():
            # 名字本身就含非数字的 ___，不是 bpftool 的重命名，不能回退到 basename
            return None
        numbered = True
    else:
        base, numbered = name, False
    entries = info.get(base)
    if not entries:
        return None
    if numbered:
        # 第一次出现不带后缀，___2 是第二份，所以 0-based 下标是 N-1
        index = int(suffix) - 1
        if 0 <= index < len(entries):
            return entries[index]
    return entries[0]


def btf_typedef_id(name, info):
    """typedef 也要处理 bpftool 的 ___2 重命名"""
    entries = info.typedefs.get(name)
    if entries:
        return entries[0]
    if "___" in name:
        base, _, suffix = name.rpartition("___")
        if suffix.isdigit():
            entries = info.typedefs.get(base)
            index = int(suffix) - 1
            if entries and 0 <= index < len(entries):
                return entries[index]
    return None


def resolve_btf_record(info, type_id):
    """跟随 typedef/array/限定符找到实际的 struct/union 条目"""
    entry = info.by_id.get(type_id)
    depth = 0
    while entry is not None and depth < 32:
        kind = entry["kind"]
        if kind in ("STRUCT", "UNION"):
            return entry
        if kind in ("TYPEDEF", "CONST", "VOLATILE", "RESTRICT", "TYPE_TAG",
                    "ARRAY", "PTR"):
            entry = info.by_id.get(entry["type_id"])
            depth += 1
            continue
        return None
    return None


def record_decl_of_type(t):
    """剥掉数组/指针/typedef/限定符，返回最内层的 record 声明"""
    while t.kind in (ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY):
        t = t.element_type
    if t.kind == ci.TypeKind.POINTER:
        return record_decl_of_type(t.get_pointee())
    while t.kind == ci.TypeKind.TYPEDEF:
        t = t.get_declaration().underlying_typedef_type
    if t.kind == ci.TypeKind.ELABORATED:
        decl = t.get_declaration()
        if decl.kind == ci.CursorKind.TYPEDEF_DECL:
            return record_decl_of_type(decl.underlying_typedef_type)
    if t.kind == ci.TypeKind.RECORD:
        return t.get_declaration()
    return None


def anonymous_record_decl(t):
    """剥掉数组/指针/typedef 后，如果最内层是匿名 record 就返回它的声明"""
    while t.kind in (ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY):
        t = t.element_type
    if t.kind == ci.TypeKind.POINTER:
        return anonymous_record_decl(t.get_pointee())
    while t.kind == ci.TypeKind.TYPEDEF:
        t = t.get_declaration().underlying_typedef_type
    if t.kind == ci.TypeKind.ELABORATED:
        decl = t.get_declaration()
        if decl.kind == ci.CursorKind.TYPEDEF_DECL:
            return anonymous_record_decl(decl.underlying_typedef_type)
    if t.kind == ci.TypeKind.RECORD:
        decl = t.get_declaration()
        if decl.is_anonymous() and decl.kind in (ci.CursorKind.STRUCT_DECL,
                                                 ci.CursorKind.UNION_DECL):
            return decl
    return None


def bind_anonymous_layout(decl, entry, info, anon):
    """把 BTF 的匿名 record 条目和 clang 游标按字段顺序对上"""
    fields = [field for field in decl.type.get_fields()
              if not types.is_padding_field(field)]
    members = entry["members"]
    if len(fields) != len(members):
        return
    for field, member in zip(fields, members):
        target = resolve_btf_record(info, member[3])
        inner = anonymous_record_decl(field.type)
        if target is None or inner is None:
            continue
        anon[inner.get_usr()] = target
        bind_anonymous_layout(inner, target, info, anon)


def build_btf_layout(records, typedefs, info):
    """建立具名/匿名 record 到 BTF 布局的映射"""
    named = {}
    for name, decl in records.items():
        entry = btf_entry(name, info)
        if entry is not None:
            named[name] = entry
    anon = {}
    # typedef 的匿名 struct（atomic_t 这类）也需要按 BTF 修布局。
    # libclang 会把这种 struct 的 spelling 设成 typedef 名，所以 records 里可能
    # 已经有一份“具名”游标，直接用它的 USR 做布局键。
    for name, decl in typedefs.items():
        target = resolve_btf_record(info, btf_typedef_id(name, info))
        if target is None:
            continue
        root = records.get(name)
        # 同名不代表同一个类型：typedef 可能指向别的 struct；
        # libclang 也会把 typedef 的匿名 struct 起成 typedef 名
        base = record_decl_of_type(decl.underlying_typedef_type)
        if root is not None and base is not None and base.get_usr() != root.get_usr():
            root = None
        if root is None:
            root = anonymous_record_decl(decl.underlying_typedef_type)
        if root is None:
            continue
        named[name] = target
        anon[root.get_usr()] = target
        bind_anonymous_layout(root, target, info, anon)
    for name, entry in named.items():
        if name in records:
            bind_anonymous_layout(records[name], entry, info, anon)
    return named, anon


def btf_layout_check(args, records, deps, roots, info):
    """全量模式直接拿 BTF 的 size/bit offset 校验生成类型，不依赖内核内部头"""
    lines = [
        "/* 由 gen_bindings.py 从 BTF 自动生成，不要手改 */",
        "#include <linux/types.h>",
        "#include <linux/stddef.h>",
        '#include "generated/bindings.h"',
        "",
    ]
    checked = missing = repaired = 0
    checks = {}

    def type_ok(name):
        """自身和所有按值嵌套的类型都必须与 BTF 一致，否则外层偏移可能碰巧
        相同、内层字段却已经错位"""
        if name in checks:
            return checks[name]
        decl = records.get(name)
        entry = types.btf_entry_for(decl) if decl is not None else None
        if decl is None:
            # 字段里按值出现的是 typedef（atomic_t 这类），没有 struct 游标；
            # 它的匿名底层 record 已经登记进 BTF_ANON，由生成器负责修正
            if name not in deps.typedefs:
                checks[name] = False
                return False
            underlying = anonymous_record_decl(
                deps.typedefs[name].underlying_typedef_type)
            target = resolve_btf_record(info, btf_typedef_id(name, info))
            if underlying is not None and target is not None:
                natural, _ = types.natural_record_layout(target["id"], target)
                if types.record_plan(underlying)[0] is not None:
                    ok = True
                elif natural is False:
                    ok = False
                elif natural is None:
                    ok = layout_matches(underlying, target)
                else:
                    ok = True
                checks[name] = ok
                return ok
            checks[name] = True
            return True
        if entry is None:
            checks[name] = False
            return False
        checks[name] = False  # 先占位，防止自引用循环
        # 生成器会按 BTF 偏移重建的类型，clang 布局本来就不一致；
        # BTF 能推出自然布局的类型也不看 clang——vmlinux.h 可能只是漏了
        # 某个嵌套类型的 packed，生成代码用的是修好的嵌套类型
        natural, _ = types.natural_record_layout(entry["id"], entry)
        if types.record_plan(decl)[0] is None:
            if natural is False:
                return False  # 需要按 BTF 重建，但当前无法安全重建
            if natural is None and not layout_matches(decl, entry):
                return False
        for dep in nested_value_records(decl):
            if dep in records and not type_ok(dep):
                return False
        checks[name] = True
        return True

    self_bad, nested_bad = [], []
    for name in roots:
        decl = records.get(name)
        if decl is None:
            # 显式把 typedef 名当根时没有 record 游标，至少校验它的大小
            if name in deps.typedefs:
                size = types.btf_size_bytes(btf_typedef_id(name, info))
                if size is None:
                    missing += 1
                else:
                    lines.append(
                        f'_Static_assert(sizeof({args.prefix}{name}) == {size}, '
                        f'"size typedef {name}");')
                    checked += 1
            continue
        entry = types.btf_entry_for(decl)
        if entry is None:
            missing += 1
            continue
        plan = types.record_plan(decl)
        natural, _ = types.natural_record_layout(entry["id"], entry)
        if plan[0] is not None:
            repaired += 1
        elif natural is False:
            self_bad.append(name)
            continue
        elif natural is None and not layout_matches(decl, entry):
            self_bad.append(name)
            continue
        elif not type_ok(name):
            nested_bad.append(name)
            continue
        keyword = "struct" if decl.kind == ci.CursorKind.STRUCT_DECL else "union"
        ref = f"{keyword} {args.prefix}{name}"
        lines.append(f'_Static_assert(sizeof({ref}) == {entry["size"]}, "size {name}");')
        for field, bits, bitfield_size, _ in entry["members"]:
            # 位域不能用 offsetof；匿名成员没有可用名字
            if bitfield_size is not None or not field.isidentifier():
                continue
            lines.append(
                f'_Static_assert(offsetof({ref}, {field}) == {bits // 8}, '
                f'"offset {name}.{field}");')
        lines.append("")
        checked += 1
    for name in sorted(deps.want_enums):
        entry = btf_entry(name, info)
        if entry is None or entry["kind"] != "ENUM":
            missing += 1
            continue
        lines.append(
            f'_Static_assert(sizeof(enum {args.prefix}{name}) == {entry["size"]}, '
            f'"size enum {name}");')
        checked += 1
    skipped = len(self_bad) + len(nested_bad)
    print(f"布局校验：{checked} 个类型有 BTF 尺寸记录，{missing} 个没有，"
          f"{repaired} 个按 BTF 偏移重建，{skipped} 个无法还原"
          f"（自身 {len(self_bad)}，嵌套 {len(nested_bad)}）")
    if self_bad:
        print("  自身布局不一致：" + ", ".join(self_bad[:10])
              + (" ..." if len(self_bad) > 10 else ""))
    if nested_bad:
        print("  嵌套了不一致类型：" + ", ".join(nested_bad[:10])
              + (" ..." if len(nested_bad) > 10 else ""))
    if self_bad or nested_bad:
        skipped_names = ", ".join(sorted(set(self_bad + nested_bad)))
        lines.append(f"/* SKIP 布局不一致且无法重建: {skipped_names} */")
    return lines


def generate(args):
    sys.setrecursionlimit(100000)
    vmlinux_h = btf.dump_btf(args.out_dir, args.btf)
    records, typedefs, enums = btf.parse_header(vmlinux_h)
    types.set_records(records)
    types.set_btf_packed(set(args.packed))
    # 普通构建也要 BTF 布局：默认 roots 里就可能遇到 bpftool 丢了 packed 的类型
    btf_info = btf.parse_btf_json(btf.dump_btf_json(args.out_dir, args.btf))
    named_layout, anon_layout = build_btf_layout(records, typedefs, btf_info)
    types.set_btf_layout(named_layout, anon_layout, btf_info.by_id, btf_info.typedefs)

    roots = list(records) if getattr(args, "all", False) else (args.roots or ROOTS)
    known_roots = set(records) | set(typedefs) | set(enums)
    for name in roots:
        if name not in known_roots:
            print(f"警告：roots 里的 {name} 在 BTF 中没有对应类型，已忽略")
    deps = Dependencies(records, typedefs, enums)
    deps.run(roots)
    known = deps.want_records | deps.want_typedefs | deps.fwd_records | set(deps.want_enums)

    macro_names = list(dict.fromkeys(CORE_MACROS + args.macro))
    macro_defs = decls.parse_macros(macro_names, args.kdir, args.headers)
    extern_decls, thunk_decls, thunk_sources = [], [], []
    thunk_prototypes = []
    if args.extern or args.thunk:
        found = decls.parse_kernel_decls(set(args.extern) | set(args.thunk),
                                         args.kdir, args.headers)
        exported = decls.kernel_exported_symbols(args.kdir)
        for name in args.extern:
            cursor = found.get(name)
            if cursor is None:
                print(f"警告：extern 里的 {name} 找不到函数声明；"
                      f"如果它是 static inline，请改放到 bindings.thunk；"
                      f"如果是函数宏，只能在 C 文件里手写包装")
                continue
            # static inline 在头文件里有定义，却没有可链接的导出符号
            if cursor.is_definition() and cursor.storage_class == ci.StorageClass.STATIC:
                print(f"警告：extern 里的 {name} 是 static inline 定义，"
                      f"导出符号并不存在；请改放到 bindings.thunk")
                continue
            if exported is not None and name not in exported:
                print(f"警告：extern 里的 {name} 不在 {args.kdir}/Module.symvers 中，"
                      f"可能没有导出；如果它是 static inline，请改放到 bindings.thunk")
            extern_decls.append(decls.gen_cpp_decl(cursor, "", known))
        for name in args.thunk:
            cursor = found.get(name)
            if cursor is None:
                print(f"警告：thunk 里的 {name} 找不到函数声明；"
                      f"如果它是函数宏，只能在 C 文件里手写包装")
                continue
            if not cursor.is_definition():
                if exported is not None and name in exported:
                    print(f"警告：thunk 里的 {name} 是导出函数，没有内联定义；"
                          f"请改放到 bindings.extern")
                else:
                    print(f"警告：thunk 里的 {name} 在头文件里没有定义，无法生成 thunk；"
                          f"如果它是导出函数，请改放到 bindings.extern")
                continue
            thunk_prototypes.append(
                decls.gen_c_thunk_head(cursor, args.prefix) + ";")
            thunk_sources.append(decls.gen_c_thunk(cursor, args.prefix))
            thunk_decls.append(decls.gen_cpp_decl(cursor, args.prefix, known))
    order = types.output_order(deps)

    def c_name(name):
        return c_type_name(name, args.prefix)

    # ---- C 版本 ----
    c_lines = [
        "/* 由 gen_bindings.py 从 BTF 自动生成，不要手改 */",
        "#ifndef LC_BINDINGS_H",
        "#define LC_BINDINGS_H",
        "#include <linux/types.h>",
        "",
    ]
    # 完整定义的类型也先声明一次：typedef 别名会先用 struct 标签
    for name in sorted(deps.fwd_records | deps.want_records):
        decl = records.get(name)
        if decl is not None and decl.kind != ci.CursorKind.ENUM_DECL:
            keyword = "struct" if decl.kind == ci.CursorKind.STRUCT_DECL else "union"
            c_lines.append(f"{keyword} {c_name(name)};")
    c_lines.append("")
    # C 没有命名空间，枚举常量也要加前缀，否则会和内核头里的同名常量撞车
    for name in sorted(deps.want_enums):
        c_lines.append(types.gen_enum(deps.want_enums[name], c_name,
                                      const_prefix=args.prefix))
    for kind, name in order:
        if kind == "typedef":
            if name in deps.typedefs:
                c_lines.append(types.gen_typedef(deps.typedefs[name], c_name,
                                                 lambda n: n, False, args.prefix))
        else:
            c_lines.append(types.gen_record(records[name], c_name, lambda n: n,
                                            False, args.prefix))
    c_lines.append("")
    c_lines.append("#endif")

    with open(os.path.join(args.out_dir, "bindings.h"), "w", encoding="utf-8") as handle:
        handle.write("\n\n".join(c_lines))

    # ---- C++ 版本 ----
    cpp_lines = [
        "// 由 gen_bindings.py 从 BTF 自动生成，不要手改",
        "#pragma once",
        "#include <stddef.h>",
        "",
        f"namespace {args.namespace} {{",
        "",
    ]
    for name in sorted(deps.fwd_records | deps.want_records):
        decl = records.get(name)
        if decl is not None and decl.kind != ci.CursorKind.ENUM_DECL:
            keyword = "struct" if decl.kind == ci.CursorKind.STRUCT_DECL else "union"
            cpp_lines.append(f"{keyword} {cpp_type_name(name)};")
    cpp_lines.append("")
    for name in sorted(deps.want_enums):
        cpp_lines.append(types.gen_enum(deps.want_enums[name], cpp_type_name, True))
    for kind, name in order:
        if kind == "typedef":
            if name in CPP_GLOBAL_TYPEDEFS and name in deps.typedefs:
                continue
            if name in deps.typedefs:
                cpp_lines.append(types.gen_typedef(deps.typedefs[name], cpp_type_name,
                                                   cpp_field_name, True))
        else:
            cpp_lines.append(types.gen_record(records[name], cpp_type_name,
                                              cpp_field_name, True))
    # C++ 和 C 的空结构体大小不同；C++ 侧也要按 BTF 校验，否则 C 的
    # layout_check 通过、C++ 镜像却可能把后续字段整体顶歪
    for name in sorted(deps.want_records):
        entry = named_layout.get(name)
        if entry is None:
            continue
        cpp_lines.append(
            f'static_assert(sizeof({cpp_type_name(name)}) == {entry["size"]}, '
            f'"size {name}");')
    cpp_lines.append("")
    # C++ 侧约定不包含内核头；这些常量与内核宏同名，如果破坏约定就会
    # 被预处理器替换成 linuxcpp::1，所以约束是“不要 include 内核头”，不是改常量名
    for name, value in macro_defs:
        cpp_lines.append(f"inline constexpr auto {name} = {value};")
    if macro_defs:
        cpp_lines.append("")
    cpp_lines.append('extern "C" {')
    base_externs = [] if args.extern else DEFAULT_EXTERN_FUNCS
    for func in base_externs + extern_decls + MANUAL_THUNK_FUNCS + thunk_decls:
        cpp_lines.append("    " + func)
    cpp_lines.append("}")
    cpp_lines.append("")
    cpp_lines.append(f"}}  // namespace {args.namespace}")

    with open(os.path.join(args.out_dir, "bindings.hpp"), "w", encoding="utf-8") as handle:
        handle.write("\n\n".join(cpp_lines))

    # ---- 布局校验 ----
    if getattr(args, "all", False):
        check_lines = btf_layout_check(args, records, deps, roots, btf_info)
    else:
        layout_headers = list(dict.fromkeys((args.headers or []) + [
            "linux/types.h", "linux/stddef.h", "linux/kobject.h",
            "linux/device.h", "linux/fs.h", "linux/miscdevice.h", "linux/uio.h",
            "linux/mutex.h",
        ]))
        check_lines = [
            "/* 由 gen_bindings.py 从 BTF 自动生成，不要手改 */",
        ]
        check_lines += [f"#include <{header}>" for header in layout_headers]
        check_lines += ['#include "generated/bindings.h"', ""]
        for name in roots:
            decl = records.get(name)
            if decl is None:
                # typedef 根没有 record 游标，至少校验它的大小
                if name in deps.typedefs:
                    check_lines.append(
                        f'_Static_assert(sizeof({name}) == sizeof({args.prefix}{name}), '
                        f'"size {name}");')
                continue
            keyword = "struct" if decl.kind == ci.CursorKind.STRUCT_DECL else "union"
            # BTF 里很多 record 是 typedef 的匿名 struct（如 atomic_t），没有 struct 标签；
            # 有同名 typedef 时必须用 typedef 名，否则 sizeof/offsetof 会报不完整类型
            c_ref = name if name in typedefs else f"{keyword} {name}"
            g_ref = f"{keyword} {args.prefix}{name}"
            check_lines.append(
                f'_Static_assert(sizeof({c_ref}) == sizeof({g_ref}), "size {name}");')
            for field in layout_fields(decl):
                check_lines.append(
                    f'_Static_assert(offsetof({c_ref}, {field.spelling}) == '
                    f'offsetof({g_ref}, {field.spelling}), '
                    f'"offset {name}.{field.spelling}");')
            check_lines.append("")
        for name in sorted(deps.want_enums):
            c_ref = name if name in typedefs else f"enum {name}"
            check_lines.append(
                f'_Static_assert(sizeof({c_ref}) == sizeof(enum {args.prefix}{name}), '
                f'"size enum {name}");')
    with open(os.path.join(args.work_dir, "layout_check.c"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(check_lines))

    # 即使没有 thunk 也写一个空文件，Kbuild 的对象列表可以保持不变
    headers = list(dict.fromkeys((args.headers or []) + DEFAULT_HEADERS))
    parts = ["// 由 gen_bindings.py 自动生成，不要手改"]
    parts += [f"#include <{header}>" for header in headers]
    parts += thunk_prototypes
    parts += thunk_sources
    with open(os.path.join(args.work_dir, "thunks_gen.c"), "w", encoding="utf-8") as handle:
        handle.write("\n\n".join(parts) + "\n")

    print(f"记录 {len(deps.want_records)}，typedef {len(deps.want_typedefs)}，"
          f"枚举 {len(deps.want_enums)}，前向声明 {len(deps.fwd_records - deps.want_records)}，"
          f"自动 thunk {len(thunk_sources)}")
