"""CLI entrypoint for plumed executable."""

import os
import sys
from pathlib import Path
from plumed_bin import setup_env, PACKAGE_DIR


def main():
    setup_env()
    bin_name = "plumed.exe" if sys.platform == "win32" else "plumed"
    bin_path = PACKAGE_DIR / "bin" / bin_name
    if not bin_path.exists():
        print(f"Error: PLUMED binary not found at {bin_path}", file=sys.stderr)
        sys.exit(1)

    if sys.platform != "win32":
        os.execv(str(bin_path), [str(bin_path)] + sys.argv[1:])
    else:
        import subprocess
        proc = subprocess.run([str(bin_path)] + sys.argv[1:])
        sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
