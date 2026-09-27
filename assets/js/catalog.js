/* Full-genre catalog: load split txt folders, render cards. */
(function (global) {
  "use strict";

  var state = {
    manifest: null,
    all: [],
    filtered: [],
    loadedCats: {},
    page: 1,
    perPage: 24,
    currentCat: ""
  };

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function qsa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function num(v) {
    var n = typeof v === "number" ? v : parseFloat(v);
    return isNaN(n) ? 0 : n;
  }

  function isFileProtocol() {
    return location.protocol === "file:";
  }

  function candidateUrls(path) {
    var clean = String(path || "").replace(/^\//, "");
    if (/^https?:/i.test(clean)) return [clean];
    var urls = ["../" + clean, "/" + clean];
    try {
      urls.push(new URL(clean, location.origin + "/").href);
    } catch (e) {}
    return urls;
  }

  function failHint() {
    if (isFileProtocol()) {
      return "请用浏览器打开网站地址，不要直接打开本地文件。";
    }
    return "书目暂时打不开，请稍后再试。";
  }

  function setStatus(text) {
    var el = qs("#catalogStatus") || qs(".dl-count");
    if (el) el.textContent = text;
  }

  function parseTxt(text) {
    var lines = String(text || "").split(/\r?\n/);
    var out = [];
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].replace(/^\uFEFF/, "");
      var stripped = line.trim();
      if (!stripped || stripped.charAt(0) === "#") continue;
      if (stripped.charAt(0) !== "{") continue;
      try {
        var rec = JSON.parse(stripped);
        if (!rec || !rec.title) continue;
        if (rec.intro == null) rec.intro = "";
        if (i + 1 < lines.length) {
          var nxt = lines[i + 1];
          var ns = nxt.trim();
          if (ns && ns.charAt(0) !== "{") {
            rec.intro = nxt;
            i += 1;
          }
        }
        out.push(rec);
      } catch (err) {}
    }
    return out;
  }

  function fetchFirst(urls, asJson) {
    function tryAt(i) {
      if (i >= urls.length) return Promise.reject(new Error("fetch"));
      return fetch(urls[i])
        .then(function (res) {
          if (!res.ok) throw new Error(String(res.status));
          return asJson ? res.json() : res.text();
        })
        .catch(function () {
          return tryAt(i + 1);
        });
    }
    return tryAt(0);
  }

  function loadFile(path) {
    return fetchFirst(candidateUrls(path), false);
  }

  function loadManifest() {
    if (state.manifest) return Promise.resolve(state.manifest);
    if (isFileProtocol()) return Promise.reject(new Error("file-protocol"));
    return fetchFirst(candidateUrls("data/manifest.json"), true).then(function (man) {
      state.manifest = man;
      return man;
    });
  }

  function filesFor(catId) {
    var cats = (state.manifest && state.manifest.categories) || [];
    var files = [];
    if (!catId) return files;
    for (var i = 0; i < cats.length; i++) {
      if (cats[i].id === catId) {
        files = files.concat(cats[i].files || []);
      }
    }
    return files;
  }

  function uniqueBooks(list) {
    var seen = {};
    var out = [];
    for (var i = 0; i < list.length; i++) {
      var b = list[i];
      var key = b.id ? "id:" + b.id : "t:" + String(b.title) + "|" + String(b.author || "");
      if (seen[key]) continue;
      seen[key] = 1;
      out.push(b);
    }
    return out;
  }

  function loadCategories(catId) {
    var key = catId || "*";
    if (state.loadedCats[key]) {
      state.all = state.loadedCats[key];
      return Promise.resolve(state.all);
    }
    var files = filesFor(catId);
    if (!files.length) {
      state.all = [];
      return Promise.resolve(state.all);
    }
    setStatus("正在载入书目…");
    var done = 0;
    return Promise.all(
      files.map(function (file) {
        return loadFile(file)
          .then(function (text) {
            done += 1;
            if (done === 1 || done === files.length || done % 8 === 0) {
              setStatus("正在载入书目… " + done + " / " + files.length);
            }
            return parseTxt(text);
          })
          .catch(function (err) {
            console.error(err);
            return [];
          });
      })
    ).then(function (chunks) {
      var all = [];
      for (var i = 0; i < chunks.length; i++) all = all.concat(chunks[i]);
      all = uniqueBooks(all);
      state.loadedCats[key] = all;
      state.all = all;
      return all;
    });
  }

  function fillCategorySelect() {
    var sel = qs("#categoryFilter");
    if (!sel || !state.manifest) return;
    var current = sel.value;
    var html = '<option value="">选择分类</option>';
    var groups = { 男频: [], 女频: [] };
    var cats = state.manifest.categories || [];
    for (var i = 0; i < cats.length; i++) {
      var g = cats[i].group || "男频";
      if (!groups[g]) groups[g] = [];
      groups[g].push(cats[i]);
    }
    ["男频", "女频"].forEach(function (g) {
      if (!groups[g].length) return;
      html += '<optgroup label="' + escapeHtml(g) + '">';
      groups[g].forEach(function (c) {
        html +=
          '<option value="' +
          escapeHtml(c.id) +
          '">' +
          escapeHtml(c.name) +
          "（" +
          c.count +
          "）</option>";
      });
      html += "</optgroup>";
    });
    sel.innerHTML = html;
    if (current) sel.value = current;
    else if (state.currentCat) sel.value = state.currentCat;
  }

  function groupCount(man, group) {
    var n = 0;
    var cats = (man && man.categories) || [];
    for (var i = 0; i < cats.length; i++) {
      if (cats[i].group === group) n += cats[i].count || 0;
    }
    return n;
  }

  function categoryCardsHtml(items, heading) {
    if (!items || !items.length) return "";
    var html = heading ? '<h3 class="dl-cat-head">' + escapeHtml(heading) + "</h3>" : "";
    html += '<div class="dl-cat-grid">';
    items.forEach(function (c) {
      var max = 2800;
      var pct = Math.max(8, Math.min(100, Math.round((c.count / max) * 100)));
      html +=
        '<a class="dl-portal dl-cat-card" href="catalog.html?cat=' +
        encodeURIComponent(c.id) +
        '"><span class="dl-kicker">' +
        escapeHtml(c.group) +
        '</span><h2>' +
        escapeHtml(c.name) +
        '</h2><p>' +
        c.count +
        ' 本</p><span class="dl-bar"><i style="width:' +
        pct +
        '%"></i></span></a>';
    });
    html += "</div>";
    return html;
  }

  function renderHome() {
    var grid = qs("#catGrid");
    var gates = qs("#channelGates");
    if (!grid && !gates) return;
    loadManifest()
      .then(function (man) {
        var male = groupCount(man, "男频");
        var female = groupCount(man, "女频");
        var note = qs("#homeCount");
        if (note) note.textContent = "共 " + (man.count || 0).toLocaleString("zh-CN") + " 本";
        var maleNote = qs("#maleCount");
        var femaleNote = qs("#femaleCount");
        if (maleNote) maleNote.textContent = male.toLocaleString("zh-CN") + " 本";
        if (femaleNote) femaleNote.textContent = female.toLocaleString("zh-CN") + " 本";
        if (gates) {
          gates.innerHTML =
            '<a class="dl-gate dl-gate-male" href="catalog.html?group=' +
            encodeURIComponent("男频") +
            '"><span class="dl-kicker">CHANNEL · MALE</span><h2>男频</h2><p class="dl-gate-count">' +
            male.toLocaleString("zh-CN") +
            ' 本</p><p>玄幻、仙侠、科幻、都市、历史。</p></a>' +
            '<a class="dl-gate dl-gate-female" href="catalog.html?group=' +
            encodeURIComponent("女频") +
            '"><span class="dl-kicker">CHANNEL · FEMALE</span><h2>女频</h2><p class="dl-gate-count">' +
            female.toLocaleString("zh-CN") +
            ' 本</p><p>穿越、言情、耽美、衍生同人。</p></a>';
        }
        if (grid) {
          var html = "";
          [
            { key: "男频", label: "男频分类" },
            { key: "女频", label: "女频分类" }
          ].forEach(function (g) {
            var items = (man.categories || []).filter(function (c) {
              return c.group === g.key;
            });
            html += categoryCardsHtml(items, g.label);
          });
          grid.innerHTML = html;
        }
      })
      .catch(function () {
        var msg = '<p class="dl-sub">' + failHint() + "</p>";
        if (gates) gates.innerHTML = msg;
        if (grid) grid.innerHTML = gates ? "" : msg;
      });
  }

  function applyFilter() {
    var nameEl = qs("#nameFilter");
    var catEl = qs("#categoryFilter");
    var rateEl = qs("#ratingFilter");
    var q = ((nameEl && nameEl.value) || "").trim().toLowerCase();
    var cat = (catEl && catEl.value) || "";
    var rate = (rateEl && rateEl.value) || "";
    var rateParts = rate ? rate.split("-").map(Number) : null;

    state.filtered = state.all.filter(function (b) {
      if (cat) {
        var slug = slugOf(b.category);
        if (slug !== cat && b.category !== cat) return false;
      }
      if (q) {
        var hay = (b.title + " " + (b.author || "") + " " + (b.tags || "")).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      if (rateParts) {
        var s = num(b.score);
        if (s < rateParts[0]) return false;
        if (rateParts[1] >= 10) {
          if (s > 10) return false;
        } else if (s >= rateParts[1]) return false;
      }
      return true;
    });
    state.filtered.sort(function (a, b) {
      var ds = num(b.score) - num(a.score);
      if (ds) return ds;
      return num(b.scorerCount) - num(a.scorerCount);
    });
    state.page = 1;
    renderPage();
  }

  function slugOf(name) {
    var cats = (state.manifest && state.manifest.categories) || [];
    for (var i = 0; i < cats.length; i++) {
      if (cats[i].name === name) return cats[i].id;
    }
    return "";
  }

  function renderPage() {
    var box = qs("#bookCards");
    if (!box) return;
    var list = state.filtered;
    var pages = list.length ? Math.ceil(list.length / state.perPage) : 0;
    if (pages && state.page > pages) state.page = pages;
    if (state.page < 1) state.page = 1;
    var start = (state.page - 1) * state.perPage;
    var slice = list.slice(start, start + state.perPage);
    if (!slice.length) {
      box.innerHTML = '<p class="dl-empty">没有匹配的书。</p>';
    } else {
      var html = "";
      for (var i = 0; i < slice.length; i++) {
        html += cardHtml(slice[i]);
      }
      box.innerHTML = html;
    }
    var prev = qs("#prevPage");
    var next = qs("#nextPage");
    if (prev) prev.disabled = state.page <= 1 || pages === 0;
    if (next) next.disabled = pages === 0 || state.page >= pages;
    var pager = qs("#pageInfo");
    if (pager) pager.textContent = pages ? "第 " + state.page + " / " + pages + " 页" : "";
    if (list.length) {
      setStatus("共 " + list.length + " 本 · 第 " + state.page + " / " + pages + " 页");
    } else {
      setStatus("没有匹配的书");
    }
  }

  function cardHtml(b) {
    var intro = String(b.intro || "").trim();
    var introBlock = intro
      ? '<p class="dl-intro">' + escapeHtml(intro) + "</p>"
      : '<p class="dl-intro is-empty">暂无简介</p>';
    var words = num(b.words) ? Math.round(num(b.words) / 10000) + " 万字" : "";
    var bits = [
      escapeHtml(b.title || ""),
      escapeHtml(b.author || "佚名"),
      escapeHtml(b.category || ""),
      num(b.score) ? escapeHtml(String(b.score)) + " 分" : "",
      num(b.scorerCount) ? escapeHtml(String(b.scorerCount)) + " 人评" : "",
      words ? escapeHtml(words) : ""
    ].filter(Boolean);
    return (
      '<article class="dl-card">' +
      '<p class="dl-book-line">' +
      bits.join(" · ") +
      "</p>" +
      introBlock +
      "</article>"
    );
  }

  function queryCat() {
    try {
      return new URLSearchParams(location.search).get("cat") || "";
    } catch (e) {
      return "";
    }
  }

  function queryGroup() {
    try {
      return new URLSearchParams(location.search).get("group") || "";
    } catch (e) {
      return "";
    }
  }

  function setPickerVisible(show, group) {
    var picker = qs("#catalogPicker");
    var books = qs("#bookCards");
    var pager = qs(".dl-pager");
    if (picker) {
      picker.hidden = !show;
      if (show && state.manifest) {
        var cats = state.manifest.categories || [];
        var items = group ? cats.filter(function (c) { return c.group === group; }) : cats;
        var male = items.filter(function (c) { return c.group === "男频"; });
        var female = items.filter(function (c) { return c.group === "女频"; });
        var html = "";
        if (!group) {
          html += categoryCardsHtml(male, "男频");
          html += categoryCardsHtml(female, "女频");
        } else {
          html += categoryCardsHtml(items, group);
        }
        picker.innerHTML = html;
      }
    }
    if (books) books.hidden = !!show;
    if (pager) pager.hidden = !!show;
  }

  function switchCategory(catId) {
    state.currentCat = catId || "";
    var heading = qs("#catalogHeading");
    var man = state.manifest;
    var group = queryGroup();
    var name = group || "全部书库";
    if (catId && man) {
      for (var i = 0; i < man.categories.length; i++) {
        if (man.categories[i].id === catId) name = man.categories[i].name;
      }
    }
    if (heading) heading.textContent = name;
    if (!catId) {
      state.all = [];
      state.filtered = [];
      setPickerVisible(true, group);
      setStatus("请先选择一个分类。");
      var box = qs("#bookCards");
      if (box) box.innerHTML = "";
      return Promise.resolve();
    }
    setPickerVisible(false);
    return loadCategories(catId).then(function () {
      applyFilter();
    });
  }

  function bind() {
    var name = qs("#nameFilter");
    var cat = qs("#categoryFilter");
    var rate = qs("#ratingFilter");
    var timer = 0;
    if (name) {
      name.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(applyFilter, 120);
      });
    }
    if (cat) {
      cat.addEventListener("change", function () {
        var id = cat.value;
        var group = queryGroup();
        var url = "catalog.html";
        if (id) url += "?cat=" + encodeURIComponent(id);
        else if (group) url += "?group=" + encodeURIComponent(group);
        try {
          history.replaceState(null, "", url);
        } catch (e) {}
        switchCategory(id);
      });
    }
    if (rate) rate.addEventListener("change", applyFilter);
    var prev = qs("#prevPage");
    var next = qs("#nextPage");
    if (prev)
      prev.addEventListener("click", function () {
        state.page -= 1;
        renderPage();
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    if (next)
      next.addEventListener("click", function () {
        state.page += 1;
        renderPage();
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
  }

  function startCatalog() {
    bind();
    var cat = queryCat();
    state.currentCat = cat;
    loadManifest()
      .then(function () {
        fillCategorySelect();
        return switchCategory(cat);
      })
      .catch(function () {
        setStatus(failHint());
      });
  }

  global.Catalog = {
    start: startCatalog,
    renderHome: renderHome,
    filter: applyFilter
  };

  if (qs("#catGrid")) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", renderHome);
    } else {
      renderHome();
    }
  }
  if (qs("#bookCards")) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", startCatalog);
    } else {
      startCatalog();
    }
  }
})(window);
