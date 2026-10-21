"""把 libclang 类型生成为 C/C++ 声明。"""

import os

import clang.cindex as ci

from .config import cpp_field_name, cpp_type_name

# parse_header 得到的 record 表，gen_type 需要用它判断同名 typedef
RECORDS = {}

# 全量模式下从 BTF 推断出必须加 packed 的类型名（vmlinux.h 可能漏掉 __packed）
BTF_PACKED = set()

# BTF 布局表：bpftool 会漏掉 __packed，导致 vmlinux.h 的自然布局和内核不一致。
# 这些类型必须按 BTF 的 bit offset 重新生成，不能照抄 clang 算出来的偏移。
BTF_RECORDS = {}     # 具名 record -> BTF 条目
BTF_ANON = {}        # 匿名 record 的 USR -> BTF 条目
BTF_BY_ID = {}       # type_id -> BTF 条目
BTF_TYPEDEFS = {}    # typedef 名 -> type_id
NATURAL_LAYOUT = {}  # type_id -> (是否自然布局, 对齐字节数)；None 表示含位域无法推断
POINTER_BYTES = None  # 内核的指针宽度，从 BTF 的 long 类型推断


def set_records(records):
    global RECORDS
    RECORDS = records


def set_btf_packed(names):
    global BTF_PACKED
    BTF_PACKED = names


def set_btf_layout(records, anon, by_id, typedefs):
    global BTF_RECORDS, BTF_ANON, BTF_BY_ID, BTF_TYPEDEFS, POINTER_BYTES
    BTF_RECORDS, BTF_ANON = records, anon
    BTF_BY_ID, BTF_TYPEDEFS = by_id, typedefs
    NATURAL_LAYOUT.clear()
    POINTER_BYTES = None


def btf_pointer_bytes():
    """内核指针宽度等于 long；交叉编译 32 位内核时不能写死 8"""
    global POINTER_BYTES
    if POINTER_BYTES is not None:
        return POINTER_BYTES
    names = ("long unsigned int", "long int", "unsigned long", "long", "size_t")
    best = None
    best_rank = len(names)
    for candidate in BTF_BY_ID.values():
        if candidate["kind"] != "INT" or candidate["name"] not in names:
            continue
        rank = names.index(candidate["name"])
        if rank < best_rank:
            best, best_rank = candidate, rank
    if best is not None:
        POINTER_BYTES = best["size"]
        return POINTER_BYTES
    # BTF 被裁剪过时按目标架构兜底；32 位架构的指针是 4 字节
    arch = os.environ.get("ARCH") or os.uname().machine
    if arch in ("i386", "i486", "i586", "i686", "arm", "armv7l",
                "armv8l", "riscv32", "ppc"):
        return 4
    if arch:
        return 8
    return None


def is_padding_field(field):
    """bpftool 为了保留 BTF 里的空洞补的无名位域，BTF members 中没有对应项"""
    width = field.get_bitfield_width()
    return not field.spelling and width is not None and width >= 0


def btf_entry_for(decl):
    if decl.is_anonymous():
        return BTF_ANON.get(decl.get_usr())
    return BTF_RECORDS.get(decl.spelling) or BTF_ANON.get(decl.get_usr())


def btf_size_bytes(type_id, depth=0):
    """按 BTF type_id 求大小；指针宽度取内核的 long，交叉编译的 32 位内核也能对上"""
    entry = BTF_BY_ID.get(type_id)
    if entry is None or depth > 32:
        return None
    kind = entry["kind"]
    if kind in ("STRUCT", "UNION", "ENUM", "INT", "FLOAT", "ENUM64"):
        return entry["size"]
    if kind in ("TYPEDEF", "CONST", "VOLATILE", "RESTRICT", "TYPE_TAG"):
        return btf_size_bytes(entry["type_id"], depth + 1)
    if kind == "PTR":
        return btf_pointer_bytes()
    if kind == "ARRAY":
        element = btf_size_bytes(entry["type_id"], depth + 1)
        if element is None or entry["nelems"] is None:
            return None
        return element * entry["nelems"]
    return None


def align_up(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def scalar_align(size):
    """标量的自然对齐；32 位 x86 的 long long/double 只按 4 对齐"""
    if size >= 16:
        return 16
    if size == 8:
        arch = os.environ.get("ARCH") or os.uname().machine
        if btf_pointer_bytes() == 4 and arch in ("x86", "i386", "i486", "i586", "i686"):
            return 4
        return 8
    return max(1, size)


def btf_align_bytes(type_id, depth=0):
    """从 BTF 推算类型的自然对齐；布局本身不自然的 record 按 packed 处理"""
    entry = BTF_BY_ID.get(type_id)
    if entry is None or depth > 64:
        return None
    kind = entry["kind"]
    if kind == "PTR":
        size = btf_size_bytes(type_id)
        return size
    if kind in ("INT", "ENUM", "FLOAT", "ENUM64"):
        return scalar_align(entry["size"])
    if kind in ("TYPEDEF", "CONST", "VOLATILE", "RESTRICT", "TYPE_TAG"):
        return btf_align_bytes(entry["type_id"], depth + 1)
    if kind == "ARRAY":
        return btf_align_bytes(entry["type_id"], depth + 1)
    if kind in ("STRUCT", "UNION"):
        natural = natural_record_layout(type_id, entry, depth + 1)
        return None if natural[0] is None else natural[1]
    return None


def natural_record_layout(type_id, entry, depth=0):
    """按 C 的自然对齐规则模拟布局，判断 BTF 里的 record 是不是 packed。

    返回 (是否自然, 对齐字节数)；含位域时无法可靠模拟，返回 (None, None)。
    """
    if type_id in NATURAL_LAYOUT:
        return NATURAL_LAYOUT[type_id]
    NATURAL_LAYOUT[type_id] = (None, None)  # 防递归占位
    kind = entry["kind"]
    members = entry["members"]
    if any(member[2] is not None for member in members):
        return NATURAL_LAYOUT[type_id]
    union = kind == "UNION"
    cursor = 0
    max_align = 1
    natural = True
    for member in members:
        size = btf_size_bytes(member[3])
        align = btf_align_bytes(member[3], depth + 1)
        if size is None or align is None:
            natural = None
            break
        max_align = max(max_align, align)
        if union:
            cursor = max(cursor, size * 8)
        else:
            expected = align_up(member[1], align * 8)
            if expected != member[1]:
                natural = False
                break
            cursor = member[1] + size * 8
    if natural is True:
        expected_size = align_up(cursor, max_align * 8) // 8
        if expected_size != entry["size"]:
            natural = False
    result = (natural, max_align if natural else 1)
    NATURAL_LAYOUT[type_id] = result
    return result


def clang_layout_needs_repair(decl, entry):
    """含位域时无法从 BTF 模拟自然布局，退回用 clang 的解析结果判断"""
    fields = [field for field in decl.type.get_fields() if not is_padding_field(field)]
    members = entry["members"]
    if len(fields) != len(members):
        return False
    if decl.type.get_size() != entry["size"]:
        return True
    for field, member in zip(fields, members):
        if field.get_field_offsetof() != member[1]:
            return True
        width = field.get_bitfield_width()
        if width is not None and width >= 0:
            if member[2] is None or width != member[2]:
                return True
        elif member[2] is not None:
            return True
    return False


def member_bits(field, member):
    size = btf_size_bytes(member[3])
    if size is None:
        size = field.type.get_size()
    return size * 8


def layout_needs_repair(decl, entry):
    """BTF 声明的布局不符合 C 自然对齐时必须按 BTF 偏移重建。

    先用 BTF 自己推，避免拿 clang 解析 vmlinux.h 的结果当依据；
    只有含位域、无法模拟时才退回 clang。
    """
    if entry is None or entry["kind"] not in ("STRUCT", "UNION"):
        return False
    natural, _ = natural_record_layout(entry["id"], entry)
    if natural is not None:
        return not natural
    return clang_layout_needs_repair(decl, entry)


def custom_layout_usable(decl, entry):
    """显式 padding 只能处理字节对齐、没有位域的字段；位域的实际分配由编译器决定"""
    fields = [field for field in decl.type.get_fields() if not is_padding_field(field)]
    if len(fields) != len(entry["members"]):
        return False
    for field, member in zip(fields, entry["members"]):
        if member[1] % 8 or member[2] is not None:
            return False
        width = field.get_bitfield_width()
        if width is not None and width >= 0:
            return False
    return True


def record_plan(decl):
    """返回按 BTF 重建所需的 (entry, align, tail_bytes)。

    entry 非空表示要加 packed 并按 BTF 偏移插 padding；align 是还原出的
    自然对齐，tail_bytes 是无法用对齐解释时补的尾部字节数。
    """
    entry = btf_entry_for(decl)
    if not layout_needs_repair(decl, entry) or not custom_layout_usable(decl, entry):
        return None, 1, 0
    fields = [field for field in decl.type.get_fields() if not is_padding_field(field)]
    union = decl.kind == ci.CursorKind.UNION_DECL
    end = 0
    for field, member in zip(fields, entry["members"]):
        start = 0 if union else member[1]
        if not union and start < end:
            return None, 1, 0  # 字段在 BTF 里相互重叠，不是普通 struct
        end = max(end, start + member_bits(field, member))
    size_bits = entry["size"] * 8
    if end > size_bits or end % 8:
        return None, 1, 0
    end_bytes = end // 8
    # 真实类型可能是 packed + aligned(N)：找最小的 N 让大小刚好等于 BTF size
    align = 0
    for candidate in (1 << shift for shift in range(13)):
        if (end_bytes + candidate - 1) // candidate * candidate == entry["size"]:
            align = candidate
            break
    if align:
        return entry, align, 0
    if size_bits > end:
        return entry, 1, entry["size"] - end_bytes
    return None, 1, 0


def record_attr(decl, plan):
    entry, align, _ = plan
    packed = is_packed(decl) or decl.spelling in BTF_PACKED or entry is not None
    if not packed:
        return ""
    if entry is not None and align > 1:
        return f" __attribute__((packed, aligned({align})))"
    return " __attribute__((packed))"


def gen_type(t, mapper, cpp):
    """把一个 clang Type 生成为 C/C++ 类型拼写；匿名记录返回 None"""
    kind = t.kind
    qual = ""
    if kind != ci.TypeKind.POINTER:
        if t.is_const_qualified():
            qual += "const "
        if t.is_volatile_qualified():
            qual += "volatile "

    if kind == ci.TypeKind.POINTER:
        pointee = t.get_pointee()
        if pointee.kind == ci.TypeKind.FUNCTIONPROTO:
            return gen_func_pointer(pointee, "", mapper, cpp)
        inner = gen_type(pointee, mapper, cpp)
        if inner is None:
            return None
        suffix = ""
        if t.is_const_qualified():
            suffix += " const"
        if t.is_volatile_qualified():
            suffix += " volatile"
        return f"{inner} *{suffix}"
    if kind == ci.TypeKind.CONSTANTARRAY:
        inner = gen_type(t.element_type, mapper, cpp)
        if inner is None:
            return None
        return f"{inner}[{t.element_count}]"
    if kind == ci.TypeKind.INCOMPLETEARRAY:
        inner = gen_type(t.element_type, mapper, cpp)
        if inner is None:
            return None
        return f"{inner}[]"
    if kind == ci.TypeKind.ELABORATED:
        decl = t.get_declaration()
        if decl.is_anonymous():
            return None
        if decl.kind == ci.CursorKind.TYPEDEF_DECL:
            if decl.spelling in RECORDS:
                keyword = "struct" if RECORDS[decl.spelling].kind == ci.CursorKind.STRUCT_DECL else "union"
                return f"{qual}{keyword} {mapper(decl.spelling)}"
            return f"{qual}{mapper(decl.spelling)}"
        keyword = {
            ci.CursorKind.STRUCT_DECL: "struct",
            ci.CursorKind.UNION_DECL: "union",
            ci.CursorKind.ENUM_DECL: "enum",
        }.get(decl.kind, "struct")
        return f"{qual}{keyword} {mapper(decl.spelling)}"
    if kind == ci.TypeKind.TYPEDEF:
        decl = t.get_declaration()
        # 编译器内置类型不能加 lc_ 前缀
        if decl.spelling.startswith("__builtin_"):
            return decl.spelling
        # typedef struct foo foo; 这种同名别名会被 output_order 跳过，
        # 字段类型直接写成 struct foo，不依赖别名
        if decl.spelling in RECORDS:
            keyword = "struct" if RECORDS[decl.spelling].kind == ci.CursorKind.STRUCT_DECL else "union"
            return f"{qual}{keyword} {mapper(decl.spelling)}"
        return f"{qual}{mapper(decl.spelling)}"
    if kind == ci.TypeKind.ENUM:
        decl = t.get_declaration()
        if decl.is_anonymous():
            return None
        return f"{qual}enum {mapper(decl.spelling)}"
    if kind == ci.TypeKind.RECORD:
        decl = t.get_declaration()
        if decl.is_anonymous():
            return None
        if decl.kind == ci.CursorKind.TYPEDEF_DECL:
            return f"{qual}{mapper(decl.spelling)}"
        keyword = "struct" if decl.kind == ci.CursorKind.STRUCT_DECL else "union"
        return f"{qual}{keyword} {mapper(decl.spelling)}"
    # 基础类型：t.spelling 本身已经带 const/volatile 等限定符
    spelling = t.spelling
    if cpp and spelling == "_Bool":
        spelling = "bool"
    return spelling


def gen_func_pointer(t, name, mapper, cpp):
    result = gen_type(t.get_result(), mapper, cpp)
    params = [gen_type(arg, mapper, cpp) for arg in t.argument_types()]
    if t.is_function_variadic():
        params.append("...")
    return f"{result} (*{name})({', '.join(params) if params else 'void'})"


def is_func_pointer(t):
    return t.kind == ci.TypeKind.POINTER and t.get_pointee().kind == ci.TypeKind.FUNCTIONPROTO


def anon_type_decl(t):
    """匿名 struct/union/enum 的声明，非匿名返回 None"""
    if t.kind in (ci.TypeKind.RECORD, ci.TypeKind.ELABORATED, ci.TypeKind.ENUM):
        decl = t.get_declaration()
        if decl.is_anonymous():
            return decl
    return None


def enum_value_text(value):
    """超过 int 范围的常量加 ULL，避免编译器把裸字面量判成无符号后告警"""
    return f"{value}ULL" if value > 0x7FFFFFFF else str(value)


def enum_constant_name(name, cpp, const_prefix=""):
    """C++ 里枚举常量没有命名空间，关键字必须转义；C 靠 lc_ 前缀区分"""
    if cpp:
        return cpp_field_name(name)
    return const_prefix + name


def gen_enum_body(decl, indent, const_prefix="", cpp=False):
    items = [
        f"{indent}{enum_constant_name(child.spelling, cpp, const_prefix)} = "
        f"{enum_value_text(child.enum_value)}"
        for child in decl.get_children()
        if child.kind == ci.CursorKind.ENUM_CONSTANT_DECL
    ]
    if not items:
        items = [f"{indent}{enum_constant_name('DUMMY', cpp, const_prefix)} = 0"]
    return ",\n".join(items)


def split_declarator(t, name):
    """把类型拆成 (基础类型, 完整声明符)，指针/数组的 * 和 [N] 都放进声明符"""
    layers = []
    cur = t
    while True:
        if cur.kind == ci.TypeKind.POINTER:
            layers.append(("ptr", cur.is_const_qualified()))
            cur = cur.get_pointee()
        elif cur.kind == ci.TypeKind.CONSTANTARRAY:
            layers.append(("array", cur.element_count))
            cur = cur.element_type
        elif cur.kind == ci.TypeKind.INCOMPLETEARRAY:
            layers.append(("array", None))
            cur = cur.element_type
        else:
            break

    decl = name
    # 从外到内展开：指针加前缀，数组加后缀；指针指向数组时用括号
    for kind, arg in layers:
        if kind == "ptr":
            decl = f"* const {decl}" if arg else f"*{decl}"
        elif arg is None:
            decl = f"({decl})[]" if decl.startswith("*") else f"{decl}[]"
        else:
            decl = f"({decl})[{arg}]" if decl.startswith("*") else f"{decl}[{arg}]"
    return cur, decl


def is_packed(decl):
    """packed 结构体不能按自然对齐生成，否则大小和后续字段偏移都会变"""
    return any(child.kind == ci.CursorKind.PACKED_ATTR for child in decl.get_children())


def field_type_name(t):
    """字段的最内层类型名，用于避免 C++ 里字段名与类型名同名"""
    while t.kind in (ci.TypeKind.POINTER, ci.TypeKind.CONSTANTARRAY,
                     ci.TypeKind.INCOMPLETEARRAY):
        t = t.get_pointee() if t.kind == ci.TypeKind.POINTER else t.element_type
    if t.kind in (ci.TypeKind.TYPEDEF, ci.TypeKind.ELABORATED,
                  ci.TypeKind.RECORD, ci.TypeKind.ENUM):
        return t.get_declaration().spelling
    return None


def gen_field(field, mapper, field_mapper, cpp, indent, const_prefix=""):
    # 匿名字段的 spelling 是空或 libclang 生成的伪名字（含 ::/括号），只有合法标识符才是字段名
    name = field_mapper(field.spelling) if field.spelling.isidentifier() else ""
    t = field.type
    # C++ 类作用域内成员名会遮住同名的类型名，后续字段再写这个类型就会解析到成员，
    # 所以字段名和它最内层的类型名相同时必须加后缀，这不是关键字转义
    if cpp and name and field_type_name(t) == field.spelling:
        name += "_"
    if t.kind == ci.TypeKind.FUNCTIONPROTO:
        return f"{indent}{gen_func_pointer(t, name, mapper, cpp)};"
    if is_func_pointer(t):
        return f"{indent}{gen_func_pointer(t.get_pointee(), name, mapper, cpp)};"

    # 函数指针数组：名字必须进入 (*...) 括号
    if t.kind in (ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY) \
            and is_func_pointer(t.element_type):
        fp = t.element_type.get_pointee()
        params = [gen_type(arg, mapper, cpp) for arg in fp.argument_types()]
        if fp.is_function_variadic():
            params.append("...")
        count = f"[{t.element_count}]" if t.kind == ci.TypeKind.CONSTANTARRAY else "[]"
        result = gen_type(fp.get_result(), mapper, cpp)
        return f"{indent}{result} (*{name}{count})({', '.join(params) if params else 'void'});"

    base_type, decl = split_declarator(t, name)
    anon = anon_type_decl(base_type)
    if anon is not None:
        if anon.kind == ci.CursorKind.ENUM_DECL:
            body = gen_enum_body(anon, indent + "    ", const_prefix, cpp)
            # 位域容器的宽度必须跟内核里这个匿名 enum 的实际大小一致，
            # 不能按位域宽度猜最小容器；否则后续字段的偏移会整体错位
            width = field.get_bitfield_width()
            bitfield = width is not None and width >= 0
            bits = f" : {width}" if bitfield else ""
            enum_bits = field.type.get_size() * 8 if field.type.get_size() > 0 else None
            if cpp and bitfield:
                storage_bits, signed = enum_bitfield_storage(anon, width, enum_bits)
                underlying = {
                    (8, True): "signed char", (8, False): "unsigned char",
                    (16, True): "short", (16, False): "unsigned short",
                    (32, True): "int", (32, False): "unsigned int",
                    (64, True): "long long", (64, False): "unsigned long long",
                }[(storage_bits, signed)]
                head, attr = f"enum : {underlying}", ""
            else:
                mode = None
                if not cpp and bitfield:
                    storage_bits, _ = enum_bitfield_storage(anon, width, enum_bits)
                    mode = {8: "__QI__", 16: "__HI__", 32: "__SI__",
                            64: "__DI__"}[storage_bits]
                head = "enum"
                attr = f" __attribute__((mode({mode})))" if mode else ""
            suffix = f" {decl}{bits}" if decl else bits
            return f"{indent}{head} {{\n{body}\n{indent}}}{attr}{suffix};"
        # union 里的匿名 struct 是 GCC/clang 扩展；clang 通过 -fms-extensions 打开
        keyword = "struct" if anon.kind == ci.CursorKind.STRUCT_DECL else "union"
        plan = record_plan(anon)
        body = gen_record_body(anon, mapper, field_mapper, cpp, indent + "    ", const_prefix)
        suffix = f" {decl}" if decl else ""
        attr = record_attr(anon, plan)
        return f"{indent}{keyword} {{\n{body}\n{indent}}}{attr}{suffix};"

    base = gen_type(base_type, mapper, cpp)
    if base is None:
        return f"{indent}{decl};"

    width = field.get_bitfield_width()
    if width is not None and width >= 0:
        return f"{indent}{base} {decl} : {width};"
    return f"{indent}{base} {decl};"


def gen_record_body(decl, mapper, field_mapper, cpp, indent, const_prefix=""):
    plan = record_plan(decl)
    if plan[0] is not None:
        return gen_custom_record_body(decl, plan, mapper, field_mapper, cpp, indent,
                                      const_prefix)
    lines = []
    for field in decl.type.get_fields():
        lines.append(gen_field(field, mapper, field_mapper, cpp, indent, const_prefix))
    return "\n".join(lines)


def gen_custom_record_body(decl, plan, mapper, field_mapper, cpp, indent,
                           const_prefix=""):
    """按 BTF 的 bit offset 显式补 padding，绕开编译器自己的对齐规则"""
    entry, _, tail = plan
    fields = [field for field in decl.type.get_fields() if not is_padding_field(field)]
    union = decl.kind == ci.CursorKind.UNION_DECL
    lines = []
    pos = 0
    pad_index = 0
    for field, member in zip(fields, entry["members"]):
        bits = member[1]
        if not union and bits > pos:
            gap = (bits - pos) // 8
            if gap:
                lines.append(f"{indent}unsigned char __lcpp_pad{pad_index}[{gap}];")
                pad_index += 1
        lines.append(gen_field(field, mapper, field_mapper, cpp, indent, const_prefix))
        if union:
            pos = max(pos, member_bits(field, member))
        else:
            pos = bits + member_bits(field, member)
    if tail:
        lines.append(f"{indent}unsigned char __lcpp_tail[{tail}];")
    return "\n".join(lines)


def gen_record(decl, mapper, field_mapper, cpp, const_prefix=""):
    keyword = "struct" if decl.kind == ci.CursorKind.STRUCT_DECL else "union"
    body = gen_record_body(decl, mapper, field_mapper, cpp, "    ", const_prefix)
    attr = record_attr(decl, record_plan(decl))
    return f"{keyword} {mapper(decl.spelling)} {{\n{body}\n}}{attr};"


def enum_underlying(decl):
    """按 BTF 的大小和枚举值符号选 C++ 底层类型，避免 C/C++ 选择不一致"""
    size = decl.type.get_size()
    if size not in (1, 2, 4, 8):
        size = 4
    values = [child.enum_value for child in decl.get_children()
              if child.kind == ci.CursorKind.ENUM_CONSTANT_DECL]
    if any(value < 0 for value in values):
        return {1: "signed char", 2: "short", 4: "int", 8: "long long"}[size]
    return {1: "unsigned char", 2: "unsigned short", 4: "unsigned int",
            8: "unsigned long long"}[size]


def enum_bitfield_storage(decl, width, storage_bits=None):
    """位域容器的位宽要同时满足位域宽度和枚举常量值域。

    storage_bits 是内核里这个匿名 enum 的实际大小；有它就必须照搬，
    否则 -fno-short-enums 下会把 4 字节的位域单元错生成 1 字节。
    """
    values = [child.enum_value for child in decl.get_children()
              if child.kind == ci.CursorKind.ENUM_CONSTANT_DECL]
    signed = any(value < 0 for value in values)
    need = max(width or 0, 1)
    if signed:
        ranges = ((8, -128, 127), (16, -32768, 32767),
                  (32, -2147483648, 2147483647),
                  (64, -9223372036854775808, 9223372036854775807))
    else:
        ranges = ((8, 0, 255), (16, 0, 65535), (32, 0, 4294967295),
                  (64, 0, 18446744073709551615))
    if storage_bits in (8, 16, 32, 64) and storage_bits >= need:
        for bits, low, high in ranges:
            if bits == storage_bits and all(low <= value <= high for value in values):
                return storage_bits, signed
    for bits, low, high in ranges:
        if need <= bits and all(low <= value <= high for value in values):
            return bits, signed
    return 64, signed


def gen_enum(decl, mapper, cpp=False, const_prefix=""):
    name = mapper(decl.spelling)
    items = [
        f"    {enum_constant_name(child.spelling, cpp, const_prefix)} = "
        f"{enum_value_text(child.enum_value)}"
        for child in decl.get_children()
        if child.kind == ci.CursorKind.ENUM_CONSTANT_DECL
    ]
    # 空枚举在 C 里不合法，BTF 偶尔会导出只有前向声明的 enum
    if not items:
        items = [f"    {name}_DUMMY = 0"]
    if not cpp:
        # C 没有 enum : type；按 BTF 的实际大小用 mode 属性固定宽度，
        # 否则默认 int 会把后面的字段偏移全部推歪
        mode = {1: "__QI__", 2: "__HI__", 4: "__SI__", 8: "__DI__"}.get(
            decl.type.get_size())
        attr = f" __attribute__((mode({mode})))" if mode else ""
        return f"enum {name} {{\n{',\n'.join(items)}\n}}{attr};"
    lines = [
        f"enum {name} : {enum_underlying(decl)} {{",
        ",\n".join(items),
        "};",
    ]
    size = decl.type.get_size()
    if size > 0:
        lines.append(f'static_assert(sizeof({name}) == {size}, "enum {name} size");')
    return "\n".join(lines)


def array_typedef(t, name, mapper, cpp):
    """数组 typedef 的名字要进入声明符，支持多维和函数指针元素"""
    if t.kind == ci.TypeKind.CONSTANTARRAY:
        return array_typedef(t.element_type, f"{name}[{t.element_count}]", mapper, cpp)
    if t.kind == ci.TypeKind.INCOMPLETEARRAY:
        return array_typedef(t.element_type, f"{name}[]", mapper, cpp)
    if is_func_pointer(t):
        return gen_func_pointer(t.get_pointee(), name, mapper, cpp)
    return f"{gen_type(t, mapper, cpp)} {name}"


def gen_typedef(decl, mapper, field_mapper, cpp, const_prefix=""):
    name = mapper(decl.spelling)
    underlying = decl.underlying_typedef_type

    # 匿名 record 可能被指针/数组包着，split_declarator 会把 * 和 [N] 放进名字
    base, declarator = split_declarator(underlying, name)
    anon = anon_type_decl(base)
    if anon is not None:
        if anon.kind == ci.CursorKind.ENUM_DECL:
            body = gen_enum_body(anon, "    ", const_prefix, cpp)
            if cpp:
                head, attr = f"enum : {enum_underlying(anon)}", ""
            else:
                mode = {1: "__QI__", 2: "__HI__", 4: "__SI__", 8: "__DI__"}.get(
                    anon.type.get_size())
                head, attr = "enum", f" __attribute__((mode({mode})))" if mode else ""
            return f"typedef {head} {{\n{body}\n}}{attr} {declarator};"
        keyword = "struct" if anon.kind == ci.CursorKind.STRUCT_DECL else "union"
        inner = gen_record_body(anon, mapper, field_mapper, cpp, "    ", const_prefix)
        attr = record_attr(anon, record_plan(anon))
        return f"typedef {keyword} {{\n{inner}\n}}{attr} {declarator};"

    if underlying.kind in (ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY):
        return f"typedef {array_typedef(underlying, name, mapper, cpp)};"
    if underlying.kind == ci.TypeKind.FUNCTIONPROTO:
        params = [gen_type(arg, mapper, cpp) for arg in underlying.argument_types()]
        if underlying.is_function_variadic():
            params.append("...")
        result = gen_type(underlying.get_result(), mapper, cpp)
        return f"typedef {result} {name}({', '.join(params) if params else 'void'});"
    if underlying.kind == ci.TypeKind.POINTER and underlying.get_pointee().kind == ci.TypeKind.FUNCTIONPROTO:
        return f"typedef {gen_func_pointer(underlying.get_pointee(), name, mapper, cpp)};"
    base_type = gen_type(base, mapper, cpp)
    return f"typedef {base_type} {declarator};"


def typedef_array_record(decl):
    """数组 typedef 的元素若是 record，返回该 record 名；元素类型必须完整"""
    t = decl.underlying_typedef_type
    if t.kind not in (ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY):
        return None
    while True:
        if t.kind in (ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY):
            t = t.element_type
        elif t.kind == ci.TypeKind.TYPEDEF:
            t = t.get_declaration().underlying_typedef_type
        elif t.kind == ci.TypeKind.ELABORATED \
                and t.get_declaration().kind == ci.CursorKind.TYPEDEF_DECL:
            t = t.get_declaration().underlying_typedef_type
        else:
            break
    if t.kind == ci.TypeKind.RECORD and t.get_declaration().spelling:
        return t.get_declaration().spelling
    return None


def output_order(deps):
    """typedef 和 record 一起做拓扑排序。

    数组 typedef 依赖 record 的完整定义，而 record 的字段又可能引用 typedef，
    分开排序会出现“typedef 引用了尚未定义的结构体”或“结构体字段用了尚未
    定义的 typedef”，所以两者必须进同一个 DFS。
    """
    order = []
    seen_typedefs = set()
    seen_records = set()

    def collect_typedef_deps(t):
        """typedef 定义里引用到的其他 typedef；按值的 record 只需前向声明"""
        if t.kind == ci.TypeKind.TYPEDEF:
            visit_typedef(t.get_declaration().spelling)
        elif t.kind == ci.TypeKind.POINTER:
            collect_typedef_deps(t.get_pointee())
        elif t.kind in (ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY):
            collect_typedef_deps(t.element_type)
        elif t.kind in (ci.TypeKind.ELABORATED, ci.TypeKind.RECORD, ci.TypeKind.ENUM):
            decl = t.get_declaration()
            if decl.kind == ci.CursorKind.TYPEDEF_DECL:
                visit_typedef(decl.spelling)
            elif decl.kind in (ci.CursorKind.STRUCT_DECL, ci.CursorKind.UNION_DECL) \
                    and decl.is_anonymous():
                # 匿名 record 的字段是按值嵌在 typedef 里的，必须完整定义；
                # 只收集 typedef 依赖会把按值使用的 struct 排到后面
                for field in decl.type.get_fields():
                    visit_value_type(field.type)
        elif t.kind == ci.TypeKind.FUNCTIONPROTO:
            collect_typedef_deps(t.get_result())
            for arg in t.argument_types():
                collect_typedef_deps(arg)

    def visit_typedef(name):
        if name in seen_typedefs or name not in deps.typedefs:
            return
        seen_typedefs.add(name)
        record = typedef_array_record(deps.typedefs[name])
        if record is not None:
            visit_record(record)
        collect_typedef_deps(deps.typedefs[name].underlying_typedef_type)
        order.append(("typedef", name))

    def visit_value_type(t):
        """record 字段按值依赖：typedef 必须已定义、结构体必须已完整"""
        kind = t.kind
        if kind == ci.TypeKind.POINTER:
            pointee = t.get_pointee()
            # 指针目标只需要前向声明，但字段里写的是 typedef 名时，
            # 这个 typedef 本身必须先声明，否则会 unknown type name
            if pointee.kind == ci.TypeKind.TYPEDEF:
                visit_typedef(pointee.get_declaration().spelling)
            elif pointee.kind == ci.TypeKind.ELABORATED \
                    and pointee.get_declaration().kind == ci.CursorKind.TYPEDEF_DECL:
                visit_typedef(pointee.get_declaration().spelling)
            elif pointee.kind in (ci.TypeKind.RECORD, ci.TypeKind.ELABORATED):
                decl = pointee.get_declaration()
                if decl.is_anonymous() and decl.kind != ci.CursorKind.ENUM_DECL:
                    for field in decl.type.get_fields():
                        visit_value_type(field.type)
        elif kind in (ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY):
            visit_value_type(t.element_type)
        elif kind == ci.TypeKind.TYPEDEF:
            decl = t.get_declaration()
            visit_typedef(decl.spelling)
            visit_value_type(decl.underlying_typedef_type)
        elif kind in (ci.TypeKind.ELABORATED, ci.TypeKind.RECORD, ci.TypeKind.ENUM):
            decl = t.get_declaration()
            if decl.kind == ci.CursorKind.TYPEDEF_DECL:
                visit_typedef(decl.spelling)
                visit_value_type(decl.underlying_typedef_type)
            elif decl.is_anonymous():
                if decl.kind != ci.CursorKind.ENUM_DECL:
                    for field in decl.type.get_fields():
                        visit_value_type(field.type)
            elif decl.spelling and decl.kind in (ci.CursorKind.STRUCT_DECL,
                                                 ci.CursorKind.UNION_DECL):
                visit_record(decl.spelling)
        elif kind == ci.TypeKind.FUNCTIONPROTO:
            visit_value_type(t.get_result())
            for arg in t.argument_types():
                visit_value_type(arg)

    def visit_record(name):
        if name in seen_records or name not in deps.records:
            return
        seen_records.add(name)
        for field in deps.records[name].type.get_fields():
            visit_value_type(field.type)
        order.append(("record", name))

    for name in sorted(deps.want_typedefs):
        if name in deps.records:
            continue  # typedef struct foo foo; 与 struct 同名，跳过别名
        visit_typedef(name)
    for name in sorted(deps.want_records):
        visit_record(name)
    return order


def with_qualifiers(spelling, t):
    """t.spelling 有时已经带 const/volatile，不能无条件前缀"""
    if t.is_const_qualified() and not spelling.startswith("const"):
        spelling = "const " + spelling
    if t.is_volatile_qualified() and not spelling.startswith("volatile"):
        spelling = "volatile " + spelling
    return spelling


def cpp_func_pointer(t, name, known):
    result = cpp_type(t.get_result(), known)
    params = [cpp_type(arg, known) for arg in t.argument_types()]
    if t.is_function_variadic():
        params.append("...")
    return f"{result} (*{name})({', '.join(params) if params else 'void'})"


def cpp_declarator(t, name, known):
    """把名字放进指针/数组声明符；cpp_type 只负责纯类型拼写"""
    if t.kind == ci.TypeKind.POINTER and t.get_pointee().kind == ci.TypeKind.FUNCTIONPROTO:
        return cpp_func_pointer(t.get_pointee(), name, known)
    base, declarator = split_declarator(t, name)
    return f"{cpp_type(base, known)} {declarator}".strip()


def cpp_param(t, name, known):
    """函数指针、数组和指向数组的指针都要把名字放进声明符"""
    return cpp_declarator(t, name, known)


def cpp_spelling(spelling):
    """处理 struct/union/enum 标签和 C++ 关键字，与生成定义一侧保持一致"""
    for prefix in ("const ", "volatile "):
        if spelling.startswith(prefix):
            return prefix + cpp_spelling(spelling[len(prefix):])
    for keyword in ("struct ", "union ", "enum "):
        if spelling.startswith(keyword):
            return keyword + cpp_type_name(spelling[len(keyword):])
    return cpp_type_name(spelling) if spelling else spelling


def cpp_type(t, known):
    """把 clang 类型翻译成 namespace 内的 C++ 拼写"""
    if t.kind == ci.TypeKind.POINTER:
        pointee = t.get_pointee()
        if pointee.kind == ci.TypeKind.FUNCTIONPROTO:
            return cpp_func_pointer(pointee, "", known)
        if pointee.kind in (ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY):
            return cpp_declarator(t, "", known)
        suffix = ""
        if t.is_const_qualified():
            suffix += " const"
        if t.is_volatile_qualified():
            suffix += " volatile"
        return cpp_type(pointee, known) + " *" + suffix
    if t.kind in (ci.TypeKind.ELABORATED, ci.TypeKind.RECORD, ci.TypeKind.ENUM):
        decl = t.get_declaration()
        spelling = decl.spelling if decl.spelling in known else t.spelling
        return with_qualifiers(cpp_spelling(spelling), t)
    if t.kind == ci.TypeKind.TYPEDEF:
        decl = t.get_declaration()
        spelling = decl.spelling if decl.spelling in known else t.get_canonical().spelling
        return with_qualifiers(cpp_spelling(spelling), t)
    if t.kind == ci.TypeKind.CONSTANTARRAY:
        return cpp_type(t.element_type, known) + f"[{t.element_count}]"
    # 基础类型的 spelling 自带 const/volatile，不能再加一遍
    return "bool" if t.spelling == "_Bool" else t.spelling
