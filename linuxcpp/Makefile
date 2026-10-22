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

# 没写 $(MODULE_NAME)-y 时按模块目录里的源文件推导，和 kbuild 的默认体验一致
$(MODULE_NAME)-y ?= $(patsubst %.cpp,%.o,$(notdir $(wildcard $(M)/*.cpp))) \
	$(patsubst %.c,%.o,$(notdir $(wildcard $(M)/*.c)))

# 用户对象是 $(MODULE_NAME)-y 里除核心/生成对象之外的部分
LCPP_CORE_OBJS := lcpp_ctors_start.o layout_check.o $(LCPP_ENTRY_OBJ) \
	linuxcpp_thunks.o thunks_gen.o lcpp_ctors.o linuxcpp.o device.o lcpp_ctors_end.o
LCPP_USER_OBJS := $(filter-out $(LCPP_CORE_OBJS),$($(MODULE_NAME)-y))

# 保持构造/析构数组边界对象的链接顺序
$(MODULE_NAME)-y := lcpp_ctors_start.o layout_check.o $(LCPP_ENTRY_OBJ) \
	linuxcpp_thunks.o thunks_gen.o lcpp_ctors.o linuxcpp.o device.o \
	$(LCPP_USER_OBJS) lcpp_ctors_end.o

KO := $(M)/$(MODULE_NAME).ko
STAMP := $(M)/generated/.prepared
CXXFLAGS_MK := $(M)/generated/cxxflags.mk

# 公共 Makefile 负责编译的 C++ 对象：核心库 + 用户列出的 .cpp
CORE_CXX_OBJS := $(addprefix $(M)/,linuxcpp.o device.o)
USER_CXX_OBJS := $(addprefix $(M)/, \
	$(filter $(patsubst %.cpp,%.o,$(notdir $(wildcard $(M)/*.cpp))),$(LCPP_USER_OBJS)))
CXX_OBJS := $(CORE_CXX_OBJS) $(USER_CXX_OBJS)
GENERATED_C := entry_gen.c layout_check.c thunks_gen.c linuxcpp_thunks.c \
	lcpp_ctors.c lcpp_ctors_start.c lcpp_ctors_end.c
USER_C_SOURCES := $(filter-out $(GENERATED_C),$(notdir $(wildcard $(M)/*.c)))
USER_SOURCES := $(USER_C_SOURCES) $(notdir $(wildcard $(M)/*.cpp))
PREPARE_DEPS := $(shell find $(LINUXCPP)/python -type f ! -path '*/__pycache__/*' ! -name '*.pyc') \
	$(SRC_DIR)/linuxcpp_thunks.c $(LINUXCPP)/Makefile $(M)/Makefile

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
	$(CXX) $(LCPP_CXXFLAGS) $(ccflags-y) $(cxxflags-y) $(CXXFLAGS) -MMD -MP -c -o $@ $<
	@echo 'savedcmd_$(notdir $@) := $(CXX) $(LCPP_CXXFLAGS) $(ccflags-y) $(cxxflags-y) $(CXXFLAGS) -MMD -MP -c -o $@ $<' > $(M)/.$(notdir $@).cmd

$(USER_CXX_OBJS): $(M)/%.o: $(M)/%.cpp $(STAMP)
	$(CXX) $(LCPP_CXXFLAGS) $(ccflags-y) $(cxxflags-y) $(CXXFLAGS) -MMD -MP -c -o $@ $<
	@echo 'savedcmd_$(notdir $@) := $(CXX) $(LCPP_CXXFLAGS) $(ccflags-y) $(cxxflags-y) $(CXXFLAGS) -MMD -MP -c -o $@ $<' > $(M)/.$(notdir $@).cmd

# 模块 Makefile 可能往 $(MODULE_NAME)-y 里加了对象，链接前按最终列表重写 Kbuild
$(KO): $(CXX_OBJS) $(addprefix $(M)/,$(USER_C_SOURCES)) $(STAMP) $(MAKEFILE_LIST)
	@printf 'obj-m := %s.o\n%s-y := %s\nccflags-y += -I%s/generated -I%s\n' \
		'$(MODULE_NAME)' '$(MODULE_NAME)' '$($(MODULE_NAME)-y)' \
		'$(M)' '$(INCLUDE_DIR)' > $(M)/Kbuild.tmp
	@cmp -s $(M)/Kbuild.tmp $(M)/Kbuild || mv $(M)/Kbuild.tmp $(M)/Kbuild
	@rm -f $(M)/Kbuild.tmp
	$(MAKE) -C $(KDIR) M=$(M) KCFLAGS="$(ccflags-y)" CONFIG_DEBUG_INFO_BTF_MODULES= modules

clean:
	$(MAKE) -C $(KDIR) M=$(M) clean
	rm -f $(CXX_OBJS) $(CXX_OBJS:.o=.d) $(M)/.*.cmd $(STAMP) $(CXXFLAGS_MK) \
		$(M)/generated/.bindings.hash $(M)/generated/.cxxflags.hash

.PHONY: all clean FORCE
FORCE:
-include $(CXX_OBJS:.o=.d)
