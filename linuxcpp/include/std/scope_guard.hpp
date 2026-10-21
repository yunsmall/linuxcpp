// SPDX-License-Identifier: GPL-3.0-or-later

// 作用域退出时执行清理，替代成对的 goto/cleanup 分支。

#pragma once

namespace linuxcpp {
namespace std {

template <typename F>
class scope_guard {
public:
	explicit scope_guard(F &&fn) : fn_(static_cast<F &&>(fn)) {}
	~scope_guard()
	{
		if (active_)
			fn_();
	}

	scope_guard(const scope_guard &) = delete;
	scope_guard &operator=(const scope_guard &) = delete;
	scope_guard(scope_guard &&other) noexcept
		: fn_(static_cast<F &&>(other.fn_)), active_(other.active_)
	{
		other.active_ = false;
	}

	void dismiss() noexcept { active_ = false; }

private:
	F fn_;
	bool active_ = true;
};

template <typename F>
inline scope_guard<F> make_scope_guard(F &&fn)
{
	return scope_guard<F>(static_cast<F &&>(fn));
}

}  // namespace std
}  // namespace linuxcpp
