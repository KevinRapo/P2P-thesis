// Mermaid diagrams you can zoom, pan and open full screen.
//
// Material renders Mermaid inside a closed shadow DOM, which no zoom tool can
// reach, so the fences use the class "mermaid-diagram" (mkdocs.yml) and are
// rendered here instead: mermaid draws the SVG, svg-pan-zoom makes it movable.
//
// Controls: drag to pan, Ctrl + mouse wheel or the +/- buttons to zoom,
// double-click to zoom in, "fit" to reset, the corner button (or Esc to close)
// to fill the browser window. Press F11 as well for the whole screen.

(function () {
  "use strict";

  let counter = 0;

  function mermaidTheme() {
    const scheme = document.body.getAttribute("data-md-color-scheme");
    return scheme === "slate" ? "dark" : "default";
  }

  function button(label, title, onClick) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "diagram-button";
    b.textContent = label;
    b.title = title;
    b.addEventListener("click", onClick);
    return b;
  }

  // Box height for the current width: the diagram's own aspect ratio (read
  // once, before svg-pan-zoom takes over the viewBox), within 240px..80% of
  // the window height.
  function fitHeight(box, svg) {
    if (!box.ratio) {
      const vb = svg.viewBox.baseVal;
      box.ratio = vb && vb.width ? vb.height / vb.width : 0.5;
    }
    const natural = box.clientWidth * box.ratio;
    return Math.max(240, Math.min(natural, window.innerHeight * 0.8));
  }

  async function renderOne(box) {
    const stage = box.querySelector(".diagram-stage");
    const id = "diagram-" + ++counter;
    const { svg } = await window.mermaid.render(id, box.dataset.source);
    stage.innerHTML = svg;
    box.ratio = null; // a redraw (e.g. new colours) re-reads the size
    const el = stage.querySelector("svg");
    el.removeAttribute("style");
    el.setAttribute("width", "100%");
    el.setAttribute("height", fitHeight(box, el) + "px");

    if (box.panZoom) box.panZoom.destroy();
    const pz = window.svgPanZoom(el, {
      zoomEnabled: true,
      mouseWheelZoomEnabled: false, // page scrolling stays normal
      dblClickZoomEnabled: true,
      controlIconsEnabled: false,
      fit: true,
      center: true,
      minZoom: 0.2,
      maxZoom: 20,
      zoomScaleSensitivity: 0.3,
    });
    box.panZoom = pz;
  }

  function build(pre) {
    const box = document.createElement("div");
    box.className = "diagram-box";
    box.dataset.source = pre.textContent;

    const stage = document.createElement("div");
    stage.className = "diagram-stage";

    const tools = document.createElement("div");
    tools.className = "diagram-tools";
    tools.append(
      button("+", "Zoom in", () => box.panZoom && box.panZoom.zoomIn()),
      button("−", "Zoom out", () => box.panZoom && box.panZoom.zoomOut()),
      button("fit", "Fit to box", () => {
        if (!box.panZoom) return;
        box.panZoom.resize();
        box.panZoom.fit();
        box.panZoom.center();
      }),
      button("⛶", "Fill the window (Esc to close)", () => toggleExpanded(box))
    );

    // Ctrl + wheel zooms the diagram; a plain wheel scrolls the page.
    stage.addEventListener(
      "wheel",
      (e) => {
        if (!e.ctrlKey || !box.panZoom) return;
        e.preventDefault();
        if (e.deltaY < 0) box.panZoom.zoomIn();
        else box.panZoom.zoomOut();
      },
      { passive: false }
    );

    box.append(tools, stage);
    pre.replaceWith(box);
    return box;
  }

  async function renderAll() {
    if (!window.mermaid || !window.svgPanZoom) return;
    window.mermaid.initialize({
      startOnLoad: false,
      theme: mermaidTheme(),
      securityLevel: "loose",
      flowchart: { useMaxWidth: false },
    });
    document.querySelectorAll("pre.mermaid-diagram").forEach(build);
    for (const box of document.querySelectorAll(".diagram-box")) {
      try {
        await renderOne(box);
      } catch (err) {
        box.querySelector(".diagram-stage").textContent =
          "Diagram error: " + err.message;
      }
    }
  }

  // Re-fit every diagram to its box: after a window resize (any screen size)
  // and when entering or leaving full screen.
  function refitAll() {
    document.querySelectorAll(".diagram-box").forEach((box) => {
      const svg = box.querySelector("svg");
      if (!svg || !box.panZoom) return;
      const full = box.classList.contains("diagram-expanded");
      const tools = box.querySelector(".diagram-tools").offsetHeight;
      const height = full ? window.innerHeight - tools - 16 : fitHeight(box, svg);
      svg.setAttribute("height", height + "px");
      box.panZoom.resize();
      box.panZoom.fit();
      box.panZoom.center();
    });
  }

  // An overlay over the whole browser window (more reliable than the browser's
  // Fullscreen API, which reports the new size only after a delay).
  function toggleExpanded(box, force) {
    const on = force ?? !box.classList.contains("diagram-expanded");
    box.classList.toggle("diagram-expanded", on);
    document.documentElement.classList.toggle("diagram-overlay-open", on);
    requestAnimationFrame(refitAll);
  }

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    document
      .querySelectorAll(".diagram-box.diagram-expanded")
      .forEach((box) => toggleExpanded(box, false));
  });

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(refitAll, 150);
  });

  // Redraw in the new colours when light / dark mode is switched.
  new MutationObserver(() => renderAll()).observe(document.body, {
    attributes: true,
    attributeFilter: ["data-md-color-scheme"],
  });

  if (window.document$) window.document$.subscribe(renderAll);
  else document.addEventListener("DOMContentLoaded", renderAll);
})();
