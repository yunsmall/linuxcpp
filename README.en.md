# linuxcpp — write Linux kernel modules in C++

[中文](README.md)

linuxcpp is a toolchain for building loadable Linux kernel modules from a
`module.toml` and ordinary C++ sources. It generates BTF-backed type bindings,
kernel function declarations, the C entry point, Kbuild glue, and compile-time
layout checks. Module Makefiles stay close to kbuild: they declare objects and
flags, and the shared driver does the rest.

```bash
python3 linuxcpp/python/build.py --init ../my_module
make -C ../my_module -j6
sudo insmod ../my_module/my_module.ko
cat /dev/my_module
sudo rmmod my_module
```

## Why kernel headers cannot be included directly

A C++ compiler cannot parse the kernel headers as-is. There are two classes of
problems:

- Keyword clashes: `struct class`, fields named `private`, macro parameters
  named `not` (a C++ alternative operator).
- C-only syntax: `typeof`, compound literals, designated initializers,
  `_Generic`, `__builtin_types_compatible_p`, statement expressions.

linuxcpp therefore splits the work into three layers:

```text
BTF (bpftool)             -> type layout -> C/C++ struct mirrors + static_assert checks
kernel headers (libclang) -> exported declarations, C thunks for static inline code
core library              -> hand-written thunks for macros and initializers
```

C++ code only includes `linuxcpp.hpp`, plus `device.hpp` for character/misc
devices or `device_model.hpp` for bus/driver/platform wrappers. Generated kernel
ABI mirrors live in `linuxcpp::abi`; the C++ device model lives in
`linuxcpp::model`. Kernel headers are never included.

Bindings are configured in `module.toml`:

- `roots`: kernel types for which complete layouts are needed
- `extern`: exported kernel functions
- `thunk`: `static inline` functions that need a C wrapper
- `macro`: object-like macros, exported as `inline constexpr auto`
- `headers`: extra kernel headers used while parsing
- `packed`: force packed layout when BTF loses the attribute

Function-like macros and inline functions cannot be translated automatically;
they need a C thunk or a small `constexpr` reimplementation.

## Features

- kbuild-style module Makefiles: `obj-m`, `<module>-y`, `ccflags-y`,
  `cxxflags-y`; object names map directly to `.cpp`/`.c` files
- BTF-generated struct mirrors and forward declarations; `layout_check.c`
  verifies every generated layout with `_Static_assert`
- automatic `.init_array`/`.fini_array` handling, so global constructors and
  destructors work
- a small `linuxcpp::std` layer with containers, RAII wrappers, and error helpers
- an object-oriented device model: `model::device` is the base class,
  `char_device<D>` virtuals are `file_operations` and only overridden operations
  get a trampoline; `platform_device`, `platform_driver`, and `bus` use real
  inheritance and virtual callbacks; safe types register in constructors, while
  drivers use explicit `start()`/`stop()`
- an optional kernel build of libc++ as a separate `libcxx_runtime.ko`; the
  libc++ sources are downloaded on demand and are not distributed with the repo
- an optional kernel C library subset (`libc_port`) that works with or without
  libc++
- [ETL](https://github.com/ETLCPP/etl) is the recommended container library for
  kernel code (MIT, GPL-2.0-only compatible); CTRE and RapidJSON are also
  supported, all as downloaded header-only dependencies

## Repository layout

```text
repository root/
├── Makefile                    repository entry point (runtime/examples/test/clean)
├── linuxcpp/
│   ├── include/                public C++ headers
│   ├── src/                    C/C++ implementation of the core library
│   ├── libc_port/              kernel C library subset
│   ├── libcxx_port/            libc++ kernel config, download script, patched runtime sources
│   ├── runtime/                shared libc++ runtime module (libcxx_runtime.ko)
│   ├── libc.mk                 flags for the kernel C library subset
│   ├── libcxx.mk               flags for the shared libc++
│   ├── Makefile                module build driver
│   └── python/                 build and binding generators
├── third_party/                downloaded libc++/ETL/CTRE/RapidJSON (not committed)
├── template/                   minimal misc-device module template
├── examples/                   buildable examples
├── raw_demo/                   minimal raw module
├── docs/                       detailed documentation (Chinese)
├── README.md                   Chinese README
└── README.en.md                this file
```

## Requirements

- Linux kernel headers or a source tree at `/lib/modules/$(uname -r)/build`
- Python 3.11+ (`tomllib`)
- Python bindings for libclang (for example `python3-clang-22` on Ubuntu)
- a real `bpftool` binary; if the distro wrapper cannot find a custom kernel,
  the scripts fall back to `/usr/lib/linux-tools/*/bpftool`
- a C++ compiler; by default it follows kbuild's C compiler (GCC -> `g++`,
  clang -> `clang++`), or set `[build] cxx` in `module.toml`
- `CONFIG_MODULES`, preferably `CONFIG_DEBUG_INFO_BTF`
- for libc++ (optional): run
  `python3 linuxcpp/libcxx_port/update_libcxx.py` once to download libc++ 20.1.8
  into `third_party/libcxx/`

## Tested kernels

Modules have only been built, loaded, and exercised on:

- `6.18.33.1-microsoft-standard-WSL2` (x86_64, WSL2)

Other kernel versions and architectures (ARM64, other distribution kernels, and
so on) are **untested**. Bindings, the generated `libc_port` errno/type headers,
and the libc++ runtime are all produced for the target kernel and compiler, so
switching kernels requires a rebuild and your own verification.

## Quick start

Create a module next to the repository:

```bash
python3 linuxcpp/python/build.py --init ../my_module
make -C ../my_module -j6
sudo insmod ../my_module/my_module.ko
cat /dev/my_module
sudo rmmod my_module
```

`--init` writes:

- `module.toml`: module and device names, optional binding configuration
- `Makefile`: kbuild-style declarations, forwarded to `linuxcpp/Makefile`
- `driver.cpp`: a minimal misc device

Alternatively, copy the template:

```bash
cp -r template mymodule
cd mymodule
python3 ../linuxcpp/python/build.py .
make -j6
```

The first build generates `Kbuild`, `generated/`, `generated/cxxflags.mk`, and
the entry `Makefile`. After that, `make -j6` in the module directory is enough.
C++ objects use `-MMD -MP` for header dependency tracking; C objects and the
final link are handled by kbuild. Use `--prepare-only` to generate build files
without compiling.

Modules that use the shared libc++ must load the runtime first:

```bash
sudo insmod linuxcpp/runtime/libcxx_runtime.ko
sudo insmod my_module.ko
```

## Repository commands

```bash
make runtime    # build linuxcpp/runtime/libcxx_runtime.ko
make examples   # build the runtime first, then all examples in parallel
make test       # run pytest
make check      # test + examples
make clean      # clean the runtime and examples
```

The default parallelism is 6; override with `make runtime JOBS=4`.
`examples/std_demo`, `examples/sysinfo_json`, and `examples/json_format` use
libc++, so `make examples` builds `libcxx_runtime.ko` first. Download libc++
before the first build:

```bash
python3 linuxcpp/libcxx_port/update_libcxx.py
```

Set `HTTPS_PROXY=http://127.0.0.1:7897` if the download needs a proxy.

## Documentation

The detailed documents are currently in Chinese:

| Document | Contents |
|---|---|
| [docs/build-system.md](docs/build-system.md) | `module.toml` `[build]`, Makefile/kbuild, build flow, kernel upgrades |
| [docs/bindings.md](docs/bindings.md) | `roots`/`extern`/`thunk`/`macro`/`headers` and diagnostics |
| [docs/usage.md](docs/usage.md) | `driver.cpp`, inheriting `misc_device<D>`, core library, ETL |
| [docs/libc.md](docs/libc.md) | kernel C library subset and generated headers |
| [docs/libcxx.md](docs/libcxx.md) | shared libc++ runtime, limitations, CTRE |
| [docs/device-model.md](docs/device-model.md) | C++ inheritance hierarchy for device/driver/bus/class/platform/attributes |
| [docs/troubleshooting.md](docs/troubleshooting.md) | link/load errors, debugging, editor setup |

## Examples

Every directory builds independently:

```bash
cd examples/hello_misc
python3 ../../linuxcpp/python/build.py .
sudo insmod hello_misc.ko
cat /dev/hello_misc
sudo rmmod hello_misc
```

| Directory | Contents |
|---|---|
| `examples/hello_misc` | minimal misc device with C-style fops |
| `examples/ioctl_misc` | ioctl, `copy_from_user`/`copy_to_user`, mutex, object-macro export |
| `examples/two_devices` | two misc devices in one module |
| `examples/kthread_demo` | kernel thread (non-device module) |
| `examples/device_model` | custom bus/driver/device, platform driver/device, sysfs attribute |
| `examples/sensor_bus` | abstract sensor interface, multiple inheritance, custom bus drivers, attribute group, misc monitor |
| `examples/etl_kv` | in-memory key-value store using ETL fixed-capacity containers |
| `examples/libc_demo` | C library subset without libc++ (`malloc/qsort/strtol/snprintf/printf/time`) |
| `examples/std_demo` | libc++ coverage: containers, optional/variant/any, chrono, charconv |
| `examples/sysinfo_json` | pretty-printed system statistics as JSON (RapidJSON writer) |
| `examples/json_format` | format a user-supplied JSON fd in place (RapidJSON SAX + explicit FPU region) |
| `raw_demo/` | minimal raw module |

`examples/README.md` explains how to download the optional libraries.

## Third-party libraries

- libc++ 20.1.8 is **not** bundled. `linuxcpp/libcxx_port/update_libcxx.py`
  downloads a pinned upstream tarball into the git-ignored `third_party/libcxx/`
  and applies the kernel patches from `linuxcpp/libcxx_port/patches/`.
- ETL, CTRE, and RapidJSON are **not** bundled either. Clone them into the
  same git-ignored `third_party/` directory when needed:

```bash
git clone --depth 1 --branch 20.49.0 https://github.com/ETLCPP/etl.git third_party/etl
git clone --depth 1 --branch v3.11.0 \
    https://github.com/hanickadot/compile-time-regular-expressions.git third_party/ctre
git clone --depth 1 --branch v1.1.0 https://github.com/Tencent/rapidjson.git third_party/rapidjson
```

The `json_format` example demonstrates explicit FPU use in a kernel module.
`kernel_fpu_begin()`/`kernel_fpu_end()` save and restore SIMD state and disable
preemption; the FPU region must not sleep, allocate with `GFP_KERNEL`, or run in
interrupt context. It is a demonstration, not a pattern for high-frequency
production code. An integer-only parser, or a JSON reader with its floating
point branch removed, avoids the FPU region entirely.

## License

The project is distributed under GPL-2.0-only, matching the Linux kernel; see
`LICENSE`.

libc++ is not distributed with the repository. It is downloaded on demand and
remains under Apache-2.0 WITH LLVM-exception. Downloaded third-party libraries
keep their own licenses (ETL and RapidJSON are MIT, CTRE is Apache-2.0).
Kernel module entry points use `MODULE_LICENSE("GPL")` to access GPL-only
kernel symbols.

Distributing the source of your own module (with its build scripts) is
generally fine. Distributing a combined `.ko` that links libc++ is the
problematic case: Apache-2.0 and GPL-2.0-only are not considered compatible.
Verify the licensing of the kernel and all dependencies before distributing
binaries.
