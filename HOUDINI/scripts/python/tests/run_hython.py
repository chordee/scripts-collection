"""Run the chd_toolkits test suite under Houdini's hython.

Usage:
    python tests/run_hython.py [pytest args...]

Requires:
    HFS env var pointing to a Houdini install root, e.g.
        Windows: C:/Program Files/Side Effects Software/Houdini 21.0.376
        Linux:   /opt/hfs21.0.376

Also requires pytest to be installed in hython's Python; one-time setup:
    hython -m pip install pytest
"""

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    hfs = os.environ.get("HFS")
    if not hfs:
        print(
            "HFS environment variable not set. Point it to your Houdini "
            "install root (e.g. C:/Program Files/Side Effects Software/Houdini 21.0.xxx).",
            file=sys.stderr,
        )
        return 2

    hython_name = "hython.exe" if os.name == "nt" else "hython"
    hython = Path(hfs) / "bin" / hython_name
    if not hython.is_file():
        print(f"hython not found at {hython}", file=sys.stderr)
        return 2

    tests_dir = Path(__file__).resolve().parent
    project_dir = tests_dir.parent  # HOUDINI/scripts/python/

    cmd = [str(hython), "-m", "pytest", str(tests_dir), *sys.argv[1:]]
    print(f"[run_hython] {' '.join(cmd)}", file=sys.stderr)
    return subprocess.call(cmd, cwd=project_dir)


if __name__ == "__main__":
    sys.exit(main())
