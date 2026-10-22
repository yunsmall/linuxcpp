"""生成器共享的常量和命名映射。"""

import clang.cindex as ci

ROOTS = ["miscdevice", "file_operations", "kiocb", "iov_iter", "file", "mutex"]

# 这些标识符在 C++ 里是关键字，作为类型名或字段名时需要改名。
# bool/wchar_t/char8_t 等内置类型名不在此列，否则会把类型本身也改名。
CPP_KEYWORDS = {
    "alignas", "alignof", "and", "and_eq", "asm", "auto", "bitand", "bitor",
    "break", "case", "catch", "class", "compl", "concept", "const", "consteval",
    "constexpr", "constinit", "const_cast", "continue", "co_await", "co_return",
    "co_yield", "decltype", "default", "delete", "do", "double", "dynamic_cast",
    "else", "enum", "explicit", "export", "extern", "false", "float", "for",
    "friend", "goto", "if", "inline", "int", "long", "mutable", "namespace",
    "new", "noexcept", "not", "not_eq", "nullptr", "operator", "or", "or_eq",
    "private", "protected", "public", "register", "reinterpret_cast", "requires",
    "return", "short", "signed", "sizeof", "static", "static_assert",
    "static_cast", "struct", "switch", "template", "this", "thread_local",
    "throw", "true", "try", "typedef", "typeid", "typename", "union",
    "unsigned", "using", "virtual", "void", "volatile", "while", "xor", "xor_eq",
}

DEFAULT_EXTERN_FUNCS = [
    "int misc_register(miscdevice *misc);",
    "void misc_deregister(miscdevice *misc);",
    "size_t _copy_to_iter(const void *addr, size_t bytes, iov_iter *i);",
    "size_t _copy_from_iter(void *addr, size_t bytes, iov_iter *i);",
]

DEFAULT_HEADERS = [
    "linux/module.h", "linux/fs.h", "linux/miscdevice.h",
    "linux/uio.h", "linux/slab.h", "linux/uaccess.h",
]

# 宏形式的接口 libclang 拿不到函数定义，只能手写
MANUAL_THUNK_FUNCS = [
    "void *lc_kmalloc(size_t size);",
    "void lc_kfree(void *ptr);",
    "void lc_might_sleep(void);",
    "void *lc_this_module(void);",
]

# 核心库和用户代码都常用的对象宏，总是从内核头导出，值不做假设
CORE_MACROS = [
    "MISC_DYNAMIC_MINOR", "MAX_ERRNO",
    "EPERM", "ENOENT", "ESRCH", "EINTR", "EIO", "ENXIO", "E2BIG", "ENOEXEC",
    "EBADF", "ECHILD", "EAGAIN", "ENOMEM", "EACCES", "EFAULT", "ENOTBLK",
    "EBUSY", "EEXIST", "EXDEV", "ENODEV", "ENOTDIR", "EISDIR", "EINVAL",
    "ENFILE", "EMFILE", "ENOTTY", "ETXTBSY", "EFBIG", "ENOSPC", "ESPIPE",
    "EROFS", "EMLINK", "EPIPE", "EDOM", "ERANGE", "EDEADLK", "ENAMETOOLONG",
    "ENOLCK", "ENOSYS", "ENOTEMPTY", "ELOOP",
]

RECORD_KINDS = (ci.CursorKind.STRUCT_DECL, ci.CursorKind.UNION_DECL, ci.CursorKind.ENUM_DECL)


def c_type_name(name, prefix):
    return prefix + name


def cpp_type_name(name):
    return name + "_" if name in CPP_KEYWORDS else name


def cpp_field_name(name):
    return name + "_" if name in CPP_KEYWORDS else name
