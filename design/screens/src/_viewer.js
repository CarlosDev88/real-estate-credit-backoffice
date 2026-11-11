// Visor de documentos de referencia. En la app real el archivo llega por una URL prefirmada
// (GET .../download) y el PDF se dibuja con un visor como PDF.js; aquí se simulan las páginas.
(function () {
  var el = document.getElementById("viewer");
  if (!el) return;
  var stage = document.getElementById("viewerStage");
  var state = { zoom: 1, rot: 0, page: 1, pages: 1, kind: "pdf", url: null }, last = null;
  var BASE = 640;

  function fakePage(n, total) {
    var lines = "";
    for (var i = 0; i < 9; i++) lines += '<i style="width:' + (60 + ((i * 37 + n * 13) % 40)) + '%"></i>';
    return '<div class="vpage" data-page="' + n + '"><div class="vh"></div><div class="vrow"><div style="display:grid;gap:8px"><i></i><i style="width:70%"></i></div><div style="display:grid;gap:8px"><i></i><i style="width:55%"></i></div></div><div class="vbox"></div>' + lines + '<div class="vfoot"><span>Documento de ejemplo</span><span>Página ' + n + " de " + total + "</span></div></div>";
  }
  function render() {
    var w = Math.round(Math.min(BASE, window.innerWidth - 32) * state.zoom);
    var t = "rotate(" + state.rot + "deg)";
    if (state.url && state.kind === "pdf") {
      stage.innerHTML = '<object class="viewer-real" data="' + state.url + '" type="application/pdf" aria-label="Vista del PDF"><p style="color:#fff">Tu navegador no puede mostrar el PDF aquí. Usa descargar.</p></object>';
    } else if (state.url) {
      stage.innerHTML = '<img class="viewer-real-img" alt="Vista del documento" src="' + state.url + '" style="width:' + w + "px;transform:" + t + '">';
    } else if (state.kind === "image") {
      stage.innerHTML = '<div class="vphoto" style="width:' + w + "px;transform:" + t + '">' + fakePage(1, 1).replace('class="vpage"', 'class="vpage" style="width:54%"') + "</div>";
    } else {
      var html = "";
      for (var p = 1; p <= state.pages; p++) html += fakePage(p, state.pages).replace('class="vpage"', 'class="vpage" style="width:' + w + "px;transform:" + t + '"');
      stage.innerHTML = html;
    }
    document.getElementById("viewerZoom").textContent = Math.round(state.zoom * 100) + " %";
    document.getElementById("viewerPage").textContent = state.page + " / " + state.pages;
    el.querySelector("[data-vprev]").disabled = state.page <= 1;
    el.querySelector("[data-vnext]").disabled = state.page >= state.pages;
  }
  function goTo(n) {
    state.page = Math.max(1, Math.min(state.pages, n));
    var pg = stage.querySelector('[data-page="' + state.page + '"]');
    if (pg) pg.scrollIntoView({ block: "start", behavior: "smooth" });
    document.getElementById("viewerPage").textContent = state.page + " / " + state.pages;
    el.querySelector("[data-vprev]").disabled = state.page <= 1;
    el.querySelector("[data-vnext]").disabled = state.page >= state.pages;
  }
  window.UmViewer = {
    open: function (o, from) {
      state = { zoom: 1, rot: 0, page: 1, pages: o.pages || 1, kind: o.kind || "pdf", url: o.url || null };
      document.getElementById("viewerName").textContent = o.name;
      document.getElementById("viewerMeta").textContent = (state.kind === "image" ? "Imagen" : "PDF · " + state.pages + (state.pages === 1 ? " página" : " páginas")) + (o.size ? " · " + o.size : "");
      var dl = el.querySelector("[data-vdownload]");
      if (o.url) { dl.href = o.url; dl.setAttribute("download", o.name); } else { dl.href = "#"; dl.removeAttribute("download"); }
      document.getElementById("viewerNote").textContent = o.url ? "Vista local del archivo que elegiste. Todavía no se ha enviado." : "Descarga con enlace firmado que vence en 5 minutos.";
      last = from || document.activeElement;
      el.classList.add("open"); el.setAttribute("aria-hidden", "false"); document.body.style.overflow = "hidden";
      render(); stage.scrollTop = 0; el.querySelector("[data-vclose]").focus();
    },
    close: function () { el.classList.remove("open"); el.setAttribute("aria-hidden", "true"); document.body.style.overflow = ""; if (last) last.focus(); }
  };
  el.querySelector("[data-vclose]").addEventListener("click", window.UmViewer.close);
  el.querySelector("[data-vprev]").addEventListener("click", function () { goTo(state.page - 1); });
  el.querySelector("[data-vnext]").addEventListener("click", function () { goTo(state.page + 1); });
  el.querySelectorAll("[data-vzoom]").forEach(function (b) { b.addEventListener("click", function () { state.zoom = Math.max(0.5, Math.min(2.5, state.zoom + 0.25 * +b.dataset.vzoom)); render(); }); });
  el.querySelector("[data-vfit]").addEventListener("click", function () { state.zoom = 1; render(); });
  el.querySelector("[data-vrotate]").addEventListener("click", function () { state.rot = (state.rot + 90) % 360; render(); });
  el.querySelector("[data-vdownload]").addEventListener("click", function (e) { if (this.getAttribute("href") === "#") e.preventDefault(); });
  stage.addEventListener("scroll", function () {
    var pages = stage.querySelectorAll("[data-page]"), top = stage.scrollTop + 80, cur = 1;
    pages.forEach(function (p) { if (p.offsetTop <= top) cur = +p.dataset.page; });
    if (cur !== state.page) { state.page = cur; document.getElementById("viewerPage").textContent = cur + " / " + state.pages; el.querySelector("[data-vprev]").disabled = cur <= 1; el.querySelector("[data-vnext]").disabled = cur >= state.pages; }
  });
  document.addEventListener("keydown", function (e) {
    if (!el.classList.contains("open")) return;
    if (e.key === "Escape") window.UmViewer.close();
    else if (e.key === "+" || e.key === "=") { state.zoom = Math.min(2.5, state.zoom + 0.25); render(); }
    else if (e.key === "-") { state.zoom = Math.max(0.5, state.zoom - 0.25); render(); }
    else if (e.key === "ArrowRight" || e.key === "PageDown") goTo(state.page + 1);
    else if (e.key === "ArrowLeft" || e.key === "PageUp") goTo(state.page - 1);
  });
  // Botones con data-view="nombre|pdf|páginas|tamaño" abren el visor.
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-view]"); if (!b) return;
    e.preventDefault();
    var p = b.dataset.view.split("|");
    window.UmViewer.open({ name: p[0], kind: p[1], pages: +p[2] || 1, size: p[3] }, b);
  });
})();
