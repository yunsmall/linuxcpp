# libc++ 运行库模块：把自行下载的 libc++ 编成独立 ko，并导出符号。
# 其他模块要用它，和依赖普通外部模块一样设置 KBUILD_EXTRA_SYMBOLS。

KDIR ?= /lib/modules/$(shell uname -r)/build
PYTHON ?= python3
LINUXCPP ?= ..

ifeq ($(LINUXCPP_BUILD),)
# 直接 make：交给 driver；driver include 本文件时这段不会生效
all:
	@$(MAKE) -C $(LINUXCPP) M=$(CURDIR) KDIR="$(KDIR)" PYTHON="$(PYTHON)"

clean:
	@$(MAKE) -C $(LINUXCPP) M=$(CURDIR) KDIR="$(KDIR)" PYTHON="$(PYTHON)" clean

else
MODULE_NAME := libcxx_runtime
obj-m := $(MODULE_NAME).o
$(MODULE_NAME)-y := driver.o
LCPP_ENTRY_OBJ := entry_gen.o

# 把 libc++ 运行库源码编进这个模块，并生成导出表供其他模块解析
LCPP_LIBCXX := 1
LCPP_LIBCXX_EXPORTS := 1

# libc++ 的 exception fallback 源码用 #warning 标记“异常未实现”，
# 内核构建固定关闭异常，这些提示是预期行为，不必每次构建都刷屏
cxxflags-y += -Wno-cpp
include $(LINUXCPP)/libcxx.mk
endif
