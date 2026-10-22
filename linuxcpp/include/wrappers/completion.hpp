#pragma once
// module.toml:
// roots = ["completion"]
// extern = ["wait_for_completion", "complete", "complete_all"]
// thunk = ["init_completion"]
#include "bindings.hpp"

namespace linuxcpp {
namespace wrappers {

class completion {
public:
	completion() { lc_init_completion(&comp_); }
	// wait_queue_head 内部有指向自己的链表指针，拷贝/移动后立即失效
	completion(const completion&) = delete;
	completion& operator=(const completion&) = delete;
	completion(completion&&) = delete;
	completion& operator=(completion&&) = delete;

	void init() { lc_init_completion(&comp_); }
	void wait() { linuxcpp::abi::wait_for_completion(&comp_); }
	void complete() { linuxcpp::abi::complete(&comp_); }
	void complete_all() { linuxcpp::abi::complete_all(&comp_); }

private:
	linuxcpp::abi::completion comp_;
};

} // namespace wrappers
} // namespace linuxcpp
