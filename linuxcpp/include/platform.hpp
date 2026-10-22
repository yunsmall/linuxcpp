// SPDX-License-Identifier: GPL-2.0-only

// platform 设备/驱动。继承关系和内核一致：platform_device 是一种 device，
// platform_driver 是一种 driver；platform 驱动注册由内核的 platform bus 完成。

#pragma once

#include "callback_result.hpp"
#include "device.hpp"
#include "driver.hpp"

namespace linuxcpp {
namespace model {

class platform_device_ref final : public device {
public:
	constexpr platform_device_ref() noexcept = default;
	constexpr explicit platform_device_ref(abi::platform_device *ptr) noexcept
		: ptr_(ptr)
	{
	}

	abi::device *kernel() override
	{
		return ptr_ ? &ptr_->dev : nullptr;
	}
	const char *name() const override
	{
		return ptr_ ? ptr_->name : nullptr;
	}
	int id() const noexcept { return ptr_ ? ptr_->id : -1; }
	abi::platform_device *get() const noexcept { return ptr_; }
	abi::platform_device *operator->() const noexcept { return ptr_; }

private:
	abi::platform_device *ptr_ = nullptr;
};

class platform_driver : public driver {
public:
	explicit platform_driver(const char *name) noexcept;
	~platform_driver() override;

	platform_driver(const platform_driver &) = delete;
	platform_driver &operator=(const platform_driver &) = delete;
	platform_driver(platform_driver &&) = delete;
	platform_driver &operator=(platform_driver &&) = delete;

	// 内核给的是 struct platform_device *，这里转成类型安全的 ref
	int probe(device &dev) final
	{
		return probe(static_cast<platform_device_ref &>(dev));
	}
	virtual int probe(platform_device_ref &pdev) = 0;

	void remove(device &dev) final
	{
		remove(static_cast<platform_device_ref &>(dev));
	}
	virtual void remove(platform_device_ref &pdev) { (void)pdev; }

	void shutdown(device &dev) final
	{
		shutdown(static_cast<platform_device_ref &>(dev));
	}
	virtual void shutdown(platform_device_ref &pdev) { (void)pdev; }

	[[nodiscard]] int start() override;
	void stop() override;
	abi::device_driver *kernel() override { return &holder_.drv.driver; }

private:
	struct holder {
		abi::platform_driver drv{};
		platform_driver *owner = nullptr;
	};

	static holder *from_driver(abi::device_driver *drv) noexcept;
	static holder *self_for(abi::platform_device *pdev) noexcept;
	static int probe_trampoline(abi::platform_device *pdev) noexcept;
	template <typename R>
	static R remove_trampoline(abi::platform_device *pdev) noexcept;
	static void shutdown_trampoline(abi::platform_device *pdev) noexcept;

	holder holder_{};
	bool started_ = false;
};

class platform_device final : public device {
public:
	platform_device(const char *name, int id = -1) noexcept;
	~platform_device() override;

	platform_device(const platform_device &) = delete;
	platform_device &operator=(const platform_device &) = delete;
	platform_device(platform_device &&) = delete;
	platform_device &operator=(platform_device &&) = delete;

	abi::device *kernel() override
	{
		return pdev_ ? &pdev_->dev : nullptr;
	}
	const char *name() const override
	{
		return pdev_ ? pdev_->name : nullptr;
	}
	int id() const noexcept { return pdev_ ? pdev_->id : -1; }
	platform_device_ref ref() const noexcept
	{
		return platform_device_ref(pdev_);
	}

	[[nodiscard]] int error() const noexcept { return error_; }
	explicit operator bool() const noexcept { return error_ == 0; }

private:
	abi::platform_device *pdev_ = nullptr;
	int error_ = -abi::EINVAL;
};

inline platform_driver::platform_driver(const char *name) noexcept
{
	holder_.owner = this;
	holder_.drv = {};
	holder_.drv.driver.name = name;
	holder_.drv.driver.owner = this_module();
	holder_.drv.probe = &probe_trampoline;
	using remove_result = detail::function_result<
		decltype(abi::platform_driver::remove)>::type;
	holder_.drv.remove = &remove_trampoline<remove_result>;
	holder_.drv.shutdown = &shutdown_trampoline;
	error_ = name ? 0 : -abi::EINVAL;
}

inline platform_driver::~platform_driver()
{
	stop();
}

inline int platform_driver::start()
{
	if (started_)
		return 0;
	if (error_ != 0)
		return error_;

	int ret = abi::__platform_driver_register(
		&holder_.drv, this_module());

	if (ret)
		return ret;
	started_ = true;
	return 0;
}

inline void platform_driver::stop()
{
	if (!started_)
		return;
	started_ = false;
	abi::platform_driver_unregister(&holder_.drv);
}

inline platform_driver::holder *
platform_driver::from_driver(abi::device_driver *drv) noexcept
{
	abi::platform_driver *pdrv = reinterpret_cast<abi::platform_driver *>(
		reinterpret_cast<char *>(drv) -
		offsetof(abi::platform_driver, driver));

	return reinterpret_cast<holder *>(
		reinterpret_cast<char *>(pdrv) - offsetof(holder, drv));
}

inline platform_driver::holder *
platform_driver::self_for(abi::platform_device *pdev) noexcept
{
	return pdev && pdev->dev.driver ? from_driver(pdev->dev.driver)
				       : nullptr;
}

inline int platform_driver::probe_trampoline(abi::platform_device *pdev) noexcept
{
	holder *h = self_for(pdev);

	if (!h || !h->owner)
		return -abi::ENODEV;
	platform_device_ref ref(pdev);
	return h->owner->probe(ref);
}

template <typename R>
inline R platform_driver::remove_trampoline(abi::platform_device *pdev) noexcept
{
	holder *h = self_for(pdev);

	if (h && h->owner) {
		platform_device_ref ref(pdev);
		h->owner->remove(ref);
	}
	return detail::zero_return<R>::get();
}

inline void platform_driver::shutdown_trampoline(
	abi::platform_device *pdev) noexcept
{
	holder *h = self_for(pdev);

	if (h && h->owner) {
		platform_device_ref ref(pdev);
		h->owner->shutdown(ref);
	}
}

inline platform_device::platform_device(const char *name, int id) noexcept
{
	if (!name) {
		error_ = -abi::EINVAL;
		return;
	}

	pdev_ = abi::platform_device_alloc(name, id);
	if (!pdev_) {
		error_ = -abi::ENOMEM;
		return;
	}

	error_ = abi::platform_device_add(pdev_);
	if (error_ != 0) {
		abi::platform_device_put(pdev_);
		pdev_ = nullptr;
	}
}

inline platform_device::~platform_device()
{
	if (error_ == 0 && pdev_) {
		error_ = -abi::EINVAL;
		abi::platform_device_unregister(pdev_);
		pdev_ = nullptr;
	}
}

}  // namespace model
}  // namespace linuxcpp
