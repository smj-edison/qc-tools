"""PLUMED prebuilt binary runtime integration."""

import os
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
LIB_DIR = PACKAGE_DIR / "lib"
BIN_DIR = PACKAGE_DIR / "bin"
ROOT_DIR = LIB_DIR / "plumed"


def get_kernel_path() -> Path | None:
    for name in ["libplumedKernel.so", "libplumedKernel.dylib"]:
        cand = LIB_DIR / name
        if cand.exists():
            return cand
    return None


def setup_env() -> dict[str, str]:
    """Configure environment variables for PLUMED."""
    kernel = get_kernel_path()
    if not kernel:
        raise FileNotFoundError(f"PLUMED kernel library not found in {LIB_DIR}")

    env = {
        "PLUMED_KERNEL": str(kernel),
        "PLUMED_ROOT": str(ROOT_DIR) if ROOT_DIR.exists() else str(PACKAGE_DIR),
    }

    os.environ["PLUMED_KERNEL"] = env["PLUMED_KERNEL"]
    os.environ["PLUMED_ROOT"] = env["PLUMED_ROOT"]

    if BIN_DIR.exists():
        current_path = os.environ.get("PATH", "")
        if str(BIN_DIR) not in current_path.split(os.pathsep):
            os.environ["PATH"] = f"{BIN_DIR}{os.pathsep}{current_path}"
        env["PATH"] = os.environ["PATH"]

    if LIB_DIR.exists():
        current_ld = os.environ.get("LD_LIBRARY_PATH", "")
        if str(LIB_DIR) not in current_ld.split(os.pathsep):
            new_ld = f"{LIB_DIR}{os.pathsep}{current_ld}" if current_ld else str(LIB_DIR)
            os.environ["LD_LIBRARY_PATH"] = new_ld
        env["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH"]

    return env


# Auto-configure on import
try:
    setup_env()
except FileNotFoundError:
    pass
