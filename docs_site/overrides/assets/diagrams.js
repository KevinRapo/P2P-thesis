// Mermaid diagrams you can zoom, pan and open full screen.
//
// Material renders Mermaid inside a closed shadow DOM, which no zoom tool can
// reach, so the fences use the class "mermaid-diagram" (mkdocs.yml) and are
// rendered here instead: mermaid draws the SVG, svg-pan-zoom makes it movable.
//
// Controls: drag to pan, Ctrl + mouse wheel or the +/- buttons to zoom,
// double-click to zoom in, "fit" to reset, the corner button for full screen.

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

  function fitHeight(box, svg) {
    const vb = svg.viewBox.baseVal;
    if (!vb || !vb.width) return 400;
    const natural = (box.clientWidth * vb.height) / vb.width;
    return Math.max(240, Math.min(natural, window.innerHeight * 0.8));
  }

  async function renderOne(box) {
    const stage = box.querySelector(".diagram-stage");
    const id = "diagram-" + ++counter;
    const { svg } = await window.mermaid.render(id, box.dataset.source);
    stage.innerHTML = svg;
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
      button("⛶", "Full screen", () => {
        if (document.fullscreenElement) document.exitFullscreen();
        else box.requestFullscreen();
      })
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

  document.addEventListener("fullscreenchange", () => {
    document.querySelectorAll(".diagram-box").forEach((box) => {
      const svg = box.querySelector("svg");
      if (!svg || !box.panZoom) return;
      const full = document.fullscreenElement === box;
      svg.setAttribute("height", full ? "100%" : fitHeight(box, svg) + "px");
      box.panZoom.resize();
      box.panZoom.fit();
      box.panZoom.center();
    });
  });

  // Redraw in the new colours when light / dark mode is switched.
  new MutationObserver(() => renderAll()).observe(document.body, {
    attributes: true,
    attributeFilter: ["data-md-color-scheme"],
  });

  if (window.document$) window.document$.subscribe(renderAll);
  else document.addEventListener("DOMContentLoaded", renderAll);
})();
