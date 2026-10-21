"""从根类型求 BTF 类型依赖闭包。"""

import clang.cindex as ci

from .config import RECORD_KINDS


class Dependencies:
    """从根类型出发，按 AST 类型关系收集：完整定义的记录、typedef、前向声明"""

    def __init__(self, records, typedefs, enums):
        self.records = records
        self.typedefs = typedefs
        self.enums = enums
        self.want_records = set()
        self.processed_records = set()
        self.want_typedefs = set()
        self.want_enums = {}
        self.fwd_records = set()
        self.visited_typedefs = set()

    def run(self, roots):
        queue = []
        # roots 里可能直接写 enum 或 typedef 名，不能只认 struct/union
        for name in roots:
            # 同名 typedef 只是 struct 的别名，root 必须按完整定义处理，
            # 否则 typedef struct foo foo; 这类根只会拿到别名、不生成结构体
            if name in self.records:
                queue.append(name)
            elif name in self.enums:
                self.want_enums.setdefault(name, self.enums[name])
            elif name in self.typedefs:
                self.visit_typedef(name, queue)
                # root 是按值使用，typedef 的底层类型必须完整；
                # 普通依赖里指针用法仍然只生成前向声明
                self.visit_type(self.typedefs[name].underlying_typedef_type, True, queue)
        while queue:
            name = queue.pop()
            # 不能用 want_records 判断是否处理过：visit_type 会提前登记，
            # 那样队列弹出时就永远不会遍历字段
            if name in self.processed_records or name not in self.records:
                continue
            self.processed_records.add(name)
            self.want_records.add(name)
            for field in self.records[name].type.get_fields():
                self.visit_field(field, queue)

    def visit_field(self, field, queue):
        self.visit_type(field.type, value=True, queue=queue)

    def visit_type(self, t, value, queue):
        kind = t.kind
        if kind == ci.TypeKind.POINTER:
            self.visit_pointer(t.get_pointee(), queue)
        elif kind in (ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY):
            self.visit_type(t.element_type, value, queue)
        elif kind in (ci.TypeKind.ELABORATED, ci.TypeKind.RECORD, ci.TypeKind.ENUM):
            decl = t.get_declaration()
            if decl.kind == ci.CursorKind.TYPEDEF_DECL:
                # libclang 对 typedef 字段经常返回 ELABORATED + typedef 声明
                self.visit_typedef(decl.spelling, queue)
                self.visit_type(decl.underlying_typedef_type, value, queue)
            elif decl.is_anonymous():
                # 匿名 struct/union，字段直接内联在父类型里；enum 没有字段
                if decl.kind != ci.CursorKind.ENUM_DECL:
                    for inner in decl.type.get_fields():
                        self.visit_field(inner, queue)
            elif decl.spelling and decl.kind in RECORD_KINDS:
                if decl.kind == ci.CursorKind.ENUM_DECL:
                    if value:
                        self.want_enums.setdefault(decl.spelling, decl)
                elif value:
                    if decl.spelling not in self.want_records:
                        self.want_records.add(decl.spelling)
                        queue.append(decl.spelling)
                else:
                    self.fwd_records.add(decl.spelling)
        elif kind == ci.TypeKind.TYPEDEF:
            decl = t.get_declaration()
            self.visit_typedef(decl.spelling, queue)
            # 值使用 typedef 时，底层类型也必须完整可见
            if value:
                self.visit_type(decl.underlying_typedef_type, True, queue)
            else:
                self.visit_pointer(decl.underlying_typedef_type, queue)
        elif kind == ci.TypeKind.FUNCTIONPROTO:
            self.visit_type(t.get_result(), value, queue)
            for arg in t.argument_types():
                self.visit_type(arg, value, queue)

    def visit_pointer(self, t, queue):
        kind = t.kind
        if kind == ci.TypeKind.POINTER:
            self.visit_pointer(t.get_pointee(), queue)
        elif kind in (ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY):
            self.visit_pointer(t.element_type, queue)
        elif kind in (ci.TypeKind.ELABORATED, ci.TypeKind.RECORD, ci.TypeKind.ENUM):
            decl = t.get_declaration()
            if decl.kind == ci.CursorKind.TYPEDEF_DECL:
                self.visit_typedef(decl.spelling, queue)
                self.visit_pointer(decl.underlying_typedef_type, queue)
            elif decl.is_anonymous():
                # 指针指向匿名 struct 时字段会被内联生成，字段类型同样是依赖
                if decl.kind != ci.CursorKind.ENUM_DECL:
                    for inner in decl.type.get_fields():
                        self.visit_field(inner, queue)
            elif decl.spelling and decl.kind in RECORD_KINDS:
                if decl.kind == ci.CursorKind.ENUM_DECL:
                    self.want_enums.setdefault(decl.spelling, decl)
                elif decl.spelling not in self.want_records:
                    self.fwd_records.add(decl.spelling)
        elif kind == ci.TypeKind.TYPEDEF:
            decl = t.get_declaration()
            self.visit_typedef(decl.spelling, queue)
            self.visit_pointer(decl.underlying_typedef_type, queue)
        elif kind == ci.TypeKind.FUNCTIONPROTO:
            for arg in t.argument_types():
                self.visit_pointer(arg, queue)
            self.visit_pointer(t.get_result(), queue)

    def visit_typedef(self, name, queue):
        if name in self.want_typedefs:
            return
        self.want_typedefs.add(name)
        if name not in self.visited_typedefs and name in self.typedefs:
            self.visited_typedefs.add(name)
            self.visit_typedef_def(name, queue)

    def visit_typedef_def(self, name, queue):
        """typedef 定义本身只需要被引用类型可见（指针层面），
        但匿名记录 typedef 需要把字段完整带出来"""
        decl = self.typedefs.get(name)
        if decl is None:
            return
        underlying = decl.underlying_typedef_type
        if underlying.kind == ci.TypeKind.RECORD and not underlying.get_declaration().spelling:
            for field in underlying.get_declaration().type.get_fields():
                self.visit_field(field, queue)
        else:
            self.visit_pointer(underlying, queue)
