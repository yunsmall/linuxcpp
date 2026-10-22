# 仓库级入口：构建共享运行库、示例和测试。
# 单个模块仍然用 make -C <模块目录>，这里只负责常用组合。

PYTHON ?= python3
JOBS ?= 6
LINUXCPP := $(CURDIR)/linuxcpp
EXAMPLES := $(patsubst %/,%,$(wildcard examples/*/))

.PHONY: all runtime examples test check clean help $(EXAMPLES)

all: runtime

runtime:
	+$(MAKE) -C $(LINUXCPP)/runtime $(if $(filter -j%,$(MAKEFLAGS)),,-j$(JOBS))

# libc++ 示例要链接 runtime/Module.symvers，先确保运行库存在
examples: runtime
	+$(MAKE) $(if $(filter -j%,$(MAKEFLAGS)),,-j$(JOBS)) $(EXAMPLES)

$(EXAMPLES):
	$(MAKE) -C $@

test:
	$(PYTHON) -m pytest -q

check: test examples

clean:
	$(MAKE) -C $(LINUXCPP)/runtime clean
	@for dir in $(EXAMPLES); do \
		$(MAKE) -C "$$dir" clean || exit 1; \
	done

help:
	@printf '%s\n' \
		'  make runtime   构建 libcxx_runtime.ko（使用 libc++ 的模块需要先加载它）' \
		'  make examples  并行构建 examples/ 下的模块（会先构建运行库，总并发 JOBS）' \
		'  make test      运行 pytest' \
		'  make check     test + examples' \
		'  make clean     清理运行库和示例'
