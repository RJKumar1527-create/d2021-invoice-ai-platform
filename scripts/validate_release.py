from __future__ import annotations

import compileall
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run(command):
    print(
        "$",
        " ".join(command),
        flush=True,
    )

    subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=True,
    )


def main():
    directories = [
        "assurance",
        "processing",
        "configuration",
        "monitoring",
    ]

    for directory in directories:
        successful = compileall.compile_dir(
            PROJECT_ROOT / directory,
            quiet=1,
        )

        if not successful:
            raise SystemExit(
                f"Compilation failed: {directory}"
            )

    run(
        [
            sys.executable,
            "-m",
            "py_compile",
            "billing_finance_ops_app.py",
            "start_server.py",
        ]
    )

    node = shutil.which(
        "node"
    )

    if node:
        run(
            [
                node,
                "--check",
                (
                    "billing_finance_ops_web/"
                    "app.js"
                ),
            ]
        )

    else:
        print(
            "Node.js not available. "
            "JavaScript validation skipped."
        )

    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-v",
        ]
    )

    print(
        "Release validation passed."
    )


if __name__ == "__main__":
    main()