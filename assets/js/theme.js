/* 马克书库 — static front-end glue. No backend, no build. */
(function () {
  "use strict";

  var page = (location.pathname.split("/").pop() || "index.html").toLowerCase();
  if (!page || page.indexOf(".") === -1) page = "index.html";

  var GLOBAL_NAV = [
    { href: "index.html", title: "首页" },
    { href: "catalog.html?group=男频", title: "男频" },
    { href: "catalog.html?group=女频", title: "女频" },
    { href: "catalog.html", title: "全部书库" },
    { href: "picture.html", title: "公众号" },
    { href: "about.html", title: "关于本站" }
  ];

  var PAGE_TITLES = {
    "index.html": "首页",
    "catalog.html": "全部书库",
    "picture.html": "公众号",
    "about.html": "关于本站"
  };

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function qsa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function el(tag, cls, html) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (html) node.innerHTML = html;
    return node;
  }

  function brandLogo() {
    qsa(".logo a, .navbar-brand .logo").forEach(function (a) {
      a.innerHTML =
        '<span class="dl-mark">库</span><span class="dl-brand">马克书库<small>ALL GENRES</small></span>';
      a.setAttribute("href", "index.html");
      a.classList.add("dl-branded");
    });
    qsa('[data-toggle="mobile-menu"]').forEach(function (a) {
      a.innerHTML = '<span class="dl-burger" aria-hidden="true"></span>';
      a.setAttribute("aria-label", "打开菜单");
    });
  }

  function unifyNav() {
    var menu = qs("#main-menu");
    if (!menu) return;

    var hashLinks = qsa("a.smooth", menu)
      .map(function (a) {
        var titleNode = qs(".title", a) || a;
        return {
          href: a.getAttribute("href"),
          title: (titleNode.textContent || "").replace(/\s+/g, " ").trim()
        };
      })
      .filter(function (item) {
        if (!item.href || item.href.charAt(0) !== "#" || !item.title) return false;
        try {
          return !!qs(item.href);
        } catch (err) {
          return false;
        }
      });

    var search = location.search || "";
    var html = "";
    GLOBAL_NAV.forEach(function (item) {
      var active = "";
      var hrefPage = item.href.split("?")[0];
      var hrefQuery = item.href.indexOf("?") >= 0 ? "?" + item.href.split("?")[1] : "";
      if (hrefPage === page) {
        if (hrefQuery) {
          if (search === hrefQuery) active = " class=\"active\"";
        } else if (item.href === "catalog.html") {
          if (search.indexOf("group=") === -1) active = " class=\"active\"";
        } else if (!search) {
          active = " class=\"active\"";
        }
      }
      html +=
        "<li" +
        active +
        '><a href="' +
        item.href +
        '"><span class="dl-dot"></span><span class="title">' +
        item.title +
        "</span></a></li>";
    });

    if (hashLinks.length) {
      html += '<li class="dl-nav-label">本页目录</li>';
      hashLinks.forEach(function (item) {
        html +=
          '<li><a href="' +
          item.href +
          '" class="smooth"><span class="dl-dot"></span><span class="title">' +
          item.title +
          "</span></a></li>";
      });
    }

    menu.innerHTML = html;
  }

  function crumbTitle() {
    try {
      var q = new URLSearchParams(location.search || "");
      var group = q.get("group");
      if (group) return group;
    } catch (e) {}
    return PAGE_TITLES[page] || "书单";
  }

  function crumb() {
    var content = qs(".main-content");
    if (!content || qs(".dl-crumb")) return;
    var nav = qs(".navbar.user-info-navbar", content);
    var bar = el(
      "div",
      "dl-crumb",
      "<span>马克书库 / <b>" +
        crumbTitle() +
        "</b></span><span>全品类目录</span>"
    );
    if (nav && nav.parentNode) {
      nav.parentNode.insertBefore(bar, nav.nextSibling);
    } else {
      content.insertBefore(bar, content.firstChild);
    }
  }

  function setMenu(open) {
    var menu = qs("#main-menu");
    if (!menu) return;
    menu.classList.toggle("mobile-is-visible", open);
    document.body.classList.toggle("dl-nav-open", open);
  }

  function mobileChrome() {
    if (qs(".dl-backdrop")) return;
    var backdrop = el("div", "dl-backdrop");
    document.body.appendChild(backdrop);

    document.addEventListener("click", function (e) {
      var toggle = e.target.closest && e.target.closest('[data-toggle="mobile-menu"]');
      if (toggle) {
        e.preventDefault();
        setMenu(!document.body.classList.contains("dl-nav-open"));
        return;
      }
      if (e.target === backdrop) {
        setMenu(false);
        return;
      }
      var link = e.target.closest && e.target.closest("#main-menu a");
      if (link && window.innerWidth <= 768) setMenu(false);
    });

    window.addEventListener("resize", function () {
      if (window.innerWidth > 768) setMenu(false);
    });
  }

  function chromeClicks() {
    document.addEventListener("click", function (e) {
      var top = e.target.closest && e.target.closest("[rel=go-top]");
      if (top) {
        e.preventDefault();
        window.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }
      var smooth = e.target.closest && e.target.closest("a.smooth");
      if (!smooth) return;
      var id = smooth.getAttribute("href");
      if (!id || id.charAt(0) !== "#") return;
      var target = qs(id);
      if (!target) return;
      e.preventDefault();
      setMenu(false);
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function analytics() {
    window.addEventListener("load", function () {
      setTimeout(function () {
        var hm = document.createElement("script");
        hm.src = "https://hm.baidu.com/hm.js?c05bb16ea908292af9f6c513087a1cc3";
        hm.async = true;
        document.head.appendChild(hm);
      }, 1800);
    });
  }

  function boot() {
    document.body.classList.add("dl-site");
    brandLogo();
    unifyNav();
    crumb();
    mobileChrome();
    chromeClicks();
    analytics();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
