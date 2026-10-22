# 使用内核版 libc++ 时 include 这个片段，得到必要的 C++ 编译参数。
# 它只追加 flags，不改变构建模式；运行库本身由 linuxcpp/runtime 编成独立 ko。
#
# 使用共享运行库的模块还要像依赖普通外部模块一样声明符号来源：
#   KBUILD_EXTRA_SYMBOLS := $(LINUXCPP)/runtime/Module.symvers

# 必须排在所有 ccflags-y/cxxflags-y 的 -I 前面：libc++ 的 <cstdlib> 等
# 包装头要先用 include_next 找到 libc_compat 的 C 头，不能被 libc 头抢先。
LCPP_LIBCXX_PREFLAGS := -nostdinc++ -DLCPP_USE_LIBCXX \
	-I$(LINUXCPP)/libcxx_port/include \
	-I$(LINUXCPP)/../third_party/libcxx/include

include $(LINUXCPP)/libc.mk
