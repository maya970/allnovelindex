# 本地书库工具

网站本身仍是静态站：GitHub + 免费 Vercel。书目用 **txt**（一行一本 JSON），先按男频 / 女频，再按分类放进不同文件夹，避免单文件过大。页面上每本书显示成两行（信息 + 简介）。

## 目录

- `data/manifest.json` — 分类索引，网站先读这个再按需加载
- `data/books/male/<分类英文>/part-001.txt` — 男频
- `data/books/female/<分类英文>/part-001.txt` — 女频（能确定是女频的书会进对应女频分类）
- 每个分片大约最多 80 本，或约 180KB
- `tools/打开录入工具.bat` — Windows 下双击打开本地工具
- `tools/rebuild.py` — 命令行从 sqlite 重建
- `tools/reclassify.py` — 按男频/女频重分并重新分片

## 第一次

1. 确认本机有 `yousuu.sqlite`（默认路径：`c:\谷歌插件\自动翻译\yousuu.sqlite`）
2. 双击 `打开录入工具.bat`，打开 **从 SQLite 重建**
3. 点「从数据库重建全部分卷」
4. 把 `data/` 整个文件夹提交到 GitHub

也可在仓库根目录执行：

```bat
python tools\rebuild.py --db "c:\谷歌插件\自动翻译\yousuu.sqlite"
```

## 以后加书

两种办法，都会直接写入对应分类文件夹，再上传改动过的 txt 和 `manifest.json` 即可。

### 一本本登录

打开工具 → **一本本登录** → 填书名、作者、评分、评分人数、简介 → 写入书库。

### 从优书网导入一本

打开 **优书网导入**：

- 粘贴 `https://www.yousuu.net/book/数字` 或纯数字 ID，点「读取这一本」
- 或搜书名，双击结果

读到的内容会填进表单（含简介），确认后再写入。这是你指定的那一本，不是整站爬取。

### 自动补全简介（推荐挂着跑）

sqlite 里没有简介。三万本没法手填，用自动补全：只请求书库里已有 ID、还缺简介的公开页，评分高的先补。

- 双击 `开始补全简介.bat`，会弹出**置顶采集窗口**：绿灯闪就是正在采，当前书名和日志都在窗口里
- 关掉窗口或点「停止并保存」都会保存进度
- 下次打开会从断点继续
- 默认每本间隔 2.2 秒，大约十几个小时跑完
- 进度在 `tools/crawl_state.json`，不要把它当成书目上传

```bat
python -u tools\crawl_intros.py
python -u tools\crawl_intros.py --limit 20
```

这不是翻分类页去整站扒库，只补你现在这份书目里空着的简介。

## txt 格式

一行一本，UTF-8 JSON。简介在 `intro` 字段里，换行写成 `\n`：

```text
{"id":"47686","title":"星辰之主","author":"减肥专家","category":"科幻","tags":"科幻","score":6.6,"scorerCount":2120,"words":5396000,"cover":"https://...","intro":"世纪之交……","link":"https://www.yousuu.net/book/47686"}
```

网站展示时再拆成两行：第一行书目信息，第二行简介并自动折行。

## 本地预览网站

不要直接双击 html。在仓库根目录：

```bat
python -m http.server 8080
```

浏览器打开 `http://127.0.0.1:8080/cn/index.html`。
