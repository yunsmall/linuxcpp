"""生成模块目录的 Makefile。"""

import sys

from paths import PY_DIR, LIB_DIR, SRC_DIR, INCLUDE_DIR

MAKEFILE_MARKER = "# 由 build.py 自动生成，不要手改。"


def write_makefile(module_dir, config, kdir):
    """生成可增量构建的 Makefile；依赖检测和并行交给 make"""
    template = """\
# 由 build.py 自动生成，不要手改。
KDIR ?= @KDIR@
PYTHON ?= @PYTHON@
MODULE_DIR := $(CURDIR)
LINUXCPP := @LINUXCPP@
SRC_DIR := @SRC_DIR@
INCLUDE_DIR := @INCLUDE_DIR@
BUILD := @BUILD@
KO := @MODULE_NAME@.ko
STAMP := generated/.prepared
CXXFLAGS_MK := generated/cxxflags.mk

CORE_CXX_OBJS := linuxcpp.o device.o
USER_CXX_OBJS := $(filter-out $(CORE_CXX_OBJS),$(patsubst %.cpp,%.o,$(notdir $(wildcard *.cpp))))
CXX_OBJS := $(CORE_CXX_OBJS) $(USER_CXX_OBJS)
GENERATED_C := entry_gen.c layout_check.c thunks_gen.c linuxcpp_thunks.c lcpp_ctors.c lcpp_ctors_start.c lcpp_ctors_end.c
USER_C_SOURCES := $(filter-out $(GENERATED_C),$(wildcard *.c))
USER_SOURCES := $(notdir $(USER_C_SOURCES)) $(notdir $(wildcard *.cpp))
PREPARE_DEPS := $(shell find $(LINUXCPP)/python -type f ! -path '*/__pycache__/*' ! -name '*.pyc') $(SRC_DIR)/linuxcpp_thunks.c

all: $(KO)

-include $(CXXFLAGS_MK)

$(CXXFLAGS_MK): $(STAMP)
	@test -f $@

$(STAMP): module.toml generated/.sources $(PREPARE_DEPS)
	@mkdir -p generated
	@$(PYTHON) $(BUILD) --prepare-only "$(MODULE_DIR)" --kdir "$(KDIR)"
	@touch $@
	@touch $(CXXFLAGS_MK)

generated/.sources: FORCE
	@mkdir -p generated
	@printf '%s\\n' '$(USER_SOURCES)' | cmp -s - $@ || printf '%s\\n' '$(USER_SOURCES)' > $@

$(CORE_CXX_OBJS): %.o: $(SRC_DIR)/%.cpp $(STAMP)
	$(CXX) $(LCPP_CXXFLAGS) $(CXXFLAGS) -MMD -MP -c -o $@ $<
	@echo 'savedcmd_$@ := $(CXX) $(LCPP_CXXFLAGS) $(CXXFLAGS) -MMD -MP -c -o $@ $<' > .$@.cmd

%.o: %.cpp $(STAMP)
	$(CXX) $(LCPP_CXXFLAGS) $(CXXFLAGS) -MMD -MP -c -o $@ $<
	@echo 'savedcmd_$@ := $(CXX) $(LCPP_CXXFLAGS) $(CXXFLAGS) -MMD -MP -c -o $@ $<' > .$@.cmd

$(KO): $(CXX_OBJS) $(USER_C_SOURCES) $(STAMP)
	$(MAKE) -C $(KDIR) M=$(MODULE_DIR) CONFIG_DEBUG_INFO_BTF_MODULES= modules

clean:
	$(MAKE) -C $(KDIR) M=$(MODULE_DIR) clean
	rm -f $(CXX_OBJS) $(CXX_OBJS:.o=.d) .*.cmd $(STAMP) $(CXXFLAGS_MK) \
		generated/.bindings.hash generated/.cxxflags.hash

.PHONY: all clean FORCE
FORCE:
-include $(CXX_OBJS:.o=.d)
"""
    replacements = {
        "@KDIR@": kdir,
        "@PYTHON@": sys.executable,
        "@LINUXCPP@": str(LIB_DIR),
        "@SRC_DIR@": str(SRC_DIR),
        "@INCLUDE_DIR@": str(INCLUDE_DIR),
        "@BUILD@": str(PY_DIR / "build.py"),
        "@MODULE_NAME@": config["name"],
    }
    content = template
    for key, value in replacements.items():
        content = content.replace(key, value)

    path = module_dir / "Makefile"
    if path.exists():
        old = path.read_text(encoding="utf-8")
        if not old.startswith(MAKEFILE_MARKER):
            sys.exit("模块目录已有手写 Makefile，拒绝覆盖；请改名或删除后再生成")
        if old == content:
            return
    path.write_text(content, encoding="utf-8")
