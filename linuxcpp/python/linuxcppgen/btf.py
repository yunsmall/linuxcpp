"""BTF 导出、缓存和 vmlinux.h 解析。"""

import glob
import json
import os
import shutil
import subprocess
import sys

import clang.cindex as ci


def bpftool_candidates():
    """系统里的 bpftool wrapper 按内核版本找二进制，自编内核找不到；
    直接扫 /usr/lib/linux-tools/*/bpftool 下的真实二进制。"""
    cands = sorted(glob.glob("/usr/lib/linux-tools/*/bpftool"))
    which = shutil.which("bpftool")
    if which:
        cands.append(which)
    return cands


def cache_id(btf_path):
    """缓存标识：内核 release + BTF 文件大小/时间，换内核后旧缓存必须失效"""
    release = os.uname().release
    try:
        stat = os.stat(btf_path)
        return f"{release}:{stat.st_size}:{stat.st_mtime_ns}"
    except OSError:
        return release


def dump_btf(out_dir, btf_path):
    vmlinux_h = os.path.join(out_dir, "vmlinux.h")
    meta = vmlinux_h + ".meta"
    want = cache_id(btf_path)
    if os.path.exists(vmlinux_h) and os.path.getsize(vmlinux_h) > 0:
        try:
            with open(meta, encoding="utf-8") as handle:
                if handle.read().strip() == want:
                    return vmlinux_h
        except OSError:
            pass
    os.makedirs(out_dir, exist_ok=True)
    for bpftool in bpftool_candidates():
        try:
            out = subprocess.run(
                [bpftool, "btf", "dump", "file", btf_path, "format", "c"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError):
            continue
        if out:
            with open(vmlinux_h, "wb") as handle:
                handle.write(out)
            with open(meta, "w", encoding="utf-8") as handle:
                handle.write(want + "\n")
            return vmlinux_h
    sys.exit("找不到可用的 bpftool，请先安装或手动提供 generated/vmlinux.h")


def dump_btf_json(out_dir, btf_path):
    """bpftool 的 JSON 输出带 size 和成员 bit offset，全量布局校验不需要内核内部头"""
    raw_path = os.path.join(out_dir, "vmlinux.btf.json")
    meta = raw_path + ".meta"
    want = cache_id(btf_path)
    if os.path.exists(raw_path) and os.path.getsize(raw_path) > 0:
        try:
            with open(meta, encoding="utf-8") as handle:
                if handle.read().strip() == want:
                    return raw_path
        except OSError:
            pass
    os.makedirs(out_dir, exist_ok=True)
    for bpftool in bpftool_candidates():
        try:
            out = subprocess.run(
                [bpftool, "-j", "btf", "dump", "file", btf_path, "format", "raw"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError):
            continue
        if out:
            with open(raw_path, "wb") as handle:
                handle.write(out)
            with open(meta, "w", encoding="utf-8") as handle:
                handle.write(want + "\n")
            return raw_path
    sys.exit("找不到可用的 bpftool，无法导出 BTF JSON")


class BtfInfo(dict):
    """按名字分组的 record/enum 表，附带匿名类型和 typedef 的完整索引。

    生成器需要按 BTF 的 offset/size 还原 bpftool 丢了 packed 的类型，
    这些信息只能从原始 type_id 里取，不能只看名字。
    """

    def __init__(self, groups, by_id, typedefs):
        super().__init__(groups)
        self.by_id = by_id
        self.typedefs = typedefs


def parse_btf_json(raw_path):
    """返回 BtfInfo：名字 -> record 列表，id -> 任意类型，typedef 名 -> type_id 列表"""
    with open(raw_path, encoding="utf-8") as handle:
        data = json.load(handle)
    groups = {}
    by_id = {}
    typedefs = {}
    for entry in data.get("types", []):
        type_id = entry.get("id")
        kind = entry.get("kind")
        if type_id is not None:
            members = [
                (member.get("name", ""), member.get("bits_offset", 0),
                 member.get("bitfield_size"), member.get("type_id"))
                for member in entry.get("members", [])
            ]
            by_id[type_id] = {
                "id": type_id, "kind": kind, "name": entry.get("name", ""),
                "size": entry.get("size", 0),
                "encoding": entry.get("encoding"), "members": members,
                # bpftool raw JSON 的字段名是 type_id/nr_elems，不是 type/nelems
                "type_id": entry.get("type_id"),
                "index_type_id": entry.get("index_type_id"),
                "nelems": entry.get("nr_elems"),
            }
        if kind == "TYPEDEF" and entry.get("name") and entry.get("type_id") is not None:
            typedefs.setdefault(entry["name"], []).append(entry["type_id"])
        name = entry.get("name")
        if not name or name == "(anon)" or kind not in ("STRUCT", "UNION", "ENUM"):
            continue
        # 缺 id 的条目没法参与布局计算，跳过而不是 KeyError
        if type_id is None or type_id not in by_id:
            continue
        groups.setdefault(name, []).append(by_id[type_id])
    return BtfInfo(groups, by_id, typedefs)


def parse_header(vmlinux_h):
    """用 libclang 解析 vmlinux.h，返回顶层声明表"""
    index = ci.Index.create()
    tu = index.parse(vmlinux_h, args=["-x", "c", "-std=gnu11", "-Wno-unknown-attributes"])
    errors = [diag for diag in tu.diagnostics
              if diag.severity >= ci.Diagnostic.Error]
    if errors:
        for diag in errors[:10]:
            print(f"{diag.location}: {diag.spelling}", file=sys.stderr)
        sys.exit(f"vmlinux.h 解析失败: {len(errors)} 个错误")
    records = {}
    typedefs = {}
    enums = {}
    for cursor in tu.cursor.get_children():
        loc = cursor.location.file
        if not loc or os.path.basename(loc.name) != "vmlinux.h":
            continue
        if cursor.kind in (ci.CursorKind.STRUCT_DECL, ci.CursorKind.UNION_DECL):
            # 匿名结构体只作为父类型的成员存在，不单独登记
            if cursor.spelling and not cursor.is_anonymous():
                records[cursor.spelling] = cursor
        elif cursor.kind == ci.CursorKind.ENUM_DECL:
            if cursor.spelling:
                enums[cursor.spelling] = cursor
        elif cursor.kind == ci.CursorKind.TYPEDEF_DECL:
            if cursor.spelling:
                typedefs[cursor.spelling] = cursor
    return records, typedefs, enums


def kernel_include_flags(kdir):
    """解析内核头只需要 include 路径和配置头，用不到 kbuild 的全套参数"""
    src = os.path.realpath(kdir)
    # 交叉编译时允许用 ARCH 覆盖宿主架构
    machine = os.environ.get("ARCH") or os.uname().machine
    arch = {
        "x86_64": "x86", "i386": "x86", "i486": "x86", "i586": "x86", "i686": "x86",
        "aarch64": "arm64", "armv7l": "arm", "armv8l": "arm",
        "riscv64": "riscv", "riscv32": "riscv",
        "ppc64le": "powerpc", "ppc64": "powerpc", "ppc": "powerpc",
        "s390x": "s390", "mips64": "mips", "mips64el": "mips", "mips": "mips",
    }.get(machine, machine)
    gccinc = subprocess.check_output(["gcc", "-print-file-name=include"], text=True).strip()
    return [
        "-x", "c", "-std=gnu11", "-nostdinc", "-Wno-everything",
        # 内核用 -fshort-wchar -funsigned-char 编译，libclang 解析时也要一致，
        # 否则 wchar_t/char 的大小和符号性会和实际内核布局对不上
        "-fshort-wchar", "-funsigned-char",
        f"-I{src}/arch/{arch}/include", f"-I{src}/arch/{arch}/include/generated",
        f"-I{src}/include", f"-I{src}/arch/{arch}/include/uapi",
        f"-I{src}/arch/{arch}/include/generated/uapi", f"-I{src}/include/uapi",
        f"-I{src}/include/generated/uapi", "-isystem", gccinc,
        "-include", f"{src}/include/linux/compiler-version.h",
        "-include", f"{src}/include/linux/kconfig.h",
        "-D__KERNEL__", "-DMODULE",
    ]
