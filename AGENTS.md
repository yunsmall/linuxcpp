# linuxcpp 项目开发约定

本文件是项目级 agent 说明。`CLAUDE.md` 是指向本文件的软链接，两份内容相同。

## C/C++ 源码分析

**禁止用正则、字符串匹配、逐行文本扫描之类的方式去读取或“解析” C/C++ 源码**，也不要靠文本匹配判断函数签名、类型、宏、调用关系或依赖。C 有预处理、宏、typedef、条件编译，文本匹配会误判，而且会把注释和字符串里的内容当成代码。

需要分析 C/C++ 代码时，用正规前端：

- 结构、声明、类型、调用关系：用 **libclang**（`clang.cindex`）解析 AST。项目里已经有 `linuxcpp/python/linuxcppgen/decls.py`，优先复用。
- 宏和预处理结果：用目标编译器 `-dM -E` 或 `-E`，再按预处理器输出格式读 `#define name value`。这是读预处理结果，不是用正则扫 C 源文件。
- 已编译对象：用 `nm`、`readelf`、`objdump`。
- 绑定生成：继续走 BTF + libclang，不要为了省事改成文本抓取。

如果只需要知道一个宏的值，也走预处理器，不要用正则直接读 `.h`/`.c` 文本。新增生成器或检查脚本时，同样遵守这条规则。

## 构建和测试

- `make runtime`：构建 `linuxcpp/runtime/libcxx_runtime.ko`。
- `make examples`：依次构建 `examples/` 下的模块。
- `make test`：运行 pytest；`make check`：test + examples。
- 单模块：`make -C <模块目录> -j6`。
- 新建模块：`python3 linuxcpp/python/build.py --init <目录>`。
- 并行度最多 6，不要同时跑多个 `-j6` 编译。
- 使用共享 libc++ 的模块加载顺序：先 `insmod linuxcpp/runtime/libcxx_runtime.ko`，再加载模块；卸载反过来。

## 代码风格

- 源码注释用中文，只解释“为什么”，不要写读者看不到的变更历史。
- 缩进跟随现有文件；C++ 一般是 4 空格，Makefile 用 tab。
- 不要提交 `tmp/`、`generated/`、`.o`、`.ko` 等构建产物。
- 修改头文件时优先让构建脚本按目标内核/编译器生成，不要手写死架构相关的类型和错误码。
