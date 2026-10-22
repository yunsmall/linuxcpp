# linuxcpp 模块构建 driver。
#
# 用法：make -C /path/to/linuxcpp M=/path/to/module [KDIR=...]
#
# 模块目录的 Makefile 只做声明；本文件设置 LINUXCPP_BUILD 后再 include 它，
# 模块文件据此跳过自己的 all/clean，目标和规则的所有权始终在 driver 这边。

LINUXCPP := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))

ifeq ($(M),)
$(error 必须指定模块目录：make -C $(LINUXCPP) M=<模块目录>)
endif
M := $(abspath $(M))

# 告诉模块 Makefile：它是被 driver include 的，不要定义入口目标
LINUXCPP_BUILD := 1

KDIR ?= /lib/modules/$(shell uname -r)/build
PYTHON ?= python3
SRC_DIR := $(LINUXCPP)/src
INCLUDE_DIR := $(LINUXCPP)/include
BUILD := $(LINUXCPP)/python/build.py

include $(M)/Makefile

# 模块声明里就算有别的目标，默认目标也必须是构建模块
.DEFAULT_GOAL := all

MODULE_NAME ?= $(notdir $(M))
obj-m := $(MODULE_NAME).o

# 自定义入口由模块 Makefile 覆盖；默认是 build.py 生成的 C 入口
LCPP_ENTRY_OBJ ?= entry_gen.o

# libc++ 运行库对象。只有 libcxx_runtime 模块的 Makefile 会打开 LCPP_LIBCXX，
# 把这份源码编进自己的 ko；其他模块留空，链接时用它的 Module.symvers。
LIBCXX_PATCHED_OBJS := libcxx_string.o libcxx_algorithm.o libcxx_chrono.o
LIBCXX_PORT_OBJS := libcxx_port.o
LIBCXX_UPSTREAM_OBJS := libcxx_any.o libcxx_bind.o \
	libcxx_error_category.o libcxx_exception.o libcxx_functional.o libcxx_hash.o \
	libcxx_memory.o libcxx_memory_resource.o libcxx_new_handler.o \
	libcxx_new_helpers.o libcxx_optional.o libcxx_stdexcept.o \
	libcxx_system_error.o libcxx_typeinfo.o libcxx_valarray.o \
	libcxx_variant.o libcxx_vector.o
LCPP_LIBCXX_OBJS := $(if $(LCPP_LIBCXX),$(LIBCXX_PATCHED_OBJS) $(LIBCXX_PORT_OBJS) $(LIBCXX_UPSTREAM_OBJS))
LCPP_LIBCXX_EXPORT_OBJS := $(if $(LCPP_LIBCXX_EXPORTS),libcxx_exports.o)

# 没写 $(MODULE_NAME)-y 时按模块目录里的源文件推导，和 kbuild 的默认体验一致
$(MODULE_NAME)-y ?= $(patsubst %.cpp,%.o,$(notdir $(wildcard $(M)/*.cpp))) \
	$(patsubst %.c,%.o,$(notdir $(wildcard $(M)/*.c)))

# 用户对象是 $(MODULE_NAME)-y 里除核心/生成对象之外的部分
LCPP_CORE_OBJS := lcpp_ctors_start.o layout_check.o $(LCPP_ENTRY_OBJ) \
	linuxcpp_thunks.o libc_port.o thunks_gen.o lcpp_ctors.o linuxcpp.o device.o \
	$(LCPP_LIBCXX_OBJS) $(LCPP_LIBCXX_EXPORT_OBJS) lcpp_ctors_end.o
LCPP_USER_OBJS := $(filter-out $(LCPP_CORE_OBJS),$($(MODULE_NAME)-y))

# 保持构造/析构数组边界对象的链接顺序
$(MODULE_NAME)-y := lcpp_ctors_start.o layout_check.o $(LCPP_ENTRY_OBJ) \
	linuxcpp_thunks.o libc_port.o thunks_gen.o lcpp_ctors.o linuxcpp.o device.o \
	$(LCPP_LIBCXX_OBJS) $(LCPP_LIBCXX_EXPORT_OBJS) \
	$(LCPP_USER_OBJS) lcpp_ctors_end.o

KO := $(M)/$(MODULE_NAME).ko
STAMP := $(M)/generated/.prepared
CXXFLAGS_MK := $(M)/generated/cxxflags.mk

# 公共 Makefile 负责编译的 C++ 对象：核心库 + 可选的 libc++ 运行时
# libc++ 对象单独一组，避免和核心库的通用模式规则抢同一个目标
CORE_CXX_OBJS := $(addprefix $(M)/,linuxcpp.o device.o)
LIBCXX_CXX_OBJS := $(addprefix $(M)/,$(LCPP_LIBCXX_OBJS))
LIBCXX_SRC_DIR := $(LINUXCPP)/../third_party/libcxx/src
LIBCXX_PORT_SRC := $(LINUXCPP)/libcxx_port/src

# exception.cpp 的 freestanding 实现要用 unexpected_handler。上游靠
# _LIBCPP_BUILDING_LIBRARY 声明它，但那个宏还会打开实验性 PSTL，内核里用不上；
# 这里只打开单独的“保留 C++17 已移除接口”开关。
# 用递归展开：cxxflags.mk 在下面才 include，立即展开会拿到空的 LCPP_CXXFLAGS
LCPP_LIBCXX_CXXFLAGS = $(LCPP_CXXFLAGS) -D_LIBCPP_ENABLE_CXX17_REMOVED_UNEXPECTED_FUNCTIONS
USER_CXX_OBJS := $(addprefix $(M)/, \
	$(filter $(patsubst %.cpp,%.o,$(notdir $(wildcard $(M)/*.cpp))),$(LCPP_USER_OBJS)))
CXX_OBJS := $(CORE_CXX_OBJS) $(LIBCXX_CXX_OBJS) $(USER_CXX_OBJS)
GENERATED_C := entry_gen.c layout_check.c thunks_gen.c linuxcpp_thunks.c \
	libc_port.c lcpp_ctors.c lcpp_ctors_start.c lcpp_ctors_end.c libcxx_exports.c
USER_C_SOURCES := $(filter-out $(GENERATED_C),$(notdir $(wildcard $(M)/*.c)))
USER_SOURCES := $(USER_C_SOURCES) $(notdir $(wildcard $(M)/*.cpp))
PREPARE_DEPS := $(shell find $(LINUXCPP)/python -type f ! -path '*/__pycache__/*' ! -name '*.pyc') \
	$(SRC_DIR)/linuxcpp_thunks.c $(LINUXCPP)/libc_port/src/libc_port.c \
	$(LINUXCPP)/Makefile $(M)/Makefile

# 模块 Makefile 可以像普通外部模块一样设置 KBUILD_EXTRA_SYMBOLS；
# 用到共享 libc++ 时把它指向 runtime/Module.symvers 即可
LCPP_KBUILD_EXTRA = $(if $(KBUILD_EXTRA_SYMBOLS),KBUILD_EXTRA_SYMBOLS="$(KBUILD_EXTRA_SYMBOLS)")

all: $(KO)

-include $(CXXFLAGS_MK)

$(CXXFLAGS_MK): $(STAMP)
	@test -f $@

$(STAMP): $(M)/module.toml $(M)/generated/.sources $(PREPARE_DEPS)
	@mkdir -p $(M)/generated
	@$(PYTHON) $(BUILD) --prepare-only "$(M)" --kdir "$(KDIR)"
	@touch $@
	@touch $(CXXFLAGS_MK)

$(M)/generated/.sources: FORCE
	@mkdir -p $(M)/generated
	@printf '%s\n' '$(USER_SOURCES)' | cmp -s - $@ || printf '%s\n' '$(USER_SOURCES)' > $@

$(CORE_CXX_OBJS): $(M)/%.o: $(SRC_DIR)/%.cpp $(STAMP)
	@echo '  CXX [M] $(notdir $@)'
	@$(CXX) $(LCPP_CXXFLAGS) $(LCPP_LIBCXX_PREFLAGS) $(ccflags-y) $(cxxflags-y) $(CXXFLAGS) -MMD -MP -c -o $@ $<
	@echo 'savedcmd_$(notdir $@) := $(CXX) $(LCPP_CXXFLAGS) $(LCPP_LIBCXX_PREFLAGS) $(ccflags-y) $(cxxflags-y) $(CXXFLAGS) -MMD -MP -c -o $@ $<' > $(M)/.$(notdir $@).cmd

ifneq ($(LCPP_LIBCXX),)
# 打过内核补丁的 libc++ 源文件（去掉浮点入口）在 libcxx_port/src/
$(addprefix $(M)/,$(LIBCXX_PATCHED_OBJS)): \
	$(M)/libcxx_%.o: $(LIBCXX_PORT_SRC)/%.cpp $(STAMP)
	@echo '  CXX [M] $(notdir $@)'
	@$(CXX) $(LCPP_LIBCXX_CXXFLAGS) $(LCPP_LIBCXX_PREFLAGS) $(ccflags-y) $(cxxflags-y) $(CXXFLAGS) -MMD -MP -c -o $@ $<
	@echo 'savedcmd_$(notdir $@) := $(CXX) $(LCPP_LIBCXX_CXXFLAGS) $(LCPP_LIBCXX_PREFLAGS) $(ccflags-y) $(cxxflags-y) $(CXXFLAGS) -MMD -MP -c -o $@ $<' > $(M)/.$(notdir $@).cmd

# 移植层运行时单独命名，避免和名为 libcxx_runtime 的模块聚合对象重名
$(M)/libcxx_port.o: $(LIBCXX_PORT_SRC)/runtime.cpp $(STAMP)
	@echo '  CXX [M] $(notdir $@)'
	@$(CXX) $(LCPP_CXXFLAGS) $(LCPP_LIBCXX_PREFLAGS) $(ccflags-y) $(cxxflags-y) $(CXXFLAGS) -MMD -MP -c -o $@ $<
	@echo 'savedcmd_$(notdir $@) := $(CXX) $(LCPP_CXXFLAGS) $(LCPP_LIBCXX_PREFLAGS) $(ccflags-y) $(cxxflags-y) $(CXXFLAGS) -MMD -MP -c -o $@ $<' > $(M)/.$(notdir $@).cmd

# 未改动的 libc++ 运行库源文件直接用上游的
$(addprefix $(M)/,$(LIBCXX_UPSTREAM_OBJS)): \
	$(M)/libcxx_%.o: $(LIBCXX_SRC_DIR)/%.cpp $(STAMP)
	@echo '  CXX [M] $(notdir $@)'
	@$(CXX) $(LCPP_LIBCXX_CXXFLAGS) $(LCPP_LIBCXX_PREFLAGS) $(ccflags-y) $(cxxflags-y) $(CXXFLAGS) -MMD -MP -c -o $@ $<
	@echo 'savedcmd_$(notdir $@) := $(CXX) $(LCPP_LIBCXX_CXXFLAGS) $(LCPP_LIBCXX_PREFLAGS) $(ccflags-y) $(cxxflags-y) $(CXXFLAGS) -MMD -MP -c -o $@ $<' > $(M)/.$(notdir $@).cmd
endif

ifneq ($(LCPP_LIBCXX_EXPORTS),)
# 从运行库对象里收集全局符号，生成 EXPORT_SYMBOL_GPL 表
$(M)/libcxx_exports.c: $(LIBCXX_CXX_OBJS) $(LINUXCPP)/python/gen_libcxx_exports.py
	@$(PYTHON) $(LINUXCPP)/python/gen_libcxx_exports.py --output $@ $(LIBCXX_CXX_OBJS)
endif

# CXXFLAGS_<对象名> 可以给单个源文件追加参数，例如给用 kernel_fpu_begin()
# 包起来的浮点翻译单元单独打开 SSE
$(USER_CXX_OBJS): $(M)/%.o: $(M)/%.cpp $(STAMP)
	@echo '  CXX [M] $(notdir $@)'
	@$(CXX) $(LCPP_CXXFLAGS) $(LCPP_LIBCXX_PREFLAGS) $(ccflags-y) $(cxxflags-y) $(CXXFLAGS) $(CXXFLAGS_$(@F)) -MMD -MP -c -o $@ $<
	@echo 'savedcmd_$(notdir $@) := $(CXX) $(LCPP_CXXFLAGS) $(LCPP_LIBCXX_PREFLAGS) $(ccflags-y) $(cxxflags-y) $(CXXFLAGS) $(CXXFLAGS_$(@F)) -MMD -MP -c -o $@ $<' > $(M)/.$(notdir $@).cmd

# 模块 Makefile 可能往 $(MODULE_NAME)-y 里加了对象，链接前按最终列表重写 Kbuild
$(KO): $(CXX_OBJS) $(addprefix $(M)/,$(USER_C_SOURCES)) \
	$(if $(LCPP_LIBCXX_EXPORTS),$(M)/libcxx_exports.c) $(STAMP) $(MAKEFILE_LIST)
	@printf 'obj-m := %s.o\n%s-y := %s\nccflags-y += -I%s/generated/libc_port/include -I%s/libc_port/include -I%s/generated -I%s\n' \
		'$(MODULE_NAME)' '$(MODULE_NAME)' '$($(MODULE_NAME)-y)' \
		'$(M)' '$(LINUXCPP)' '$(M)' '$(INCLUDE_DIR)' > $(M)/Kbuild.tmp
	@cmp -s $(M)/Kbuild.tmp $(M)/Kbuild || mv $(M)/Kbuild.tmp $(M)/Kbuild
	@rm -f $(M)/Kbuild.tmp
	@$(MAKE) -C $(KDIR) M=$(M) KCFLAGS="$(ccflags-y)" $(LCPP_KBUILD_EXTRA) \
		CONFIG_DEBUG_INFO_BTF_MODULES= modules

clean:
	$(MAKE) -C $(KDIR) M=$(M) clean
	rm -f $(CXX_OBJS) $(CXX_OBJS:.o=.d) $(M)/.*.cmd $(STAMP) $(CXXFLAGS_MK) \
		$(M)/libc_port.c $(M)/libcxx_exports.c $(M)/libcxx_exports.o \
		$(M)/generated/.bindings.hash $(M)/generated/.cxxflags.hash
	rm -rf $(M)/generated/libc_port

.PHONY: all clean FORCE
FORCE:
-include $(CXX_OBJS:.o=.d)
