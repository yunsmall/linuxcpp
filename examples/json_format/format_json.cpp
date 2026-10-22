// SPDX-License-Identifier: GPL-2.0-only

// JSON 解析和缩进格式化：RapidJSON SAX + kernel_fpu_begin/end。
// 这个翻译单元用 SSE 编译，但只在内核 FPU 区间内执行浮点代码；
// 解析器使用固定栈分配器，FPU 区间内不进行任何可能睡眠的分配。

#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include <rapidjson/reader.h>

#include "json_format.h"

extern "C" void lc_fpu_begin(void);
extern "C" void lc_fpu_end(void);

namespace {

constexpr size_t kMaxOutput = 4U * 1024U * 1024U;
constexpr unsigned int kMaxDepth = 128;
constexpr size_t kStackSize = 256U * 1024U;

// RapidJSON 的 Reader 会从 StackAllocator 申请内部栈。这里用一块静态
// 缓冲做 bump 分配，保证 FPU 区间内不会走到 kmalloc(GFP_KERNEL)。
struct FixedAllocator {
	static char buffer[kStackSize];
	static size_t used;

	static void *Malloc(size_t size)
	{
		size_t aligned = (used + 15U) & ~size_t(15U);

		if (aligned + size > kStackSize)
			return nullptr;
		used = aligned + size;
		return buffer + aligned;
	}

	static void *Realloc(void *ptr, size_t old_size, size_t new_size)
	{
		void *next = Malloc(new_size);

		if (!next)
			return nullptr;
		if (ptr && old_size)
			memcpy(next, ptr, old_size < new_size ? old_size : new_size);
		return next;
	}

	static void Free(void *) {}
};

char FixedAllocator::buffer[kStackSize];
size_t FixedAllocator::used;

struct json_out {
	char *data;
	size_t capacity;
	size_t length;
	bool overflow;

	bool put(const char *text, size_t size)
	{
		if (length + size > kMaxOutput) {
			overflow = true;
			return false;
		}
		if (data) {
			// 留一个字节给结尾 NUL
			if (length + size + 1 > capacity) {
				overflow = true;
				return false;
			}
			memcpy(data + length, text, size);
		}
		length += size;
		return true;
	}

	bool put(const char *text)
	{
		return put(text, strlen(text));
	}

	bool put_char(char c)
	{
		return put(&c, 1);
	}

	bool indent(unsigned int depth)
	{
		for (unsigned int i = 0; i < depth; ++i) {
			if (!put("  "))
				return false;
		}
		return true;
	}
};

bool emit_escaped(json_out *out, const char *text, size_t size)
{
	if (!out->put_char('"'))
		return false;

	for (size_t i = 0; i < size; ++i) {
		unsigned char c = static_cast<unsigned char>(text[i]);

		switch (c) {
		case '"':
			if (!out->put("\\\""))
				return false;
			break;
		case '\\':
			if (!out->put("\\\\"))
				return false;
			break;
		case '\b':
			if (!out->put("\\b"))
				return false;
			break;
		case '\f':
			if (!out->put("\\f"))
				return false;
			break;
		case '\n':
			if (!out->put("\\n"))
				return false;
			break;
		case '\r':
			if (!out->put("\\r"))
				return false;
			break;
		case '\t':
			if (!out->put("\\t"))
				return false;
			break;
		default:
			if (c < 0x20) {
				char escape[7];
				int length = snprintf(escape, sizeof(escape),
						      "\\u%04x", c);

				if (length <= 0 ||
				    !out->put(escape, static_cast<size_t>(length)))
					return false;
			} else if (!out->put_char(static_cast<char>(c))) {
				return false;
			}
			break;
		}
	}

	return out->put_char('"');
}

struct Handler : rapidjson::BaseReaderHandler<rapidjson::UTF8<>, Handler> {
	struct Level {
		char type;
		unsigned int count;
	};

	json_out *out;
	Level levels[kMaxDepth];
	unsigned int depth;
	bool failed;

	explicit Handler(json_out *output)
		: out(output), levels{}, depth(0), failed(false)
	{
	}

	// 数组元素先输出逗号和缩进；对象的值由 Key() 负责缩进。
	bool begin_value()
	{
		if (depth == 0)
			return true;

		Level &parent = levels[depth - 1];

		if (parent.type != 'a')
			return true;
		if (parent.count++ > 0) {
			if (!out->put(",\n"))
				return false;
		} else if (!out->put_char('\n')) {
			return false;
		}
		return out->indent(depth);
	}

	bool emit_integer(long long value)
	{
		char text[32];
		int length = snprintf(text, sizeof(text), "%lld", value);

		if (length <= 0)
			return false;
		return begin_value() &&
		       out->put(text, static_cast<size_t>(length));
	}

	bool emit_string(const char *text, rapidjson::SizeType size)
	{
		return begin_value() && emit_escaped(out, text, size);
	}

	bool Null()
	{
		return begin_value() && out->put("null");
	}

	bool Bool(bool value)
	{
		return begin_value() && out->put(value ? "true" : "false");
	}

	bool Int(int value) { return emit_integer(value); }
	bool Uint(unsigned value) { return emit_integer(value); }
	bool Int64(long long value) { return emit_integer(value); }
	bool Uint64(unsigned long long value)
	{
		char text[32];
		int length = snprintf(text, sizeof(text), "%llu", value);

		if (length <= 0)
			return false;
		return begin_value() &&
		       out->put(text, static_cast<size_t>(length));
	}

	// kParseNumbersAsStringsFlag 会把数字交给 RawNumber；走到这里说明
	// 浮点路径被意外打开，直接让解析失败，避免输出错误数字。
	bool Double(double)
	{
		failed = true;
		return false;
	}

	bool RawNumber(const char *text, rapidjson::SizeType size, bool)
	{
		return begin_value() && out->put(text, size);
	}

	bool String(const char *text, rapidjson::SizeType size, bool)
	{
		return emit_string(text, size);
	}

	bool StartObject()
	{
		if (depth >= kMaxDepth || !begin_value() || !out->put_char('{'))
			return false;
		levels[depth++] = {'o', 0};
		return true;
	}

	bool Key(const char *text, rapidjson::SizeType size, bool)
	{
		if (depth == 0 || levels[depth - 1].type != 'o')
			return false;

		Level &parent = levels[depth - 1];
		if (parent.count++ > 0) {
			if (!out->put(",\n"))
				return false;
		} else if (!out->put_char('\n')) {
			return false;
		}
		return out->indent(depth) && emit_escaped(out, text, size) &&
		       out->put(": ");
	}

	bool EndObject(rapidjson::SizeType)
	{
		if (depth == 0 || levels[depth - 1].type != 'o')
			return false;

		unsigned int count = levels[--depth].count;

		if (count > 0 &&
		    (!out->put_char('\n') || !out->indent(depth)))
			return false;
		return out->put_char('}');
	}

	bool StartArray()
	{
		if (depth >= kMaxDepth || !begin_value() || !out->put_char('['))
			return false;
		levels[depth++] = {'a', 0};
		return true;
	}

	bool EndArray(rapidjson::SizeType)
	{
		if (depth == 0 || levels[depth - 1].type != 'a')
			return false;

		unsigned int count = levels[--depth].count;

		if (count > 0 &&
		    (!out->put_char('\n') || !out->indent(depth)))
			return false;
		return out->put_char(']');
	}
};

// RapidJSON 的栈分配器是固定大小；先限制嵌套深度，避免它把静态缓冲耗尽。
bool too_deep(const char *text, size_t length)
{
	unsigned int depth = 0;
	bool in_string = false;
	bool escaped = false;

	for (size_t i = 0; i < length; ++i) {
		char c = text[i];

		if (in_string) {
			if (escaped) {
				escaped = false;
			} else if (c == '\\') {
				escaped = true;
			} else if (c == '"') {
				in_string = false;
			}
			continue;
		}
		if (c == '"') {
			in_string = true;
		} else if (c == '{' || c == '[') {
			if (++depth > kMaxDepth)
				return true;
		} else if ((c == '}' || c == ']') && depth > 0) {
			--depth;
		}
	}
	return false;
}

}  // namespace

extern "C" long lc_pretty_json(const char *input, unsigned long length,
				char *output, unsigned long capacity)
{
	if (!input || length == 0)
		return -EINVAL;

	if (too_deep(input, length))
		return -EINVAL;

	json_out out = {output, static_cast<size_t>(capacity), 0, false};
	Handler handler(&out);

	FixedAllocator::used = 0;

	FixedAllocator allocator;
	lc_fpu_begin();
	rapidjson::MemoryStream stream(input, length);
	// 把 allocator 实例传给 Reader，避免它在 Stack 内部再 new 一个
	rapidjson::GenericReader<rapidjson::UTF8<>, rapidjson::UTF8<>,
				 FixedAllocator> reader(&allocator, 1024);
	rapidjson::ParseResult result =
		reader.Parse<rapidjson::kParseNumbersAsStringsFlag>(stream, handler);
	lc_fpu_end();

	if (result.IsError())
		return out.overflow ? -EFBIG : -EINVAL;
	if (!out.put_char('\n'))
		return -EFBIG;
	if (output) {
		if (out.length + 1 > out.capacity)
			return -ENOSPC;
		output[out.length] = '\0';
	}
	return static_cast<long>(out.length);
}
