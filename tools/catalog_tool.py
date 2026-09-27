# -*- coding: utf-8 -*-
"""Local catalog desk tool: manual entry + yousuu.net single-book import."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_catalog import (  # noqa: E402
    CANON_ORDER,
    DEFAULT_SQLITE,
    ROOT,
    crawl_missing_intros,
    empty_book,
    fetch_user_id_list,
    fetch_yousuu_book,
    load_crawl_state,
    missing_intro_queue,
    normalize_book,
    rebuild_from_sqlite,
    request_crawl_stop,
    search_yousuu,
    split_write,
    upsert_books,
)


class CatalogApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("马克书库 · 本地录入工具")
        self.geometry("920x720")
        self.minsize(820, 640)
        self.db_path = tk.StringVar(value=str(DEFAULT_SQLITE))
        self.status = tk.StringVar(value="就绪。缺简介的书可在「自动补全」里通宵跑，进度会保存。")
        self._busy = False
        self._stop_event = threading.Event()
        self._build()

    def _build(self) -> None:
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        self.manual_tab = ttk.Frame(nb)
        self.fetch_tab = ttk.Frame(nb)
        self.crawl_tab = ttk.Frame(nb)
        self.batch_tab = ttk.Frame(nb)
        self.rebuild_tab = ttk.Frame(nb)
        nb.add(self.manual_tab, text="一本本登录")
        nb.add(self.fetch_tab, text="优书网导入")
        nb.add(self.crawl_tab, text="自动补全简介")
        nb.add(self.batch_tab, text="粘贴 ID 列表")
        nb.add(self.rebuild_tab, text="从 SQLite 重建")

        self._build_form(self.manual_tab)
        self._build_fetch(self.fetch_tab)
        self._build_crawl(self.crawl_tab)
        self._build_batch(self.batch_tab)
        self._build_rebuild(self.rebuild_tab)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(bar, textvariable=self.status, wraplength=860).pack(anchor="w")

    def _build_form(self, parent: ttk.Frame) -> None:
        hint = ttk.Label(
            parent,
            text="填完点「写入书库」。简介可多行。分类会按标签自动归到文件夹，你也可以手动指定。",
            wraplength=860,
        )
        hint.pack(anchor="w", padx=8, pady=8)

        grid = ttk.Frame(parent)
        grid.pack(fill="x", padx=8)

        self.vars = {
            "id": tk.StringVar(),
            "title": tk.StringVar(),
            "author": tk.StringVar(),
            "category": tk.StringVar(value="其他"),
            "tags": tk.StringVar(),
            "score": tk.StringVar(value="0"),
            "scorerCount": tk.StringVar(value="0"),
            "words": tk.StringVar(value="0"),
            "cover": tk.StringVar(),
            "link": tk.StringVar(),
        }

        rows = [
            ("优书网 ID", "id"),
            ("书名 *", "title"),
            ("作者", "author"),
            ("标签（逗号分隔）", "tags"),
            ("评分", "score"),
            ("评分人数", "scorerCount"),
            ("字数", "words"),
            ("封面 URL", "cover"),
            ("优书网链接", "link"),
        ]
        for i, (label, key) in enumerate(rows):
            ttk.Label(grid, text=label).grid(row=i, column=0, sticky="e", padx=(0, 8), pady=3)
            ttk.Entry(grid, textvariable=self.vars[key], width=78).grid(
                row=i, column=1, sticky="ew", pady=3
            )
        ttk.Label(grid, text="分类").grid(row=len(rows), column=0, sticky="e", padx=(0, 8), pady=3)
        ttk.Combobox(
            grid,
            textvariable=self.vars["category"],
            values=CANON_ORDER,
            state="readonly",
            width=24,
        ).grid(row=len(rows), column=1, sticky="w", pady=3)
        grid.columnconfigure(1, weight=1)

        ttk.Label(parent, text="简介").pack(anchor="w", padx=8, pady=(10, 4))
        self.intro = tk.Text(parent, height=10, wrap="word")
        self.intro.pack(fill="both", expand=True, padx=8)

        btns = ttk.Frame(parent)
        btns.pack(fill="x", padx=8, pady=10)
        ttk.Button(btns, text="写入书库", command=self.save_form).pack(side="left")
        ttk.Button(btns, text="清空表单", command=self.clear_form).pack(side="left", padx=8)

    def _build_fetch(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="只导入你指定的那一本：粘贴 https://www.yousuu.net/book/数字 或纯数字 ID。也可以先搜书名，再选中打开。不会整站爬库。",
            wraplength=860,
        ).pack(anchor="w", padx=8, pady=8)

        row = ttk.Frame(parent)
        row.pack(fill="x", padx=8, pady=4)
        ttk.Label(row, text="链接 / ID").pack(side="left")
        self.fetch_url = tk.StringVar()
        ttk.Entry(row, textvariable=self.fetch_url).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row, text="读取这一本", command=self.fetch_one).pack(side="left")

        row2 = ttk.Frame(parent)
        row2.pack(fill="x", padx=8, pady=8)
        ttk.Label(row2, text="搜书名").pack(side="left")
        self.search_key = tk.StringVar()
        ttk.Entry(row2, textvariable=self.search_key).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row2, text="搜索", command=self.search_site).pack(side="left")

        self.search_list = tk.Listbox(parent, height=12)
        self.search_list.pack(fill="both", expand=True, padx=8, pady=8)
        self.search_list.bind("<Double-Button-1>", lambda _e: self.fetch_selected())
        ttk.Button(parent, text="读取选中的这一本", command=self.fetch_selected).pack(
            anchor="w", padx=8, pady=(0, 8)
        )
        self._search_hits = []

    def _build_crawl(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="自动补全书库里还没有简介的书：只请求已有 ID 的公开页，评分高的优先。关掉或点停止都会保存，下次从断点继续。三万本大约要十几个小时，适合挂着跑。",
            wraplength=860,
        ).pack(anchor="w", padx=8, pady=8)
        self.crawl_info = tk.StringVar(value="正在统计缺简介的书…")
        ttk.Label(parent, textvariable=self.crawl_info).pack(anchor="w", padx=8, pady=4)

        row = ttk.Frame(parent)
        row.pack(fill="x", padx=8, pady=6)
        ttk.Label(row, text="间隔秒数").pack(side="left")
        self.crawl_delay = tk.StringVar(value="2.2")
        ttk.Entry(row, textvariable=self.crawl_delay, width=8).pack(side="left", padx=8)
        ttk.Button(row, text="开始补全", command=self.start_crawl).pack(side="left", padx=4)
        ttk.Button(row, text="停止并保存", command=self.stop_crawl).pack(side="left", padx=4)
        ttk.Button(row, text="刷新统计", command=self.refresh_crawl_stats).pack(side="left", padx=4)

        self.crawl_log = ScrolledText(parent, height=18, wrap="word")
        self.crawl_log.pack(fill="both", expand=True, padx=8, pady=8)
        self.after(200, self.refresh_crawl_stats)

    def _build_batch(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="把你自己整理好的优书网链接或 ID 粘进来（空格 / 逗号 / 换行均可）。只会请求列表里这些书，每本间隔约 1.6 秒。",
            wraplength=860,
        ).pack(anchor="w", padx=8, pady=8)
        self.batch_text = tk.Text(parent, height=18, wrap="word")
        self.batch_text.pack(fill="both", expand=True, padx=8)
        ttk.Button(parent, text="按列表导入并写入", command=self.fetch_list).pack(
            anchor="w", padx=8, pady=10
        )

    def _build_rebuild(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="用本地 yousuu.sqlite 重建全部分类 txt。已有简介会按 ID 保留。重建后直接把 data/books/ 和 data/manifest.json 上传到 GitHub 即可。",
            wraplength=860,
        ).pack(anchor="w", padx=8, pady=8)
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=8, pady=8)
        ttk.Entry(row, textvariable=self.db_path).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="浏览…", command=self.browse_db).pack(side="left", padx=8)
        ttk.Button(parent, text="从数据库重建全部分卷", command=self.rebuild).pack(
            anchor="w", padx=8, pady=8
        )
        ttk.Label(
            parent,
            text="仓库根目录：\n" + str(ROOT),
            wraplength=860,
        ).pack(anchor="w", padx=8, pady=16)

    def set_status(self, text: str) -> None:
        self.status.set(text)
        self.update_idletasks()

    def busy(self, flag: bool) -> None:
        self._busy = flag

    def fill_form(self, book: dict) -> None:
        for key, var in self.vars.items():
            var.set(str(book.get(key, "") or ""))
        self.intro.delete("1.0", "end")
        self.intro.insert("1.0", book.get("intro") or "")

    def clear_form(self) -> None:
        self.fill_form(empty_book())
        self.vars["category"].set("其他")
        self.set_status("表单已清空。")

    def form_book(self) -> dict:
        data = {k: v.get() for k, v in self.vars.items()}
        data["intro"] = self.intro.get("1.0", "end").strip()
        book = normalize_book(data)
        if not book:
            raise ValueError("书名不能为空。")
        return book

    def save_form(self) -> None:
        if self._busy:
            return
        try:
            book = self.form_book()
        except ValueError as exc:
            messagebox.showerror("无法保存", str(exc))
            return
        self.busy(True)

        def work() -> None:
            logs = []
            try:
                manifest = upsert_books([book], log=logs.append)
                msg = f"已写入《{book['title']}》→ {book['category']}，当前书库 {manifest['count']} 本。"
            except Exception as exc:
                msg = f"写入失败：{exc}"
            self.after(0, lambda: self._done(msg, "\n".join(logs)))

        threading.Thread(target=work, daemon=True).start()
        self.set_status("正在写入分类文件夹…")

    def fetch_one(self) -> None:
        self._fetch_async(self.fetch_url.get().strip())

    def fetch_selected(self) -> None:
        sel = self.search_list.curselection()
        if not sel:
            messagebox.showinfo("提示", "先在搜索结果里点一本。")
            return
        hit = self._search_hits[sel[0]]
        self.fetch_url.set(hit["link"])
        self._fetch_async(hit["link"])

    def _fetch_async(self, url_or_id: str) -> None:
        if self._busy:
            return
        if not url_or_id:
            messagebox.showinfo("提示", "请填写优书网链接或 ID。")
            return
        self.busy(True)
        self.set_status("正在读取优书网这一本书…")

        def work() -> None:
            try:
                book = fetch_yousuu_book(url_or_id)
                self.after(0, lambda: self._fetched(book))
            except Exception as exc:
                self.after(0, lambda: self._done(f"读取失败：{exc}"))

        threading.Thread(target=work, daemon=True).start()

    def _fetched(self, book: dict) -> None:
        self.busy(False)
        self.fill_form(book)
        self.set_status(f"已填入《{book['title']}》。可改简介后再写入。")
        if messagebox.askyesno("已读取", f"《{book['title']}》已填进表单。\n要现在写入书库吗？\n选「否」可先到「一本本登录」里改简介。"):
            self.save_form()

    def search_site(self) -> None:
        if self._busy:
            return
        key = self.search_key.get().strip()
        if not key:
            messagebox.showinfo("提示", "请输入书名关键词。")
            return
        self.busy(True)
        self.set_status("正在搜索…")

        def work() -> None:
            try:
                hits = search_yousuu(key)
                self.after(0, lambda: self._show_hits(hits))
            except Exception as exc:
                self.after(0, lambda: self._done(f"搜索失败：{exc}"))

        threading.Thread(target=work, daemon=True).start()

    def _show_hits(self, hits) -> None:
        self.busy(False)
        self._search_hits = hits
        self.search_list.delete(0, "end")
        if not hits:
            self.set_status("没有搜到。可改关键词，或直接粘贴书籍链接。")
            return
        for hit in hits:
            self.search_list.insert("end", f"{hit['title']}    {hit['link']}")
        self.set_status(f"搜到 {len(hits)} 条，双击即可读取。")

    def fetch_list(self) -> None:
        if self._busy:
            return
        blob = self.batch_text.get("1.0", "end")
        self.busy(True)
        self.set_status("正在按列表读取…")

        def work() -> None:
            logs = []
            try:
                books = fetch_user_id_list(blob, log=logs.append)
                if not books:
                    raise ValueError("列表里没有成功读到任何一本。")
                manifest = upsert_books(books, log=logs.append)
                msg = f"成功写入 {len(books)} 本，书库现有 {manifest['count']} 本。"
            except Exception as exc:
                msg = f"导入失败：{exc}"
            self.after(0, lambda: self._done(msg, "\n".join(logs)))

        threading.Thread(target=work, daemon=True).start()

    def refresh_crawl_stats(self) -> None:
        def work() -> None:
            try:
                state = load_crawl_state()
                left = len(missing_intro_queue(state))
                filled = int(state.get("filled") or 0)
                empty = len(state.get("empty") or [])
                failed = len(state.get("failed") or {})
                hours = left * 2.2 / 3600
                msg = (
                    f"还缺简介 {left} 本，大约 {hours:.1f} 小时。"
                    f"已写入 {filled}，页面无简介 {empty}，失败 {failed}。"
                )
            except Exception as exc:
                msg = f"统计失败：{exc}"
            self.after(0, lambda: self.crawl_info.set(msg))

        threading.Thread(target=work, daemon=True).start()

    def _append_crawl_log(self, msg: str) -> None:
        self.crawl_log.insert("end", msg + "\n")
        self.crawl_log.see("end")
        self.set_status(msg)

    def start_crawl(self) -> None:
        if self._busy:
            messagebox.showinfo("提示", "已有任务在跑。要停就点「停止并保存」。")
            return
        try:
            delay = float(self.crawl_delay.get() or "2.2")
        except ValueError:
            messagebox.showerror("间隔无效", "间隔秒数必须是数字。")
            return
        if delay < 1.2:
            messagebox.showerror("太快了", "间隔不要低于 1.2 秒，避免把优书网打挂。")
            return
        self._stop_event.clear()
        self.busy(True)
        self._append_crawl_log("开始补全…")

        def work() -> None:
            def log(msg: str) -> None:
                self.after(0, lambda m=msg: self._append_crawl_log(m))

            try:
                crawl_missing_intros(
                    delay=delay,
                    should_stop=self._stop_event.is_set,
                    log=log,
                )
                msg = "补全任务结束。进度已保存，缺的下次会接着跑。"
            except Exception as exc:
                msg = f"补全中断：{exc}"
            self.after(0, lambda: self._crawl_finished(msg))

        threading.Thread(target=work, daemon=True).start()

    def stop_crawl(self) -> None:
        self._stop_event.set()
        request_crawl_stop()
        self._append_crawl_log("已请求停止，等当前这本写完…")

    def _crawl_finished(self, msg: str) -> None:
        self.busy(False)
        self._append_crawl_log(msg)
        self.refresh_crawl_stats()
        messagebox.showinfo("补全结束", msg)

    def browse_db(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 yousuu.sqlite",
            filetypes=[("SQLite", "*.sqlite *.db"), ("全部", "*.*")],
        )
        if path:
            self.db_path.set(path)

    def rebuild(self) -> None:
        if self._busy:
            return
        db = Path(self.db_path.get())
        if not db.exists():
            messagebox.showerror("找不到数据库", str(db))
            return
        if not messagebox.askyesno("确认重建", "会重写 data/books/ 全部分卷（已有简介按 ID 保留）。继续吗？"):
            return
        self.busy(True)
        self.set_status("正在从数据库重建…")

        def work() -> None:
            logs = []
            try:
                manifest = rebuild_from_sqlite(db, log=logs.append)
                msg = f"重建完成：{manifest['count']} 本，{len(manifest['categories'])} 个分类。"
            except Exception as extra:
                msg = f"重建失败：{extra}"
            self.after(0, lambda: self._done(msg, "\n".join(logs)))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, msg: str, detail: str = "") -> None:
        self.busy(False)
        self.set_status(msg)
        if detail:
            print(detail)
        if msg.startswith("写入失败") or msg.startswith("读取失败") or msg.startswith("重建失败") or msg.startswith("导入失败") or msg.startswith("搜索失败"):
            messagebox.showerror("出错", msg)
        else:
            messagebox.showinfo("完成", msg)


def main() -> None:
    app = CatalogApp()
    app.mainloop()


if __name__ == "__main__":
    main()
