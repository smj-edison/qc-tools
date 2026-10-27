import os
import sys
from plumed_bin import setup_env

if __name__ == "__main__":
    env = setup_env()
    if len(sys.argv) > 1 and sys.argv[1] == "--sh":
        print(f'export PLUMED_KERNEL="{env["PLUMED_KERNEL"]}"')
        print(f'export PLUMED_ROOT="{env["PLUMED_ROOT"]}"')
        if "PATH" in env:
            print(f'export PATH="{env["PATH"]}"')
        if "LD_LIBRARY_PATH" in env:
            print(f'export LD_LIBRARY_PATH="{env["LD_LIBRARY_PATH"]}"')
    else:
        print("PLUMED environment active:")
        for k, v in env.items():
            if k in ("PATH", "LD_LIBRARY_PATH"):
                print(f"  {k} prepended with: {v.split(os.pathsep)[0]}")
            else:
                print(f"  {k} = {v}")
