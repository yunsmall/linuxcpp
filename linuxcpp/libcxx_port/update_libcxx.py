#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""下载并 patch libc++ 20.1.8 到 third_party/libcxx。

固定上游 URL 和 SHA256，只解压内核需要的 include/、src/ 和 LICENSE，然后应用
patches/ 下的内核补丁。libc++ 本身不随仓库分发，这样也能审计改过哪些地方。

用法：python3 linuxcpp/libcxx_port/update_libcxx.py
"""

import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

VERSION = "20.1.8"
URL = ("https://github.com/llvm/llvm-project/releases/download/"
       f"llvmorg-{VERSION}/libcxx-{VERSION}.src.tar.xz")
SHA256 = "3e12992e3d1a0e648dc2e1c8c6b1dd31717ac8e684a25a302773667f47f75546"
PREFIX = f"libcxx-{VERSION}.src"

HERE = Path(__file__).resolve().parent
DEST = HERE.parent.parent / "third_party" / "libcxx"
PATCH_DIR = HERE / "patches"


def download(target):
    print(f"下载 {URL}")
    with urllib.request.urlopen(URL) as response, open(target, "wb") as handle:
        shutil.copyfileobj(response, handle)


def verify(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != SHA256:
        sys.exit(f"SHA256 不匹配：期望 {SHA256}，实际 {digest}")


def extract(tarball, target):
    # 只解压需要的部分，避免把 tests/docs 铺满临时目录
    wanted = (f"{PREFIX}/include/", f"{PREFIX}/src/", f"{PREFIX}/LICENSE.TXT")
    with tarfile.open(tarball) as archive:
        members = [m for m in archive.getmembers()
                   if m.name.startswith(wanted)]
        archive.extractall(target, members=members)


def apply_patches(root):
    patches = sorted(PATCH_DIR.glob("*.patch"))
    if not patches:
        sys.exit(f"{PATCH_DIR} 里没有补丁")
    for patch in patches:
        print(f"应用 {patch.name}")
        subprocess.run(["patch", "-p1", "-i", str(patch)], cwd=root, check=True)


def install(source):
    include = source / "include"
    src = source / "src"
    # 冻结的 C++03 头和 CMake 模板用不到
    shutil.rmtree(include / "__cxx03")
    (include / "__config_site.in").unlink()
    DEST.mkdir(parents=True, exist_ok=True)
    if (DEST / "include").exists():
        shutil.rmtree(DEST / "include")
    if (DEST / "src").exists():
        shutil.rmtree(DEST / "src")
    shutil.copytree(include, DEST / "include")
    shutil.copytree(src, DEST / "src")
    shutil.copy2(source / "LICENSE.TXT", DEST / "LICENSE.TXT")


def main():
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        tarball = temp / f"libcxx-{VERSION}.src.tar.xz"
        download(tarball)
        verify(tarball)
        extract(tarball, temp)
        source = temp / PREFIX
        apply_patches(source)
        install(source)
    print(f"libc++ {VERSION} 更新完成")


if __name__ == "__main__":
    main()
