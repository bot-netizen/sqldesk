/*
 * The switch in the bar. The theme itself is applied by a line in <head>
 * before anything paints, so a reader who chose dark never sees a white
 * flash; this file only has to handle the pressing.
 */
(function () {
  var root = document.documentElement;
  var KEY = "sqldesk-theme";

  function label(dark) {
    return dark ? "Switch to light mode" : "Switch to dark mode";
  }

  function paint(dark) {
    document.querySelectorAll("[data-theme-toggle]").forEach(function (b) {
      b.setAttribute("aria-label", label(dark));
      b.setAttribute("title", label(dark));
    });
  }

  paint(root.dataset.theme === "dark");

  document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      var dark = root.dataset.theme !== "dark";
      if (dark) {
        root.dataset.theme = "dark";
      } else {
        delete root.dataset.theme;
      }
      try {
        dark ? localStorage.setItem(KEY, "dark") : localStorage.removeItem(KEY);
      } catch (e) {
        /* A reader with storage blocked still gets the switch, for this page. */
      }
      paint(dark);
    });
  });
})();
