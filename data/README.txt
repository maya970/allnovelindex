马克书库书目（txt，一行一本 JSON）

网站只读这些文件，没有数据库。
大类分成男频 / 女频两个文件夹，下面再按分类分片：
  data/books/male/<分类英文>/part-*.txt
  data/books/female/<分类英文>/part-*.txt

每个 part 大约最多 80 本，或约 180KB，方便 GitHub / 免费 Vercel 托管。

一行一本，UTF-8 JSON。简介写在 intro 字段里，换行写成 \n，方便引用和解析。
页面上再拆成两行显示：第一行书目信息，第二行简介并自动折行。

新增或改书请用仓库里的 tools/打开录入工具.bat，不要手改超大文件。
重建索引：python tools/rebuild.py
按男频/女频重分并重新分片：python tools/reclassify.py
