// SPDX-License-Identifier: GPL-2.0-only

// 包装内核 list_head 的侵入式双向链表。
// 需要生成的 bindings 里有完整的 list_head 定义（module.toml 的 roots 加 "list_head"）。

#pragma once

#include <stddef.h>

#include "bindings.hpp"

namespace linuxcpp {
namespace wrappers {

// Offset 是 list_head 成员在 T 中的偏移；元素所有权仍归调用方
template <typename T, size_t Offset>
class intrusive_list {
public:
	intrusive_list() noexcept
	{
		head_.next = &head_;
		head_.prev = &head_;
	}

	~intrusive_list() { clear(); }

	intrusive_list(const intrusive_list &) = delete;
	intrusive_list &operator=(const intrusive_list &) = delete;

	bool empty() const noexcept { return head_.next == &head_; }

	// 只摘链，不释放元素
	void clear() noexcept
	{
		while (!empty())
			unlink(*head_.next);
	}

	void push_back(T &item) noexcept { insert_before(head_, node(item)); }
	void push_front(T &item) noexcept { insert_before(*head_.next, node(item)); }
	void erase(T &item) noexcept { unlink(node(item)); }

	T *front() noexcept { return empty() ? nullptr : owner(head_.next); }
	T *back() noexcept { return empty() ? nullptr : owner(head_.prev); }
	const T *front() const noexcept { return empty() ? nullptr : owner(head_.next); }
	const T *back() const noexcept { return empty() ? nullptr : owner(head_.prev); }

	class iterator {
	public:
		explicit iterator(list_head *node) noexcept : node_(node) {}

		T &operator*() const noexcept { return *owner(node_); }
		T *operator->() const noexcept { return owner(node_); }

		iterator &operator++() noexcept
		{
			node_ = node_->next;
			return *this;
		}

		bool operator==(const iterator &other) const noexcept { return node_ == other.node_; }
		bool operator!=(const iterator &other) const noexcept { return node_ != other.node_; }

	private:
		list_head *node_;
	};

	class const_iterator {
	public:
		explicit const_iterator(const list_head *node) noexcept : node_(node) {}

		const T &operator*() const noexcept { return *owner(const_cast<list_head *>(node_)); }
		const T *operator->() const noexcept { return owner(const_cast<list_head *>(node_)); }

		const_iterator &operator++() noexcept
		{
			node_ = node_->next;
			return *this;
		}

		bool operator==(const const_iterator &other) const noexcept
		{
			return node_ == other.node_;
		}
		bool operator!=(const const_iterator &other) const noexcept
		{
			return node_ != other.node_;
		}

	private:
		const list_head *node_;
	};

	iterator begin() noexcept { return iterator(head_.next); }
	iterator end() noexcept { return iterator(&head_); }
	const_iterator begin() const noexcept { return const_iterator(head_.next); }
	const_iterator end() const noexcept { return const_iterator(&head_); }

private:
	static T *owner(list_head *node) noexcept
	{
		return reinterpret_cast<T *>(reinterpret_cast<char *>(node) - Offset);
	}

	static list_head &node(T &item) noexcept
	{
		return *reinterpret_cast<list_head *>(reinterpret_cast<char *>(&item) + Offset);
	}

	static void insert_before(list_head &pos, list_head &item) noexcept
	{
		item.next = &pos;
		item.prev = pos.prev;
		pos.prev->next = &item;
		pos.prev = &item;
	}

	static void unlink(list_head &item) noexcept
	{
		item.prev->next = item.next;
		item.next->prev = item.prev;
		item.next = &item;
		item.prev = &item;
	}

	list_head head_;
};

}  // namespace wrappers
}  // namespace linuxcpp

// 用法：LCPP_LIST(my_item, node) items;
#define LCPP_LIST(Type, member) ::linuxcpp::wrappers::intrusive_list<Type, offsetof(Type, member)>
