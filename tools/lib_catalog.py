# -*- coding: utf-8 -*-
"""Shared catalog helpers: category mapping, txt JSONL IO, yousuu page import."""

from __future__ import annotations

import json
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
BOOKS_DIR = DATA_DIR / "books"
MANIFEST_PATH = DATA_DIR / "manifest.json"
CRAWL_STATE_PATH = Path(__file__).resolve().parent / "crawl_state.json"
CRAWL_STOP_PATH = Path(__file__).resolve().parent / ".crawl_stop"
DEFAULT_SQLITE = Path(r"c:\谷歌插件\自动翻译\yousuu.sqlite")

PER_FILE = 80
MAX_PART_BYTES = 180_000
YOUSUU_ORIGIN = "https://www.yousuu.net"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

CATEGORIES = [
    ("玄幻", "xuanhuan", "男频"),
    ("奇幻", "qihuan", "男频"),
    ("武侠", "wuxia", "男频"),
    ("仙侠", "xianxia", "男频"),
    ("都市", "dushi", "男频"),
    ("现实", "xianshi", "男频"),
    ("军事", "junshi", "男频"),
    ("历史", "lishi", "男频"),
    ("悬疑", "xuanyi", "男频"),
    ("游戏", "youxi", "男频"),
    ("竞技", "jingji", "男频"),
    ("科幻", "kehuan", "男频"),
    ("灵异", "lingyi", "男频"),
    ("二次元", "erciyuan", "男频"),
    ("同人", "tongren", "男频"),
    ("其他", "qita", "男频"),
    ("穿越时空", "chuanyue", "女频"),
    ("架空历史", "jiakong", "女频"),
    ("总裁豪门", "zongcai", "女频"),
    ("都市言情", "dushi_yanqing", "女频"),
    ("仙侠奇缘", "xianxia_qiyuan", "女频"),
    ("幻想言情", "huanxiang_yanqing", "女频"),
    ("悬疑推理", "xuanyi_tuili", "女频"),
    ("耽美纯爱", "danmei", "女频"),
    ("衍生同人", "yansheng", "女频"),
    ("轻小说", "lightnovel", "女频"),
    ("综合其他", "zonghe", "女频"),
]

CANON_ORDER = [name for name, _, _ in CATEGORIES]
CANON_SET = set(CANON_ORDER)
SLUG_BY_NAME = {name: slug for name, slug, _ in CATEGORIES}
GROUP_BY_NAME = {name: group for name, _, group in CATEGORIES}
NAME_BY_SLUG = {slug: name for name, slug, _ in CATEGORIES}
FEMALE_SET = {name for name, _, group in CATEGORIES if group == "女频"}
MALE_SET = {name for name, _, group in CATEGORIES if group == "男频"}
CHANNEL_DIR = {"男频": "male", "女频": "female"}

# 能确定是女频的标签优先，覆盖原先误分到男频/未分类的书。
FEMALE_RULES = [
    (["耽美纯爱", "耽美", "强强", "BL"], "耽美纯爱"),
    (["总裁豪门", "豪门世家"], "总裁豪门"),
    (["都市言情", "都市情缘", "现代言情"], "都市言情"),
    (["仙侠奇缘"], "仙侠奇缘"),
    (["幻想言情", "幻想空间"], "幻想言情"),
    (["悬疑推理"], "悬疑推理"),
    (["穿越时空", "快穿", "穿书"], "穿越时空"),
    (["架空历史", "清穿", "古代言情", "宫廷侯爵", "种田文", "宫斗", "宅斗"], "架空历史"),
    (["衍生同人", "英美衍生", "西方名著", "衍生-"], "衍生同人"),
    (["轻小说"], "轻小说"),
    (["言情"], "都市言情"),
    (["女强", "女配", "甜文", "虐文", "团宠", "白月光"], "综合其他"),
]

FEMALE_TITLE_RULES = [
    ("女配", "综合其他"),
    ("穿书", "穿越时空"),
    ("穿成", "穿越时空"),
    ("嫡女", "架空历史"),
    ("庶女", "架空历史"),
    ("农女", "架空历史"),
    ("闺秀", "架空历史"),
    ("王妃", "架空历史"),
    ("皇后", "架空历史"),
    ("炮灰女", "综合其他"),
    ("团宠", "综合其他"),
    ("白月光", "综合其他"),
]

# First matching keyword wins. Longer / more specific phrases first.
TAG_RULES = [
    (["同人小说", "同人"], "同人"),
    (["二次元", "宅文", "综漫", "诸天无限", "无限流", "火影", "猎人", "网王", "少年漫"], "二次元"),
    (["历史军事"], "历史"),
    (["武侠仙侠", "仙侠武侠", "仙侠修真", "仙侠"], "仙侠"),
    (["玄幻奇幻", "奇幻玄幻", "东方玄幻", "玄幻"], "玄幻"),
    (["奇幻魔幻", "西幻传说", "奇幻", "魔幻"], "奇幻"),
    (["科幻空间", "科幻游戏", "科幻"], "科幻"),
    (["游戏竞技", "游戏"], "游戏"),
    (["都市娱乐", "都市小说", "娱乐圈", "都市"], "都市"),
    (["灵异神怪", "灵异", "恐怖"], "灵异"),
    (["悬疑"], "悬疑"),
    (["军事"], "军事"),
    (["历史"], "历史"),
    (["武侠", "江湖恩怨"], "武侠"),
    (["体育", "竞技"], "竞技"),
    (["现实"], "现实"),
    (["系统"], "二次元"),
]


def parse_tags(raw: str) -> List[str]:
    if not raw:
        return []
    return [t.strip() for t in str(raw).replace("，", ",").split(",") if t.strip()]


def classify(tags_raw: str, fallback: str = "") -> str:
    return classify_book({"tags": tags_raw, "title": "", "category": fallback})


def classify_book(book: dict) -> str:
    tags = parse_tags(book.get("tags") or "")
    title = str(book.get("title") or "")
    current = str(book.get("category") or "").strip()
    if current == "未分类":
        current = ""

    for keys, cat in FEMALE_RULES:
        for key in keys:
            if any(key in t for t in tags) or key in title:
                return cat
    for key, cat in FEMALE_TITLE_RULES:
        if key in title:
            return cat
    if current in FEMALE_SET:
        return current

    for t in tags:
        if t in MALE_SET:
            return t
    for t in tags:
        if t in CANON_SET:
            return t

    blob = " ".join(tags)
    for keys, cat in TAG_RULES:
        for key in keys:
            if key in blob or any(key in t for t in tags):
                return cat

    if current in MALE_SET:
        return current
    return "其他"


def slug_for(category: str) -> str:
    return SLUG_BY_NAME.get(category, "qita")


def channel_dir(category: str) -> str:
    group = GROUP_BY_NAME.get(category, "男频")
    return CHANNEL_DIR.get(group, "male")


def category_dir(category: str) -> Path:
    return BOOKS_DIR / channel_dir(category) / slug_for(category)


def empty_book() -> dict:
    return {
        "id": "",
        "title": "",
        "author": "",
        "category": "其他",
        "tags": "",
        "score": 0.0,
        "scorerCount": 0,
        "words": 0,
        "cover": "",
        "intro": "",
        "link": "",
    }


def normalize_book(raw: dict) -> Optional[dict]:
    if not raw:
        return None
    title = str(raw.get("title") or "").strip()
    if not title:
        return None
    tags = str(raw.get("tags") or "").strip()
    category = classify_book(
        {"tags": tags, "title": title, "category": str(raw.get("category") or "").strip()}
    )
    book_id = str(raw.get("id") or "").strip()
    link = str(raw.get("link") or "").strip()
    if not link and book_id.isdigit():
        link = f"{YOUSUU_ORIGIN}/book/{book_id}"
    try:
        score = round(float(raw.get("score") or 0), 1)
    except (TypeError, ValueError):
        score = 0.0
    try:
        scorer = int(float(raw.get("scorerCount") or 0))
    except (TypeError, ValueError):
        scorer = 0
    try:
        words = int(float(raw.get("words") or 0))
    except (TypeError, ValueError):
        words = 0
    intro = str(raw.get("intro") or "").replace("\r\n", "\n").strip()
    if len(intro) > 1200:
        intro = intro[:1197] + "…"
    return {
        "id": book_id,
        "title": title,
        "author": str(raw.get("author") or "").strip(),
        "category": category,
        "tags": tags,
        "score": score,
        "scorerCount": scorer,
        "words": words,
        "cover": str(raw.get("cover") or "").strip(),
        "intro": intro,
        "link": link,
    }


def book_key(book: dict) -> str:
    if book.get("id"):
        return "id:" + str(book["id"]).strip()
    title = str(book.get("title") or "").strip().lower()
    author = str(book.get("author") or "").strip().lower()
    return "ta:" + title + "|" + author


def read_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    out = []
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].replace("\ufeff", "").rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if stripped.startswith("{"):
            try:
                rec = json.loads(stripped)
            except json.JSONDecodeError:
                i += 1
                continue
            intro = str(rec.get("intro") or "")
            if i + 1 < len(lines):
                nxt_s = lines[i + 1].strip()
                if nxt_s and not nxt_s.startswith("{"):
                    intro = lines[i + 1]
                    i += 1
            rec["intro"] = intro
            book = normalize_book(rec)
            if book:
                out.append(book)
        i += 1
    return out


def write_jsonl(path: Path, books: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks = [
        json.dumps(book, ensure_ascii=False, separators=(",", ":")) for book in books
    ]
    path.write_text("\n".join(chunks) + ("\n" if chunks else ""), encoding="utf-8")


def iter_part_files(root: Path = BOOKS_DIR) -> List[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.txt") if p.is_file())


def wipe_part_files(root: Path = BOOKS_DIR) -> None:
    if not root.exists():
        return
    for path in list(root.rglob("*.txt")):
        path.unlink()
    for folder in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        try:
            folder.rmdir()
        except OSError:
            pass


def load_all_books(root: Path = BOOKS_DIR) -> List[dict]:
    books = []
    for path in iter_part_files(root):
        books.extend(read_jsonl(path))
    return books


def books_by_key(books: Iterable[dict]) -> Dict[str, dict]:
    merged: Dict[str, dict] = {}
    for book in books:
        key = book_key(book)
        old = merged.get(key)
        if old:
            if not book.get("intro") and old.get("intro"):
                book["intro"] = old["intro"]
            if not book.get("cover") and old.get("cover"):
                book["cover"] = old["cover"]
        merged[key] = book
    return merged


def sort_books(books: List[dict]) -> List[dict]:
    return sorted(
        books,
        key=lambda b: (
            -(float(b.get("score") or 0)),
            -(int(b.get("scorerCount") or 0)),
            str(b.get("title") or ""),
        ),
    )


def write_manifest(grouped: Dict[str, List[dict]]) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cats = []
    total = 0
    for name, slug, group in CATEGORIES:
        items = grouped.get(name) or []
        if not items:
            continue
        n = len(items)
        total += n
        folder = BOOKS_DIR / CHANNEL_DIR[group] / slug
        existing = sorted(folder.glob("part-*.txt")) if folder.exists() else []
        files = [f"data/books/{CHANNEL_DIR[group]}/{slug}/{p.name}" for p in existing]
        if not files:
            parts = max(1, (n + PER_FILE - 1) // PER_FILE)
            files = [
                f"data/books/{CHANNEL_DIR[group]}/{slug}/part-{i:03d}.txt"
                for i in range(1, parts + 1)
            ]
        cats.append(
            {
                "id": slug,
                "name": name,
                "group": group,
                "count": n,
                "files": files,
            }
        )
    payload = {
        "title": "马克书库",
        "source": "yousuu.sqlite / yousuu.net",
        "disclaimer": "书目来自优书网元数据快照（约 2024 年前）及站长后续本地增补，不是实时榜。",
        "count": total,
        "perFile": PER_FILE,
        "categories": cats,
    }
    MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def split_write(books: Iterable[dict], log: Optional[Callable[[str], None]] = None) -> dict:
    """Dedup, group by category, write part files, refresh manifest."""
    merged = books_by_key(books)
    grouped: Dict[str, List[dict]] = {name: [] for name, _, _ in CATEGORIES}
    for book in merged.values():
        cat = classify_book(book)
        book["category"] = cat
        grouped.setdefault(cat, []).append(book)

    wipe_part_files(BOOKS_DIR)

    total = 0
    for name, slug, group in CATEGORIES:
        items = sort_books(grouped.get(name) or [])
        grouped[name] = items
        if not items:
            continue
        folder = BOOKS_DIR / CHANNEL_DIR[group] / slug
        folder.mkdir(parents=True, exist_ok=True)
        part_no = 1
        chunk: List[dict] = []
        chunk_bytes = 0
        for book in items:
            size = len(json.dumps(book, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 1
            if chunk and (len(chunk) >= PER_FILE or chunk_bytes + size > MAX_PART_BYTES):
                part = folder / f"part-{part_no:03d}.txt"
                write_jsonl(part, chunk)
                total += len(chunk)
                if log:
                    log(f"写入 {part.relative_to(ROOT)}  ({len(chunk)} 本)")
                part_no += 1
                chunk = []
                chunk_bytes = 0
            chunk.append(book)
            chunk_bytes += size
        if chunk:
            part = folder / f"part-{part_no:03d}.txt"
            write_jsonl(part, chunk)
            total += len(chunk)
            if log:
                log(f"写入 {part.relative_to(ROOT)}  ({len(chunk)} 本)")

    manifest = write_manifest(grouped)
    if log:
        log(f"完成：共 {manifest['count']} 本，{len(manifest['categories'])} 个分类")
    return manifest


def upsert_books(new_books: Iterable[dict], log: Optional[Callable[[str], None]] = None) -> dict:
    current = load_all_books()
    current.extend(list(new_books))
    return split_write(current, log=log)


def load_sqlite_books(db_path: Path) -> List[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT bookId, status, tags, score, scorerCount, title, countWord, author, cover, updateAt
        FROM books
        WHERE title IS NOT NULL AND TRIM(title) != ''
        """
    ).fetchall()
    conn.close()
    books = []
    for row in rows:
        books.append(
            normalize_book(
                {
                    "id": row["bookId"],
                    "title": row["title"],
                    "author": row["author"],
                    "tags": row["tags"],
                    "score": row["score"],
                    "scorerCount": row["scorerCount"],
                    "words": row["countWord"],
                    "cover": row["cover"],
                    "intro": "",
                    "link": f"{YOUSUU_ORIGIN}/book/{row['bookId']}",
                }
            )
        )
    return [b for b in books if b]


def rebuild_from_sqlite(
    db_path: Path, log: Optional[Callable[[str], None]] = None
) -> dict:
    if log:
        log(f"读取数据库 {db_path}")
    incoming = load_sqlite_books(db_path)
    if log:
        log(f"数据库有效书目 {len(incoming)} 本，正在与现有简介合并…")
    existing = books_by_key(load_all_books())
    merged = []
    for book in incoming:
        old = existing.get(book_key(book))
        if old:
            if old.get("intro") and not book.get("intro"):
                book["intro"] = old["intro"]
            if old.get("cover") and not book.get("cover"):
                book["cover"] = old["cover"]
        merged.append(book)
    # keep locally added books that are not in sqlite
    sqlite_keys = {book_key(b) for b in incoming}
    for key, old in existing.items():
        if key not in sqlite_keys:
            merged.append(old)
    return split_write(merged, log=log)


def strip_html(html: str) -> str:
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</p>", "\n", html)
    html = re.sub(r"<[^>]+>", "", html)
    html = unescape(html)
    html = html.replace("\xa0", " ")
    html = re.sub(r"[ \t]+\n", "\n", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


class FetchBlocked(RuntimeError):
    """Site returned a challenge / block page."""


def http_get(url: str, timeout: int = 45, retries: int = 2) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": YOUSUU_ORIGIN + "/",
        },
    )
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                charset = "utf-8"
                ctype = resp.headers.get("Content-Type") or ""
                m = re.search(r"charset=([\w-]+)", ctype, re.I)
                if m:
                    charset = m.group(1)
                html = raw.decode(charset, "replace")
            low = html[:2500].lower()
            if "just a moment" in low or "cf-browser-verification" in low:
                raise FetchBlocked("优书网返回了验证页，需要停一会儿再继续。")
            return html
        except FetchBlocked:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
    raise last_err or RuntimeError("请求失败")


def parse_book_id(text: str) -> str:
    text = (text or "").strip()
    m = re.search(r"/book/(\d+)", text)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d+", text):
        return text
    return ""


def parse_yousuu_book(html: str, book_id: str) -> dict:
    title = ""
    m = re.search(
        r'font-size:20px;font-weight:bold;color:#f27622;">([^<]+)', html
    )
    if m:
        title = unescape(m.group(1)).strip()
    if not title:
        m = re.search(r"<title>([^<]+)</title>", html, re.I)
        if m:
            title = unescape(m.group(1)).split("-")[0].strip()

    author = ""
    m = re.search(r"作者：\s*<a[^>]*>([^<]+)</a>", html)
    if m:
        author = unescape(m.group(1)).strip()

    score = 0.0
    m = re.search(r'class="ratenum">\s*([0-9.]+)', html)
    if m:
        try:
            score = round(float(m.group(1)), 1)
        except ValueError:
            score = 0.0

    scorer = 0
    m = re.search(r"\((\d+)\s*人已评\)", html)
    if not m:
        m = re.search(r'class="scorer-count">\s*(\d+)\s*个评分', html)
    if m:
        scorer = int(m.group(1))

    category = ""
    m = re.search(r"作品分类：([^<]+)", html)
    if m:
        category = unescape(m.group(1)).strip()

    words = 0
    m = re.search(r"全文字数：\s*(\d+)", html)
    if m:
        words = int(m.group(1))

    cover = ""
    m = re.search(r'class="book-detail-img"[^>]*>\s*<img[^>]+src="([^"]+)"', html)
    if m:
        cover = m.group(1).strip()

    tags = [unescape(t).strip() for t in re.findall(r'class="tag-link"[^>]*>([^<]+)', html)]
    tags = [t for t in tags if t]
    if category and category not in tags:
        tags.insert(0, category)

    intro = ""
    m = re.search(
        r"内容介绍</a>.*?<div class=\"tabvalue\"[^>]*>\s*<div[^>]*>(.*?)</div>",
        html,
        re.S,
    )
    if m:
        intro = strip_html(m.group(1))
        if intro in ("本书尚无公告！", "暂无简介"):
            intro = ""

    return normalize_book(
        {
            "id": book_id,
            "title": title,
            "author": author,
            "category": category,
            "tags": ", ".join(tags),
            "score": score,
            "scorerCount": scorer,
            "words": words,
            "cover": cover,
            "intro": intro,
            "link": f"{YOUSUU_ORIGIN}/book/{book_id}",
        }
    )


def fetch_yousuu_book(url_or_id: str) -> dict:
    book_id = parse_book_id(url_or_id)
    if not book_id:
        raise ValueError("请填写优书网书籍链接或数字 ID，例如 https://www.yousuu.net/book/47686")
    html = http_get(f"{YOUSUU_ORIGIN}/book/{book_id}")
    book = parse_yousuu_book(html, book_id)
    if not book or not book.get("title"):
        raise ValueError("页面里没有解析到书名，可能是链接不对或站点改版了。")
    return book


def search_yousuu(keyword: str, limit: int = 12) -> List[dict]:
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    qs = urllib.parse.urlencode({"searchkey": keyword, "searchtype": "all"})
    html = http_get(f"{YOUSUU_ORIGIN}/modules/article/search.php?{qs}")
    seen = set()
    results = []
    for m in re.finditer(r'href="(/book/(\d+))"[^>]*>([^<]{1,80})</a>', html):
        book_id = m.group(2)
        title = unescape(m.group(3)).strip()
        if book_id in seen or not title or title in ("优书网", "书库", "书单"):
            continue
        seen.add(book_id)
        results.append(
            {
                "id": book_id,
                "title": title,
                "link": f"{YOUSUU_ORIGIN}/book/{book_id}",
            }
        )
        if len(results) >= limit:
            break
    return results


def fetch_user_id_list(text: str, delay: float = 1.6, log: Optional[Callable[[str], None]] = None) -> List[dict]:
    """Fetch only the IDs/URLs the user pasted. Not a site-wide crawl."""
    ids = []
    for token in re.split(r"[\s,，;；]+", text or ""):
        book_id = parse_book_id(token)
        if book_id and book_id not in ids:
            ids.append(book_id)
    books = []
    for i, book_id in enumerate(ids, 1):
        if log:
            log(f"[{i}/{len(ids)}] 读取 /book/{book_id}")
        try:
            books.append(fetch_yousuu_book(book_id))
        except Exception as exc:
            if log:
                log(f"  失败：{exc}")
        if i < len(ids) and delay > 0:
            time.sleep(delay)
    return books


def request_crawl_stop() -> None:
    CRAWL_STOP_PATH.write_text("stop", encoding="utf-8")


def clear_crawl_stop() -> None:
    if CRAWL_STOP_PATH.exists():
        CRAWL_STOP_PATH.unlink()


def crawl_stop_requested() -> bool:
    return CRAWL_STOP_PATH.exists()


def load_crawl_state() -> dict:
    if not CRAWL_STATE_PATH.exists():
        return {
            "done": [],
            "failed": {},
            "empty": [],
            "filled": 0,
            "startedAt": "",
            "updatedAt": "",
        }
    return json.loads(CRAWL_STATE_PATH.read_text(encoding="utf-8"))


def save_crawl_state(state: dict) -> None:
    state["updatedAt"] = datetime.now(timezone.utc).isoformat()
    CRAWL_STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def interruptible_sleep(seconds: float, should_stop: Optional[Callable[[], bool]] = None) -> bool:
    """Sleep in slices. Return True if stop was requested."""
    end = time.time() + max(0.0, seconds)
    while time.time() < end:
        if (should_stop and should_stop()) or crawl_stop_requested():
            return True
        time.sleep(min(0.25, max(0.0, end - time.time())))
    return False


def missing_intro_queue(state: Optional[dict] = None) -> List[dict]:
    skip = set()
    if state:
        skip.update(str(x) for x in state.get("done") or [])
        skip.update(str(x) for x in state.get("empty") or [])
    books = []
    for book in load_all_books():
        book_id = str(book.get("id") or "").strip()
        if not book_id.isdigit():
            continue
        if str(book.get("intro") or "").strip():
            continue
        if book_id in skip:
            continue
        books.append(book)
    return sort_books(books)


def build_id_path_index() -> Dict[str, Path]:
    index: Dict[str, Path] = {}
    for path in iter_part_files():
        for line in path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            book_id = str(rec.get("id") or "").strip()
            if book_id:
                index[book_id] = path
    return index


def patch_local_book(book_id: str, fetched: dict, index: Optional[Dict[str, Path]] = None) -> bool:
    """Replace one JSONL line in-place so a long crawl does not rewrite the whole library."""
    book_id = str(book_id)
    paths = [index[book_id]] if index and book_id in index else iter_part_files()
    needle_a = f'"id":"{book_id}"'
    needle_b = f'"id": "{book_id}"'
    for path in paths:
        text = path.read_text(encoding="utf-8")
        if needle_a not in text and needle_b not in text:
            continue
        lines = text.splitlines()
        found = False
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped.startswith("{") and (needle_a in stripped or needle_b in stripped):
                try:
                    rec = json.loads(stripped)
                except json.JSONDecodeError:
                    i += 1
                    continue
                if str(rec.get("id") or "") != book_id:
                    i += 1
                    continue
                found = True
                if fetched.get("intro"):
                    rec["intro"] = fetched["intro"]
                if fetched.get("score"):
                    rec["score"] = fetched["score"]
                if fetched.get("scorerCount"):
                    rec["scorerCount"] = fetched["scorerCount"]
                if fetched.get("words"):
                    rec["words"] = fetched["words"]
                if fetched.get("cover"):
                    rec["cover"] = fetched["cover"]
                if fetched.get("link"):
                    rec["link"] = fetched["link"]
                if fetched.get("author") and not rec.get("author"):
                    rec["author"] = fetched["author"]
                lines[i] = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
                if i + 1 < len(lines) and not lines[i + 1].lstrip().startswith("{"):
                    del lines[i + 1]
                break
            i += 1
        if found:
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
    return False


def crawl_missing_intros(
    delay: float = 2.2,
    should_stop: Optional[Callable[[], bool]] = None,
    log: Optional[Callable[[str], None]] = None,
    limit: int = 0,
) -> dict:
    """Fill empty intros for IDs already in the local catalog. Resumable."""

    def say(msg: str) -> None:
        if log:
            log(msg)

    clear_crawl_stop()
    state = load_crawl_state()
    if not state.get("startedAt"):
        state["startedAt"] = datetime.now(timezone.utc).isoformat()
    queue = missing_intro_queue(state)
    if limit and limit > 0:
        queue = queue[:limit]
    total = len(queue)
    say(f"待补全 {total} 本（已跳过有简介 / 已处理过的）。间隔 {delay} 秒，可随时停止后续跑。")
    if not total:
        say("没有需要补全的书。")
        return state

    index = build_id_path_index()

    filled = int(state.get("filled") or 0)
    consecutive_fail = 0
    done_set = set(str(x) for x in state.get("done") or [])
    empty_set = set(str(x) for x in state.get("empty") or [])
    failed_map = dict(state.get("failed") or {})

    for i, book in enumerate(queue, 1):
        if (should_stop and should_stop()) or crawl_stop_requested():
            say("收到停止指令，进度已保存。")
            break
        book_id = str(book["id"])
        title = book.get("title") or book_id
        say(f"[{i}/{total}] {title}  /book/{book_id}")
        try:
            fetched = fetch_yousuu_book(book_id)
            consecutive_fail = 0
            intro = (fetched.get("intro") or "").strip()
            if intro:
                patch_local_book(book_id, fetched, index=index)
                filled += 1
                done_set.add(book_id)
                say(f"  已写入简介（{len(intro)} 字）")
            else:
                empty_set.add(book_id)
                say("  页面没有简介，记下来不再重试")
        except FetchBlocked as exc:
            say(f"  {exc}")
            state["done"] = sorted(done_set)
            state["empty"] = sorted(empty_set)
            state["failed"] = failed_map
            state["filled"] = filled
            save_crawl_state(state)
            raise
        except Exception as exc:
            consecutive_fail += 1
            failed_map[book_id] = str(exc)
            say(f"  失败：{exc}")
            if consecutive_fail == 8:
                say("连续失败较多，暂停 3 分钟后再试…")
                if interruptible_sleep(180, should_stop):
                    say("暂停期间收到停止指令。")
                    break
            if consecutive_fail >= 16:
                say("连续失败太多，先停。进度已保存，稍后可再开。")
                break

            state["done"] = sorted(done_set)
            state["empty"] = sorted(empty_set)
            state["failed"] = failed_map
            state["filled"] = filled
            state["current"] = {"i": i, "total": total, "id": book_id, "title": title}
            save_crawl_state(state)

        if i < total:
            if interruptible_sleep(delay, should_stop):
                say("间隔等待时收到停止指令，进度已保存。")
                break

    state["done"] = sorted(done_set)
    state["empty"] = sorted(empty_set)
    state["failed"] = failed_map
    state["filled"] = filled
    save_crawl_state(state)
    clear_crawl_stop()
    say(f"本轮结束：累计写入简介 {filled} 本，无简介 {len(empty_set)}，失败 {len(failed_map)}。")
    return state
