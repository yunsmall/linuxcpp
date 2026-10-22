# 使用内核 libc 子集时 include 这个片段。
# generated 目录是 build.py 按目标内核/编译器生成的 errno 和类型定义，
# 必须排在静态头前面；静态头只放函数声明和不可用标记。

LCPP_LIBC_ROOT ?= $(if $(M),$(M),$(CURDIR))/generated/libc_port/include
ccflags-y += -I$(LCPP_LIBC_ROOT) -I$(LINUXCPP)/libc_port/include
cxxflags-y += -I$(LCPP_LIBC_ROOT) -I$(LINUXCPP)/libc_port/include
