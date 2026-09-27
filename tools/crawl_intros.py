# -*- coding: utf-8 -*-
"""Fill empty intros for books already in the local catalog. Resumable overnight job."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_catalog import FetchBlocked, crawl_missing_intros  # noqa: E402


def _safe_print(msg: str) -> None:
    try:
        print(msg, flush=True)
        return
    except UnicodeEncodeError:
        pass
    encoding = getattr(sys.stdout, "encoding", None) or "gbk"
    stream = getattr(sys.stdout, "buffer", None)
    if stream is not None:
        stream.write((msg + "\n").encode(encoding, "replace"))
        stream.flush()
        return
    print(msg.encode(encoding, "replace").decode(encoding, "replace"), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="自动补全书库里还没有简介的书（可中断后续跑）")
    parser.add_argument("--delay", type=float, default=2.2, help="每本间隔秒数，默认 2.2")
    parser.add_argument("--limit", type=int, default=0, help="本轮最多处理几本，0 表示一直跑到没有")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
            sys.stderr.reconfigure(errors="replace")
        except Exception:
            pass

    try:
        crawl_missing_intros(delay=args.delay, log=_safe_print, limit=args.limit)
    except FetchBlocked as exc:
        _safe_print(str(exc))
        return 2
    except KeyboardInterrupt:
        from lib_catalog import request_crawl_stop

        request_crawl_stop()
        _safe_print("已记下停止，当前这本结束后会保存。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
