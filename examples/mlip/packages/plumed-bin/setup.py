import fnmatch
import io
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from setuptools import setup, find_packages
from setuptools.command.build_py import build_py


def get_platform_subdir() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        if machine in ("x86_64", "amd64"):
            return "linux-64"
        elif machine in ("aarch64", "arm64"):
            return "linux-aarch64"
    elif system == "darwin":
        if machine in ("arm64", "aarch64"):
            return "osx-arm64"
        elif machine in ("x86_64", "amd64"):
            return "osx-64"
    raise RuntimeError(f"Unsupported platform: {system} {machine}")


def extract_tar_bytes(tar_bytes: bytes, target_dir: Path, pattern: str | None = None):
    """Extract tar bytes using system tar (if available) or python zstandard."""
    if shutil.which("tar") and shutil.which("zstd"):
        cmd = ["tar", "-I", "zstd", "-xf", "-", "-C", str(target_dir)]
        if pattern:
            cmd.extend(["--wildcards", pattern])
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.communicate(input=tar_bytes)
        if proc.returncode == 0:
            return

    # Fallback to pure-python decompression via zstandard module
    import zstandard as zstd
    dctx = zstd.ZstdDecompressor()
    with dctx.stream_reader(io.BytesIO(tar_bytes)) as reader:
        with tarfile.open(fileobj=reader, mode="r|*") as tf:
            for member in tf:
                if pattern and not fnmatch.fnmatch(member.name, pattern):
                    continue
                tf.extract(member, path=target_dir)


def get_conda_package_url(pkg_name: str, subdir: str, version: str | None = None) -> tuple[str, str]:
    api_url = f"https://api.anaconda.org/package/conda-forge/{pkg_name}"
    print(f"[plumed-bin build] Querying {api_url} ({subdir})...")
    req = urllib.request.Request(api_url, headers={"User-Agent": "plumed-bin-builder/1.0"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    target_ver = version or data.get("latest_version")
    files = [
        f for f in data.get("files", [])
        if f.get("attrs", {}).get("subdir") == subdir and f.get("version") == target_ver
    ]
    if not files:
        files = [
            f for f in data.get("files", [])
            if f.get("attrs", {}).get("subdir") == subdir
        ]
    if not files:
        raise RuntimeError(f"Could not find package {pkg_name} on {subdir}")

    # Prefer nompi builds if available
    selected = None
    for f in files:
        if "nompi" in f.get("basename", ""):
            selected = f
            break
    if not selected:
        selected = files[-1]

    basename = selected.get("basename", "")
    download_url = selected.get("download_url")
    if download_url.startswith("//"):
        download_url = "https:" + download_url
    return download_url, Path(basename).name


def download_package(url: str, filename: str) -> Path:
    cache_dir = Path("/tmp/plumed_download_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive_path = cache_dir / filename

    if not archive_path.exists() or archive_path.stat().st_size == 0:
        print(f"[plumed-bin build] Downloading {url}...")
        req = urllib.request.Request(url, headers={"User-Agent": "plumed-bin-builder/1.0"})
        with urllib.request.urlopen(req) as resp, open(archive_path, "wb") as out:
            shutil.copyfileobj(resp, out)
        print(f"[plumed-bin build] Downloaded {archive_path.stat().st_size} bytes.")
    else:
        print(f"[plumed-bin build] Using cached package: {archive_path}")

    return archive_path


def extract_archive(archive_path: Path, target_dir: Path, pattern: str | None = None):
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, "r") as zf:
            pkg_tar = [n for n in zf.namelist() if n.startswith("pkg-")][0]
            tar_bytes = zf.read(pkg_tar)
            extract_tar_bytes(tar_bytes, target_dir, pattern)
    else:
        if shutil.which("tar"):
            cmd = ["tar", "-xf", str(archive_path), "-C", str(target_dir)]
            if pattern:
                cmd.extend(["--wildcards", pattern])
            subprocess.run(cmd, check=True)
        else:
            with tarfile.open(archive_path, mode="r:*") as tf:
                for member in tf:
                    if pattern and not fnmatch.fnmatch(member.name, pattern):
                        continue
                    tf.extract(member, path=target_dir)


def download_and_extract_all(version: str, target_dir: Path):
    target_dir.mkdir(parents=True, exist_ok=True)
    subdir = get_platform_subdir()

    # 1. Main PLUMED distribution
    url, filename = get_conda_package_url("plumed", subdir, version=version)
    plumed_pkg = download_package(url, filename)
    print(f"[plumed-bin build] Extracting PLUMED into {target_dir}...")
    extract_archive(plumed_pkg, target_dir)

    # 2. Bundle runtime libraries on Linux (fftw, gsl, openblas, libstdcxx, libgfortran)
    # This prevents 'version GLIBCXX not found' and missing math libraries on HPC/enterprise Linux nodes.
    if subdir.startswith("linux"):
        runtime_deps = [
            ("libstdcxx", "lib/libstdc++*.so*"),
            ("libgfortran5", "lib/libgfortran*.so*"),
            ("fftw", "lib/libfftw3*.so*"),
            ("gsl", "lib/libgsl*.so*"),
            ("libopenblas", "lib/libopenblas*.so*"),
        ]
        for dep_name, pattern in runtime_deps:
            try:
                dep_url, dep_file = get_conda_package_url(dep_name, subdir)
                dep_pkg = download_package(dep_url, dep_file)
                print(f"[plumed-bin build] Bundling {dep_name} into {target_dir}/lib...")
                extract_archive(dep_pkg, target_dir, pattern)
            except Exception as e:
                print(f"[plumed-bin build] Warning: Could not bundle {dep_name}: {e}")

        # Ensure BLAS / LAPACK symlinks exist pointing to OpenBLAS
        lib_dir = target_dir / "lib"
        if lib_dir.exists():
            openblas_target = None
            for cand in ["libopenblas.so.0", "libopenblas.so"]:
                if (lib_dir / cand).exists():
                    openblas_target = cand
                    break
            if not openblas_target:
                for f in lib_dir.iterdir():
                    if f.name.startswith("libopenblas") and ".so" in f.name:
                        openblas_target = f.name
                        break

            if openblas_target:
                for alias in ["libblas.so.3", "libcblas.so.3", "liblapack.so.3"]:
                    link_path = lib_dir / alias
                    if not link_path.exists():
                        link_path.symlink_to(openblas_target)

    # Ensure executable permissions
    bin_dir = target_dir / "bin"
    if bin_dir.exists():
        for f in bin_dir.iterdir():
            if f.is_file():
                f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    lib_dir = target_dir / "lib"
    if lib_dir.exists():
        for f in lib_dir.iterdir():
            if f.is_file() and (".so" in f.name or ".dylib" in f.name):
                f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class CustomBuildPy(build_py):
    def run(self):
        super().run()
        version = self.distribution.get_version()
        dest_pkg = Path(self.build_lib) / "plumed_bin"

        # Download and extract directly into the build directory
        download_and_extract_all(version, dest_pkg)

        # Create plumed_bin.pth in the root of site-packages
        pth_path = Path(self.build_lib) / "plumed_bin.pth"
        with open(pth_path, "w") as f:
            f.write("import plumed_bin\n")
        print(f"[plumed-bin build] Created auto-configuration hook: {pth_path}")


if __name__ == "__main__":
    setup(
        packages=find_packages(),
        cmdclass={
            "build_py": CustomBuildPy,
        },
        package_data={
            "plumed_bin": ["bin/*", "lib/*", "lib/**/*"],
        },
    )
