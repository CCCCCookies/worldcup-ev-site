from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
TMP = ROOT / "tmp"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8020)
    args = parser.parse_args()

    TMP.mkdir(exist_ok=True)
    stdout = (TMP / f"uvicorn-{args.port}.out.log").open("ab")
    stderr = (TMP / f"uvicorn-{args.port}.err.log").open("ab")
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ],
        cwd=BACKEND,
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        close_fds=True,
        creationflags=flags,
    )
    (ROOT / "server.pid").write_text(str(process.pid), encoding="utf-8")
    print(f"http://{args.host}:{args.port}")
    print(process.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
