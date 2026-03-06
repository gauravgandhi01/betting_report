import argparse
import os
import tempfile
import urllib.request


def download(url: str, timeout_seconds: int = 30) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "betting-analysis-sync/1.0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        return resp.read()


def atomic_write_bytes(path: str, data: bytes) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_bets_", suffix=".csv", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync bets.csv from a published Google Sheet CSV URL")
    parser.add_argument("--url", required=True, help="Published CSV URL")
    parser.add_argument("--output", default="bets.csv", help="Local output path (default: bets.csv)")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    args = parser.parse_args()

    data = download(args.url, timeout_seconds=args.timeout)
    if not data or b"," not in data:
        raise RuntimeError("Downloaded content does not look like a CSV")

    atomic_write_bytes(args.output, data)
    print(f"Wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
