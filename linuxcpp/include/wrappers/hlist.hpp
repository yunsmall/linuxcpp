#pragma once
// 哈希链表包装，仅做字段指针操作，不调用内核函数。
#include <stddef.h>
#include "bindings.hpp"

namespace linuxcpp {
namespace wrappers {

template <typename T, size_t Offset>
class hlist {
public:
	class iterator {
	public:
		explicit iterator(hlist_node* node = nullptr) : node_(node) {}
		T& operator*() const { return *hlist::value_of(node_); }
		T* operator->() const { return hlist::value_of(node_); }
		iterator& operator++() { node_ = node_->next; return *this; }
		bool operator==(const iterator& other) const { return node_ == other.node_; }
		bool operator!=(const iterator& other) const { return node_ != other.node_; }
	private:
		hlist_node* node_;
	};

	class const_iterator {
	public:
		explicit const_iterator(const hlist_node* node = nullptr) : node_(node) {}
		const T& operator*() const { return *hlist::value_of(node_); }
		const T* operator->() const { return hlist::value_of(node_); }
		const_iterator& operator++() { node_ = node_->next; return *this; }
		bool operator==(const const_iterator& other) const { return node_ == other.node_; }
		bool operator!=(const const_iterator& other) const { return node_ != other.node_; }
	private:
		const hlist_node* node_;
	};

	hlist() { head_.first = nullptr; }
	// 节点里的 pprev 指回本对象的 head_，拷贝后仍指向原链表
	hlist(const hlist&) = delete;
	hlist& operator=(const hlist&) = delete;
	hlist(hlist&&) = delete;
	hlist& operator=(hlist&&) = delete;

	// 析构时清掉节点的 pprev，避免元素之后 erase() 写已释放的 head_
	~hlist() {
		hlist_node* node = head_.first;
		while (node != nullptr) {
			hlist_node* next = node->next;
			node->next = nullptr;
			node->pprev = nullptr;
			node = next;
		}
	}

	bool empty() const { return head_.first == nullptr; }

	void push_front(T& value) {
		hlist_node* node = node_of(value);
		node->next = head_.first;
		node->pprev = &head_.first;
		if (head_.first != nullptr)
			head_.first->pprev = &node->next;
		head_.first = node;
	}

	// 节点必须已插入过（pprev 有效）或清零；未初始化的随机 pprev 会被当成
	// “已插入”，随后写入野指针
	bool erase(T& value) {
		hlist_node* node = node_of(value);
		if (node->pprev == nullptr)
			return false;
		if (node->next != nullptr)
			node->next->pprev = node->pprev;
		*node->pprev = node->next;
		node->next = nullptr;
		node->pprev = nullptr;
		return true;
	}

	T* front() { return head_.first != nullptr ? value_of(head_.first) : nullptr; }
	const T* front() const { return head_.first != nullptr ? value_of(head_.first) : nullptr; }

	iterator begin() { return iterator(head_.first); }
	iterator end() { return iterator(nullptr); }
	const_iterator begin() const { return const_iterator(head_.first); }
	const_iterator end() const { return const_iterator(nullptr); }

private:
	hlist_head head_;

	static hlist_node* node_of(T& value) {
		return reinterpret_cast<hlist_node*>(reinterpret_cast<char*>(&value) + Offset);
	}
	static const hlist_node* node_of(const T& value) {
		return reinterpret_cast<const hlist_node*>(reinterpret_cast<const char*>(&value) + Offset);
	}
	static T* value_of(hlist_node* node) {
		return reinterpret_cast<T*>(reinterpret_cast<char*>(node) - Offset);
	}
	static const T* value_of(const hlist_node* node) {
		return reinterpret_cast<const T*>(reinterpret_cast<const char*>(node) - Offset);
	}
};

} // namespace wrappers
} // namespace linuxcpp

#define LCPP_HLIST(T, member) ::linuxcpp::wrappers::hlist<T, offsetof(T, member)>
