"""C++ 包装类的主机侧编译和运行测试。

这些类不依赖内核头，可以在用户态用 g++ 直接验证行为。
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDE = ROOT / "linuxcpp" / "include"


class WrapperTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def compile_and_run(self, source, extra_include=None):
        source_path = self.dir / "test.cpp"
        source_path.write_text(source, encoding="utf-8")
        exe = self.dir / "test"
        cmd = ["g++", "-std=gnu++20", "-fno-exceptions", "-fno-rtti",
               f"-I{INCLUDE}"]
        if extra_include is not None:
            cmd.append(f"-I{extra_include}")
        cmd += ["-o", str(exe), str(source_path)]
        subprocess.run(cmd, check=True)
        subprocess.run([str(exe)], check=True)

    def test_string_view_and_fixed_string(self):
        self.compile_and_run(r"""
#include "std/string_view.hpp"
#include "std/fixed_string.hpp"

using linuxcpp::std::string_view;
using linuxcpp::std::fixed_string;

int main()
{
    string_view text("hello");
    if (text.size() != 5 || text.empty())
        return 1;
    if (!text.starts_with("he") || !text.ends_with("lo"))
        return 2;
    if (text.find('l') != 2 || text.find('z') != string_view::npos)
        return 3;
    if (text.substr(1, 3) != string_view("ell"))
        return 4;
    if (text.compare("hellp") >= 0)
        return 5;
    string_view empty_view;
    if (!empty_view.substr(0).empty())
        return 11;

    fixed_string<4> value;
    if (!value.assign("abc") || value.size() != 3)
        return 6;
    if (value.assign("abcdef") || value.size() != 4)
        return 7;
    if (value.view() != string_view("abcd"))
        return 8;
    if (value.c_str()[4] != '\0')
        return 9;
    if (value.assign(nullptr) || value.size() != 0 || value.c_str()[0] != '\0')
        return 10;

    return 0;
}
""")

    def test_unique_ptr_array(self):
        self.compile_and_run(r"""
#include "std/memory.hpp"

using linuxcpp::std::unique_ptr;

int main()
{
    unique_ptr<int[]> values(new int[4]);
    values[0] = 7;
    values[3] = 9;
    if (!values || values[0] != 7 || values[3] != 9)
        return 1;

    unique_ptr<int> single(new int(3));
    if (!single || *single != 3)
        return 2;

    unique_ptr<int[]> moved(static_cast<unique_ptr<int[]>&&>(values));
    if (values || !moved || moved[0] != 7)
        return 3;

    return 0;
}
""")

    def test_vector_iterators_and_move(self):
        self.compile_and_run(r"""
#include "std/vector.hpp"

using linuxcpp::std::vector;

struct item {
    int value;
    explicit item(int v) : value(v) {}
    item(const item &) = delete;
    item &operator=(const item &) = delete;
    item(item &&other) noexcept : value(other.value) { other.value = -1; }
};

int main()
{
    vector<int> numbers;
    if (!numbers.push_back(1) || !numbers.push_back(2))
        return 1;
    int sum = 0;
    for (int value : numbers)
        sum += value;
    if (sum != 3 || numbers.front() != 1 || numbers.back() != 2)
        return 2;

    vector<int> moved(static_cast<vector<int>&&>(numbers));
    if (!numbers.empty() || moved.size() != 2 || moved.end() - moved.begin() != 2)
        return 3;

    vector<int> assigned;
    assigned = static_cast<vector<int>&&>(moved);
    if (!moved.empty() || assigned[1] != 2)
        return 4;

    vector<item> items;
    if (!items.emplace_back(7) || !items.emplace_back(8))
        return 5;
    items.pop_back();
    if (items.size() != 1 || items[0].value != 7)
        return 6;

    return 0;
}
""")

    def test_intrusive_list(self):
        bindings = self.dir / "bindings.hpp"
        bindings.write_text(
            "#pragma once\n"
            "namespace linuxcpp {\n"
            "struct list_head {\n"
            "    list_head *next;\n"
            "    list_head *prev;\n"
            "};\n"
            "}\n",
            encoding="utf-8",
        )
        self.compile_and_run(r"""
#include "bindings.hpp"
#include "wrappers/intrusive_list.hpp"

#include <stddef.h>

struct item {
    int value;
    linuxcpp::list_head node;
};

int main()
{
    linuxcpp::wrappers::intrusive_list<item, offsetof(item, node)> list;
    item a{1, {}};
    item b{2, {}};
    item c{3, {}};

    list.push_back(a);
    list.push_back(b);
    list.push_front(c);

    int order[] = {3, 1, 2};
    int index = 0;
    for (item &value : list) {
        if (value.value != order[index++])
            return 1;
    }
    if (index != 3)
        return 2;

    list.erase(a);
    for (item &value : list) {
        if (value.value != 3 && value.value != 2)
            return 3;
    }

    list.clear();
    if (!list.empty())
        return 4;

    const auto &const_list = list;
    if (const_list.begin() != const_list.end())
        return 5;

    return 0;
}
""", extra_include=self.dir)


    def test_more_wrappers(self):
        bindings = self.dir / "bindings.hpp"
        bindings.write_text(
            "#pragma once\n"
            "#include <stddef.h>\n"
            "namespace linuxcpp {\n"
            "struct hlist_node { hlist_node *next; hlist_node **pprev; };\n"
            "struct hlist_head { hlist_node *first; };\n"
            "struct timespec64 { long long tv_sec; long tv_nsec; };\n"
            "struct kvec { void *iov_base; size_t iov_len; };\n"
            "struct iovec { void *iov_base; size_t iov_len; };\n"
            "struct completion { unsigned int done; };\n"
            "typedef struct { int raw_lock; } spinlock_t;\n"
            "typedef struct { int counter; } atomic_t;\n"
            "void wait_for_completion(completion *);\n"
            "void complete(completion *);\n"
            "void complete_all(completion *);\n"
            "}\n"
            "extern \"C\" {\n"
            "void lc_init_completion(linuxcpp::completion *);\n"
            "void lc_spin_lock_init(linuxcpp::spinlock_t *);\n"
            "void lc_spin_lock(linuxcpp::spinlock_t *);\n"
            "void lc_spin_unlock(linuxcpp::spinlock_t *);\n"
            "int lc_atomic_read(const linuxcpp::atomic_t *);\n"
            "void lc_atomic_set(linuxcpp::atomic_t *, int);\n"
            "void lc_atomic_add(int, linuxcpp::atomic_t *);\n"
            "void lc_atomic_sub(int, linuxcpp::atomic_t *);\n"
            "void lc_atomic_inc(linuxcpp::atomic_t *);\n"
            "void lc_atomic_dec(linuxcpp::atomic_t *);\n"
            "}\n",
            encoding="utf-8",
        )
        self.compile_and_run(r"""
#include "bindings.hpp"
#include "wrappers/hlist.hpp"
#include "wrappers/timestamp.hpp"
#include "wrappers/kvec.hpp"
#include "wrappers/completion.hpp"
#include "wrappers/spinlock.hpp"
#include "wrappers/atomic.hpp"

#include <stddef.h>

extern "C" {
void lc_init_completion(linuxcpp::completion *value) { value->done = 0; }
void lc_spin_lock_init(linuxcpp::spinlock_t *value) { value->raw_lock = 0; }
void lc_spin_lock(linuxcpp::spinlock_t *) {}
void lc_spin_unlock(linuxcpp::spinlock_t *) {}
int lc_atomic_read(const linuxcpp::atomic_t *value) { return value->counter; }
void lc_atomic_set(linuxcpp::atomic_t *value, int v) { value->counter = v; }
void lc_atomic_add(int v, linuxcpp::atomic_t *value) { value->counter += v; }
void lc_atomic_sub(int v, linuxcpp::atomic_t *value) { value->counter -= v; }
void lc_atomic_inc(linuxcpp::atomic_t *value) { ++value->counter; }
void lc_atomic_dec(linuxcpp::atomic_t *value) { --value->counter; }
}

namespace linuxcpp {
void wait_for_completion(completion *) {}
void complete(completion *value) { ++value->done; }
void complete_all(completion *value) { value->done = ~0u; }
}

struct item {
    int value;
    linuxcpp::hlist_node node;
};

int main()
{
    linuxcpp::wrappers::hlist<item, offsetof(item, node)> list;
    item a{1, {}};
    item b{2, {}};
    list.push_front(a);
    list.push_front(b);

    if (list.front()->value != 2)
        return 1;
    int order[] = {2, 1};
    int index = 0;
    for (item &value : list) {
        if (value.value != order[index++])
            return 2;
    }
    if (!list.erase(b) || list.front()->value != 1)
        return 3;
    if (list.erase(b))
        return 4;

    linuxcpp::wrappers::timestamp first(1, 900000000);
    linuxcpp::wrappers::timestamp second(0, 200000000);
    if ((first + second).to_ns() != 2100000000LL)
        return 5;
    if (linuxcpp::wrappers::timestamp::from_ns(-1).to_ns() != -1)
        return 6;

    char buffer[8];
    linuxcpp::wrappers::kvec kvec(buffer, sizeof(buffer));
    if (kvec.data() != buffer || kvec.size() != sizeof(buffer))
        return 7;
    linuxcpp::wrappers::iovec iovec(buffer, sizeof(buffer));
    if (iovec.size() != sizeof(buffer))
        return 8;

    linuxcpp::wrappers::completion completion;
    completion.init();
    completion.complete();
    completion.complete_all();

    linuxcpp::wrappers::spinlock lock;
    lock.lock();
    lock.unlock();
    {
        linuxcpp::wrappers::spin_guard guard(lock);
    }

    linuxcpp::wrappers::atomic atomic;
    atomic.set(5);
    atomic.add(2);
    atomic.sub(1);
    atomic.inc();
    atomic.dec();
    if (atomic.get() != 6)
        return 9;

    return 0;
}
""", extra_include=self.dir)


if __name__ == "__main__":
    unittest.main()
