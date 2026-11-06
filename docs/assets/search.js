/*
 * Search, on every page of the site.
 *
 * The site is static, so there is nobody to ask: search.json -- every section
 * of the guide, every release and every post, built by docs/tools/search.py --
 * is fetched the first time somebody opens the box, and matched here. It is a
 * few hundred kilobytes, compressed on the way, and only paid for by somebody
 * who searches.
 *
 * Opened by the button in the bar, by "/" anywhere that is not a text field,
 * and by Cmd-K or Ctrl-K. Every term has to appear; a term in a heading counts
 * for more than one in a page title, which counts for more than one in the
 * body, because a section *about* a word beats one that mentions it.
 */
(function () {
  var script = document.currentScript;
  var root = script ? script.src.replace(/assets\/search\.js(\?.*)?$/, "") : "";
  var index = null;
  var loading = null;
  var dialog, input, list, status, chosen = -1, shown = [];

  function load() {
    if (index) return Promise.resolve(index);
    if (!loading) {
      loading = fetch(root + "assets/search.json")
        .then(function (r) {
          if (!r.ok) throw new Error(r.status);
          return r.json();
        })
        .then(function (records) {
          index = records.map(function (r) {
            return { r: r, page: r.p.toLowerCase(), head: r.h.toLowerCase(), body: r.t.toLowerCase() };
          });
          return index;
        })
        .catch(function (e) {
          loading = null;
          throw e;
        });
    }
    return loading;
  }

  function escape(s) {
    return s.replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* Split the raw text on the terms, longest first, and escape each piece.
     Marking the escaped text instead finds "a" inside the <mark> the term
     before it wrote, and "amp" inside every &amp;. */
  function mark(s, terms) {
    var alternatives = terms
      .slice()
      .sort(function (a, b) {
        return b.length - a.length;
      })
      .map(function (t) {
        return t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      });
    if (!alternatives.length) return escape(s);
    return s
      .split(new RegExp("(" + alternatives.join("|") + ")", "gi"))
      .map(function (part, i) {
        return i % 2 ? "<mark>" + escape(part) + "</mark>" : escape(part);
      })
      .join("");
  }

  /* The words around the first match, so a result says why it matched. */
  function snippet(entry, terms) {
    var at = -1;
    terms.forEach(function (t) {
      var i = entry.body.indexOf(t);
      if (i >= 0 && (at < 0 || i < at)) at = i;
    });
    var text = entry.r.t;
    if (at < 0) return text.slice(0, 150) + (text.length > 150 ? "…" : "");
    var from = Math.max(0, at - 60);
    var to = Math.min(text.length, at + 110);
    return (from ? "…" : "") + text.slice(from, to) + (to < text.length ? "…" : "");
  }

  function search(query) {
    var phrase = query.trim().toLowerCase();
    var terms = phrase.split(/\s+/).filter(Boolean);
    if (!terms.length) return [];
    var scored = [];
    index.forEach(function (e) {
      var score = 0;
      for (var i = 0; i < terms.length; i++) {
        var t = terms[i];
        var inHead = e.head.indexOf(t) >= 0;
        var inPage = e.page.indexOf(t) >= 0;
        var inBody = e.body.indexOf(t) >= 0;
        if (!inHead && !inPage && !inBody) return;
        score += (inHead ? 8 : 0) + (inPage ? 4 : 0) + (inBody ? 1 : 0);
      }
      if (terms.length > 1 && (e.head + " " + e.body).indexOf(phrase) >= 0) score += 6;
      if (!e.head) score -= 1;
      scored.push({ e: e, score: score });
    });
    scored.sort(function (a, b) {
      return b.score - a.score;
    });
    return scored.slice(0, 12).map(function (s) {
      return s.e;
    });
  }

  function choose(n) {
    var items = list.querySelectorAll("[role=option]");
    if (!items.length) return;
    chosen = (n + items.length) % items.length;
    items.forEach(function (item, i) {
      item.setAttribute("aria-selected", i === chosen ? "true" : "false");
    });
    items[chosen].scrollIntoView({ block: "nearest" });
    input.setAttribute("aria-activedescendant", items[chosen].id);
  }

  function render() {
    var query = input.value;
    if (!index) return;
    var terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    shown = search(query);
    chosen = -1;
    input.removeAttribute("aria-activedescendant");
    if (!terms.length) {
      list.innerHTML = "";
      status.textContent = "Search the guide, the releases and the blog.";
      return;
    }
    if (!shown.length) {
      list.innerHTML = "";
      status.textContent = "Nothing matches “" + query.trim() + "”.";
      return;
    }
    status.textContent = shown.length + (shown.length === 1 ? " result" : " results");
    list.innerHTML = shown
      .map(function (e, i) {
        var where = e.r.h ? escape(e.r.p) + " › " + mark(e.r.h, terms) : mark(e.r.p, terms);
        return (
          '<li><a id="search-result-' + i + '" role="option" aria-selected="false" href="' + root + escape(e.r.u) + '">' +
          '<span class="search-where">' + where + "</span>" +
          '<span class="search-snippet">' + mark(snippet(e, terms), terms) + "</span></a></li>"
        );
      })
      .join("");
    choose(0);
  }

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "search-dialog";
    dialog.setAttribute("aria-label", "Search the docs");
    dialog.innerHTML =
      '<div class="search-box">' +
      '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><circle cx="7" cy="7" r="4.6"/><path d="m10.4 10.4 3.4 3.4"/></svg>' +
      '<input type="search" placeholder="Search the docs" autocomplete="off" spellcheck="false" ' +
      'role="combobox" aria-expanded="true" aria-controls="search-results" aria-autocomplete="list">' +
      '<button type="button" class="search-close" aria-label="Close search">Esc</button></div>' +
      '<p class="search-status" role="status"></p>' +
      '<ul class="search-results" id="search-results" role="listbox"></ul>' +
      '<p class="search-help"><kbd>↑</kbd><kbd>↓</kbd> to move &middot; <kbd>Enter</kbd> to open &middot; <kbd>Esc</kbd> to close</p>';
    document.body.appendChild(dialog);
    input = dialog.querySelector("input");
    list = dialog.querySelector(".search-results");
    status = dialog.querySelector(".search-status");

    input.addEventListener("input", render);
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        choose(chosen + 1);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        choose(chosen - 1);
      } else if (e.key === "Enter" && chosen >= 0) {
        e.preventDefault();
        var link = list.querySelectorAll("[role=option]")[chosen];
        if (link) link.click();
      }
    });
    dialog.querySelector(".search-close").addEventListener("click", function () {
      dialog.close();
    });
    /* A click on the backdrop is a click on the dialog itself. */
    dialog.addEventListener("click", function (e) {
      if (e.target === dialog) dialog.close();
    });
    /* Following a result to a section on this same page has to close the box. */
    list.addEventListener("click", function () {
      dialog.close();
    });
  }

  function open() {
    if (!dialog) build();
    if (!dialog.open) dialog.showModal();
    input.focus();
    input.select();
    if (index) {
      render();
      return;
    }
    status.textContent = "Loading the index…";
    load().then(render, function () {
      status.textContent = "Search is built when the site is published, and this copy has no index.";
    });
  }

  document.querySelectorAll("[data-search-open]").forEach(function (button) {
    button.addEventListener("click", open);
  });

  var mac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
  document.querySelectorAll("[data-search-key]").forEach(function (k) {
    k.textContent = mac ? "⌘K" : "Ctrl K";
  });

  document.addEventListener("keydown", function (e) {
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target && e.target.tagName) || "") || (e.target && e.target.isContentEditable);
    if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      open();
    } else if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      open();
    }
  });

  /* On a guide page, the section being read is marked in the list on the right. */
  var toc = document.querySelector(".doc-toc");
  if (toc && "IntersectionObserver" in window) {
    var links = {};
    toc.querySelectorAll("a[href^='#']").forEach(function (a) {
      links[decodeURIComponent(a.getAttribute("href").slice(1))] = a;
    });
    var current = null;
    var seen = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          if (current) current.removeAttribute("aria-current");
          current = links[entry.target.id];
          if (current) current.setAttribute("aria-current", "location");
        });
      },
      { rootMargin: "0px 0px -70% 0px" }
    );
    Object.keys(links).forEach(function (id) {
      var heading = document.getElementById(id);
      if (heading) seen.observe(heading);
    });
  }
})();
