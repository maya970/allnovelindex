# -*- coding: utf-8 -*-
"""Rebuild catalog txt files from local yousuu.sqlite, keeping existing intros."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python tools/rebuild.py`
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_catalog import DEFAULT_SQLITE, rebuild_from_sqlite  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="从本地 yousuu.sqlite 重建分类 txt 书库")
    parser.add_argument(
        "--db",
        default=str(DEFAULT_SQLITE),
        help="sqlite 路径",
    )
    args = parser.parse_args()
    db = Path(args.db)
    if not db.exists():
        print("找不到数据库：", db)
        return 1

    def log(msg: str) -> None:
        print(msg)

    rebuild_from_sqlite(db, log=log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
