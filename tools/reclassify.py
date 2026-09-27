# -*- coding: utf-8 -*-
"""Reclassify all books into 男频/女频 folders and rewrite two-line shards."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_catalog import load_all_books, split_write  # noqa: E402


def main() -> int:
    def log(msg: str) -> None:
        print(msg, flush=True)

    books = load_all_books()
    log(f"读入 {len(books)} 本，开始按男频/女频重分并分片…")
    split_write(books, log=log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
