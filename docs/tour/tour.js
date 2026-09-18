// The tour pages' own script, shared by index.html and every feature page.
// Lifted out of index.html in M18, and made to tolerate a page that has only
// some of the pieces: the feature pages have stops but no stepper.
//
// What it does, in order:
//   1. put a "read" box on every built stop, remembered in this browser
//   2. refresh the contents ticks, each part's count, and the stages done
//   3. colour the Mermaid diagrams from the artifactkit theme, and draw them
//
// It is loaded after the Mermaid script tag, so `window.mermaid` is already there.

(function () {
  // Keys start with "edgar-tour:" because every page on github.io shares one storage.
  var store = {
    get: function (k) { try { return localStorage.getItem("edgar-tour:" + k); } catch (e) { return null; } },
    set: function (k, v) {
      try { v === null ? localStorage.removeItem("edgar-tour:" + k) : localStorage.setItem("edgar-tour:" + k, v); } catch (e) {}
    }
  };

  // 1. A "read" box on every built stop; the contents list shows a tick and a count.
  //    A page with no <h2 class="part"> puts all its stops under one name, "page".
  var parts = {};
  var part = "page";
  document.querySelectorAll("h2.part, article.stop").forEach(function (el) {
    if (el.matches("h2.part")) { part = el.id; return; }
    if (!parts[part]) parts[part] = [];
    parts[part].push(el);
    if (el.classList.contains("planned")) return;
    var box = document.createElement("label");
    box.className = "done";
    box.innerHTML = '<input type="checkbox"> read';
    var input = box.querySelector("input");
    input.checked = store.get("read:" + el.id) === "1";
    input.addEventListener("change", function () {
      store.set("read:" + el.id, input.checked ? "1" : null);
      refresh();
    });
    el.appendChild(box);
  });

  // 2. Refresh the ticks in the contents, each part's count, and the stages done.
  function refresh() {
    Object.keys(parts).forEach(function (name) {
      var built = parts[name].filter(function (el) { return !el.classList.contains("planned"); });
      var read = built.filter(function (el) { return store.get("read:" + el.id) === "1"; });
      built.forEach(function (el) {
        var item = document.querySelector('.ak-toc a[href="#' + el.id + '"]');
        if (item) item.parentElement.classList.toggle("read", read.indexOf(el) >= 0);
      });
      var count = document.querySelector('[data-count="' + name + '"]');
      if (count) count.textContent = built.length ? read.length + " / " + built.length : "planned";
    });
    // A stage is done when every stop between its heading and the next one is read.
    document.querySelectorAll(".ak-stepper .ak-step").forEach(function (step, i) {
      var heading = document.getElementById("stage-" + (i + 1));
      if (!heading) return;
      var stops = [];
      for (var el = heading.nextElementSibling; el && !el.matches("h3, .part-head"); el = el.nextElementSibling) {
        if (el.matches("article.stop")) stops.push(el);
      }
      var done = stops.length && stops.every(function (el) { return store.get("read:" + el.id) === "1"; });
      step.classList.toggle("ak-done", Boolean(done));
    });
  }
  refresh();

  // 3. Colour the diagrams from the artifactkit theme, so they follow its tokens.
  if (!window.mermaid) return;
  // 3a. Read the theme's three base colours.
  var css = getComputedStyle(document.documentElement);
  var bg = css.getPropertyValue("--t-bg").trim();
  var ink = css.getPropertyValue("--t-ink").trim();
  var accent = css.getPropertyValue("--t-accent").trim();
  // 3b. Mix them the way the theme does: a share of one colour over another.
  function mix(top, share, ground) {
    var a = parseInt(top.slice(1), 16), b = parseInt(ground.slice(1), 16);
    var out = [16, 8, 0].map(function (shift) {
      var x = (a >> shift) & 255, y = (b >> shift) & 255;
      return Math.round(x * share + y * (1 - share)).toString(16).padStart(2, "0");
    });
    return "#" + out.join("");
  }
  // 3c. Draw.
  window.mermaid.initialize({
    startOnLoad: true,
    theme: "base",
    themeVariables: {
      darkMode: true,
      background: bg,
      fontFamily: css.getPropertyValue("--t-font").trim(),
      fontSize: "14px",
      primaryColor: mix(ink, 0.08, bg),
      primaryTextColor: ink,
      primaryBorderColor: mix(accent, 0.7, bg),
      secondaryColor: mix(accent, 0.18, bg),
      tertiaryColor: mix(ink, 0.04, bg),
      lineColor: mix(ink, 0.5, bg),
      textColor: ink,
      clusterBkg: mix(ink, 0.03, bg),
      clusterBorder: mix(ink, 0.24, bg),
      edgeLabelBackground: bg,
      nodeTextColor: ink
    },
    flowchart: { htmlLabels: true, nodeSpacing: 28, rankSpacing: 36, padding: 10 }
  });
})();
