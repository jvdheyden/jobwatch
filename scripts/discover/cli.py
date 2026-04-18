"""CLI compatibility wrapper for deterministic discovery."""

from __future__ import annotations


def main() -> int:
    from discover_jobs import main as legacy_main

    return legacy_main()


if __name__ == "__main__":
    raise SystemExit(main())
