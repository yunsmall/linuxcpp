// SPDX-License-Identifier: GPL-2.0-only

// 自定义总线和挂在自定义总线上的驱动。
//
// 内核的 bus_type / device_driver 用函数指针做虚表；这里把 bus 变成抽象基类，
// bus_driver 继承 driver，probe/remove/shutdown 都是普通虚函数。

#pragma once

#include "callback_result.hpp"
#include "device_ref.hpp"
#include "driver.hpp"

namespace linuxcpp {
namespace model {

class bus;

class bus_driver : public driver {
public:
	bus_driver(const char *name, bus &bus) noexcept;
	~bus_driver() override;

	bus_driver(const bus_driver &) = delete;
	bus_driver &operator=(const bus_driver &) = delete;
	bus_driver(bus_driver &&) = delete;
	bus_driver &operator=(bus_driver &&) = delete;

	[[nodiscard]] int start() override;
	void stop() override;
	abi::device_driver *kernel() override { return &holder_.drv; }

	// bus 接管 probe/remove/shutdown 后，由它把回调转发回 C++ driver
	static int dispatch_probe(abi::device *dev) noexcept;
	static int dispatch_remove(abi::device *dev) noexcept;
	static void dispatch_shutdown(abi::device *dev) noexcept;

	// match 时内核只给 struct device_driver *，反查回 C++ driver
	static driver *driver_for(abi::device_driver *drv) noexcept;

private:
	struct holder {
		abi::device_driver drv{};
		bus_driver *owner = nullptr;
	};

	static holder *from_driver(abi::device_driver *drv) noexcept;
	static holder *self_for(abi::device *dev) noexcept;

	holder holder_{};
	bus *bus_ = nullptr;
	bool started_ = false;
};

class bus {
public:
	explicit bus(const char *name) noexcept;
	virtual ~bus();

	bus(const bus &) = delete;
	bus &operator=(const bus &) = delete;
	bus(bus &&) = delete;
	bus &operator=(bus &&) = delete;

	virtual int match(device &dev, driver &drv) = 0;
	virtual int probe(device &dev)
	{
		(void)dev;
		return 0;
	}
	virtual void remove(device &dev) { (void)dev; }
	virtual void shutdown(device &dev) { (void)dev; }

	[[nodiscard]] int error() const noexcept { return error_; }
	explicit operator bool() const noexcept { return error_ == 0; }
	abi::bus_type *kernel() noexcept { return &holder_.type; }

private:
	struct holder {
		abi::bus_type type{};
		bus *owner = nullptr;
	};

	static holder *from_bus(const abi::bus_type *bus) noexcept;
	static int match_trampoline(abi::device *dev,
				    const abi::device_driver *drv) noexcept;
	static int probe_trampoline(abi::device *dev) noexcept;
	template <typename R>
	static R remove_trampoline(abi::device *dev) noexcept;
	static void shutdown_trampoline(abi::device *dev) noexcept;

	holder holder_{};
	int error_ = -abi::EINVAL;
};

inline bus_driver::bus_driver(const char *name, bus &bus) noexcept
{
	holder_.owner = this;
	bus_ = &bus;
	holder_.drv = {};
	holder_.drv.name = name;
	holder_.drv.bus = bus.kernel();
	holder_.drv.owner = this_module();
	// bus 自己提供了 probe/remove/shutdown，driver 不能再填同名字段
	error_ = name ? 0 : -abi::EINVAL;
}

inline bus_driver::~bus_driver()
{
	stop();
}

inline int bus_driver::start()
{
	if (started_)
		return 0;
	if (error_ != 0)
		return error_;

	int ret = abi::driver_register(&holder_.drv);

	if (ret)
		return ret;
	started_ = true;
	return 0;
}

inline void bus_driver::stop()
{
	if (!started_)
		return;
	started_ = false;
	abi::driver_unregister(&holder_.drv);
}

inline bus_driver::holder *bus_driver::from_driver(abi::device_driver *drv) noexcept
{
	return reinterpret_cast<holder *>(
		reinterpret_cast<char *>(drv) - offsetof(holder, drv));
}

inline bus_driver::holder *bus_driver::self_for(abi::device *dev) noexcept
{
	return dev && dev->driver ? from_driver(dev->driver) : nullptr;
}

inline driver *bus_driver::driver_for(abi::device_driver *drv) noexcept
{
	holder *h = drv ? from_driver(drv) : nullptr;

	return h && h->owner ? static_cast<driver *>(h->owner) : nullptr;
}

inline int bus_driver::dispatch_probe(abi::device *dev) noexcept
{
	holder *h = self_for(dev);

	if (!h || !h->owner)
		return -abi::ENODEV;
	device_ref ref(dev);
	return h->owner->probe(ref);
}

inline int bus_driver::dispatch_remove(abi::device *dev) noexcept
{
	holder *h = self_for(dev);

	if (h && h->owner) {
		device_ref ref(dev);
		h->owner->remove(ref);
	}
	return 0;
}

inline void bus_driver::dispatch_shutdown(abi::device *dev) noexcept
{
	holder *h = self_for(dev);

	if (h && h->owner) {
		device_ref ref(dev);
		h->owner->shutdown(ref);
	}
}

inline bus::bus(const char *name) noexcept
{
	holder_.owner = this;
	holder_.type = {};
	holder_.type.name = name;
	holder_.type.match = &match_trampoline;
	holder_.type.probe = &probe_trampoline;
	using remove_result = detail::function_result<
		decltype(abi::bus_type::remove)>::type;
	holder_.type.remove = &remove_trampoline<remove_result>;
	holder_.type.shutdown = &shutdown_trampoline;
	error_ = name ? abi::bus_register(&holder_.type) : -abi::EINVAL;
}

inline bus::~bus()
{
	if (error_ == 0) {
		error_ = -abi::EINVAL;
		abi::bus_unregister(&holder_.type);
	}
}

inline bus::holder *bus::from_bus(const abi::bus_type *bus) noexcept
{
	return reinterpret_cast<holder *>(
		reinterpret_cast<char *>(const_cast<abi::bus_type *>(bus)) -
		offsetof(holder, type));
}

inline int bus::match_trampoline(abi::device *dev,
				 const abi::device_driver *drv) noexcept
{
	bus *owner = dev && dev->bus ? from_bus(dev->bus)->owner : nullptr;
	driver *drv_cpp = bus_driver::driver_for(
		const_cast<abi::device_driver *>(drv));

	if (!owner || !drv_cpp)
		return 0;
	device_ref ref(dev);
	return owner->match(ref, *drv_cpp);
}

inline int bus::probe_trampoline(abi::device *dev) noexcept
{
	bus *owner = dev && dev->bus ? from_bus(dev->bus)->owner : nullptr;

	if (!owner)
		return -abi::ENODEV;

	device_ref ref(dev);
	int ret = owner->probe(ref);

	if (ret)
		return ret;
	return bus_driver::dispatch_probe(dev);
}

template <typename R>
inline R bus::remove_trampoline(abi::device *dev) noexcept
{
	bus *owner = dev && dev->bus ? from_bus(dev->bus)->owner : nullptr;

	if (owner) {
		device_ref ref(dev);
		owner->remove(ref);
	}
	bus_driver::dispatch_remove(dev);
	return detail::zero_return<R>::get();
}

inline void bus::shutdown_trampoline(abi::device *dev) noexcept
{
	bus *owner = dev && dev->bus ? from_bus(dev->bus)->owner : nullptr;

	if (owner) {
		device_ref ref(dev);
		owner->shutdown(ref);
	}
	bus_driver::dispatch_shutdown(dev);
}

}  // namespace model
}  // namespace linuxcpp
