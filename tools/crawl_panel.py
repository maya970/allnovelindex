# -*- coding: utf-8 -*-
"""Foreground collector window: live status, current book, log. Auto-starts."""

from __future__ import annotations

import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_catalog import (  # noqa: E402
    crawl_missing_intros,
    load_crawl_state,
    missing_intro_queue,
    request_crawl_stop,
)

BG = "#0d0b12"
PANEL = "#16121c"
GOLD = "#e4b45a"
TEXT = "#efe6d6"
MUTED = "#9a8f7e"
GREEN = "#6bcb77"
RED = "#d35d5d"
DIM = "#6e665a"


class CollectorWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("马克书库 · 采集中")
        self.geometry("780x640")
        self.minsize(640, 520)
        self.configure(bg=BG)
        self.attributes("-topmost", True)

        self._stop = threading.Event()
        self._running = False
        self._last_beat = 0.0
        self._pulse = False

        self.live = tk.StringVar(value="尚未开始")
        self.stats = tk.StringVar(value="正在读取进度…")
        self.current = tk.StringVar(value="当前：—")
        self.beat = tk.StringVar(value="还没有采集输出")
        self.pin = tk.BooleanVar(value=True)

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._tick)
        self.after(400, self._refresh_stats)
        self.after(800, self.start)

    def _label(self, parent, var, size=14, color=TEXT, bold=False) -> tk.Label:
        font = ("Microsoft YaHei UI", size, "bold" if bold else "normal")
        return tk.Label(parent, textvariable=var, bg=parent["bg"], fg=color, font=font, anchor="w", justify="left")

    def _build(self) -> None:
        pad = tk.Frame(self, bg=BG)
        pad.pack(fill="both", expand=True, padx=18, pady=16)

        self.banner = tk.Label(
            pad,
            textvariable=self.live,
            bg="#1c1810",
            fg=GOLD,
            font=("Microsoft YaHei UI", 28, "bold"),
            pady=16,
        )
        self.banner.pack(fill="x")

        self._label(pad, self.stats, 13, MUTED).pack(fill="x", pady=(14, 4))
        self._label(pad, self.current, 16, TEXT, True).pack(fill="x")
        self._label(pad, self.beat, 12, DIM).pack(fill="x", pady=(4, 10))

        row = tk.Frame(pad, bg=BG)
        row.pack(fill="x", pady=8)
        tk.Button(row, text="开始采集", command=self.start, bg=GOLD, fg="#1a1208", relief="flat", padx=16, pady=8).pack(side="left")
        tk.Button(row, text="停止并保存", command=self.stop, bg=PANEL, fg=TEXT, relief="flat", padx=16, pady=8).pack(side="left", padx=8)
        tk.Checkbutton(
            row,
            text="窗口置顶（一直看得见）",
            variable=self.pin,
            command=self._toggle_pin,
            bg=BG,
            fg=MUTED,
            selectcolor=PANEL,
            activebackground=BG,
            activeforeground=GOLD,
        ).pack(side="left", padx=8)

        tk.Label(pad, text="实时日志", bg=BG, fg=DIM, font=("Microsoft YaHei UI", 10)).pack(anchor="w", pady=(8, 4))
        self.log = ScrolledText(
            pad,
            height=18,
            wrap="word",
            bg=PANEL,
            fg=TEXT,
            insertbackground=GOLD,
            font=("Consolas", 11),
            relief="flat",
        )
        self.log.pack(fill="both", expand=True)

        ttk.Style().theme_use("clam")

    def _toggle_pin(self) -> None:
        self.attributes("-topmost", bool(self.pin.get()))

    def _set_live(self, text: str, color: str, banner_bg: str) -> None:
        self.live.set(text)
        self.banner.configure(fg=color, bg=banner_bg)
        self.title("马克书库 · " + text)

    def _append(self, msg: str) -> None:
        self._last_beat = time.time()
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        if msg.startswith("[") and "] " in msg:
            self.current.set("当前：" + msg.split("]", 1)[1].strip())

    def _tick(self) -> None:
        if self._running:
            ago = time.time() - self._last_beat if self._last_beat else 0
            self._pulse = not self._pulse
            if ago > 60:
                self._set_live("可能卡住了", RED, "#2a1010")
                self.beat.set(f"已经 {int(ago)} 秒没有新输出。可以点停止再开始。")
            else:
                mark = "●" if self._pulse else "○"
                self._set_live(f"{mark}  正在采集", GREEN if self._pulse else GOLD, "#132214")
                if self._last_beat:
                    self.beat.set(f"刚才还有输出（{int(ago)} 秒前）  {datetime.now().strftime('%H:%M:%S')}")
                else:
                    self.beat.set("正在排队，马上会出第一本…")
        self.after(500, self._tick)

    def _refresh_stats(self) -> None:
        def work() -> None:
            try:
                state = load_crawl_state()
                left = len(missing_intro_queue(state))
                filled = int(state.get("filled") or 0)
                empty = len(state.get("empty") or [])
                failed = len(state.get("failed") or {})
                hours = left * 2.2 / 3600
                msg = f"已写入 {filled} 本简介 · 还剩 {left} 本（约 {hours:.1f} 小时）· 无简介 {empty} · 失败 {failed}"
            except Exception as exc:
                msg = f"统计失败：{exc}"
            self.after(0, lambda: self.stats.set(msg))

        threading.Thread(target=work, daemon=True).start()
        self.after(15000, self._refresh_stats)

    def start(self) -> None:
        if self._running:
            return
        self._stop.clear()
        self._running = True
        self._last_beat = time.time()
        self._set_live("●  正在采集", GREEN, "#132214")
        self._append("采集窗口已打开，开始从断点继续…")

        def work() -> None:
            def log(msg: str) -> None:
                self.after(0, lambda m=msg: self._append(m))

            try:
                crawl_missing_intros(delay=2.2, should_stop=self._stop.is_set, log=log)
                msg = "本轮结束。进度已保存。"
            except Exception as exc:
                msg = f"采集中断：{exc}"
            self.after(0, lambda: self._stopped(msg))

        threading.Thread(target=work, daemon=True).start()

    def stop(self) -> None:
        if not self._running:
            return
        self._stop.set()
        request_crawl_stop()
        self._append("已点停止，等当前这本写完…")

    def _stopped(self, msg: str) -> None:
        self._running = False
        self._set_live("已停止", MUTED, "#1c1810")
        self.beat.set(msg)
        self._append(msg)
        self._refresh_stats()

    def _on_close(self) -> None:
        if self._running:
            self.stop()
            self.after(400, self.destroy)
            return
        self.destroy()


def main() -> None:
    CollectorWindow().mainloop()


if __name__ == "__main__":
    main()
