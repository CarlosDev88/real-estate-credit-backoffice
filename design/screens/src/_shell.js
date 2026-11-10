// Comportamiento compartido de las pantallas de referencia: tema y menú móvil.
(function () {
  // Tema: solo claro y oscuro. Claro por defecto; la elección se recuerda en este navegador.
  var btn = document.getElementById("themeToggle");
  var cur = "light";
  try { cur = localStorage.getItem("um-theme") === "dark" ? "dark" : "light"; } catch (e) {}
  var applyTheme = function (m) {
    document.documentElement.setAttribute("data-theme", m);
    if (btn) {
      btn.dataset.mode = m;
      var label = m === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro";
      btn.setAttribute("aria-label", label);
      btn.title = label;
    }
  };
  applyTheme(cur);
  if (btn) btn.addEventListener("click", function () {
    cur = cur === "dark" ? "light" : "dark";
    try { localStorage.setItem("um-theme", cur); } catch (e) {}
    applyTheme(cur);
  });
  var side = document.querySelector(".side");
  var open = document.getElementById("menuToggle");
  var scrim = document.querySelector(".scrim");
  if (side && open && scrim) {
    var set = function (v) {
      side.classList.toggle("open", v);
      scrim.classList.toggle("show", v);
      open.setAttribute("aria-expanded", String(v));
      if (v) { var f = side.querySelector("a, button"); if (f) f.focus(); }
    };
    open.addEventListener("click", function () { set(!side.classList.contains("open")); });
    scrim.addEventListener("click", function () { set(false); });
    side.querySelectorAll(".close-menu").forEach(function (b) { b.addEventListener("click", function () { set(false); open.focus(); }); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && side.classList.contains("open")) { set(false); open.focus(); } });
  }
})();

// ---------- toasts ----------
// UmToast.show({ tone: "success" | "danger" | "warning" | "info", title, message, action: { label, onClick }, duration })
// Éxito e información se cierran solos (5 s); los errores se quedan hasta que el usuario los cierra.
// Se pausan al pasar el mouse o al enfocar. Máximo 3 visibles: el más antiguo se va primero.
(function () {
  var host = document.createElement("div");
  host.className = "toasts";
  host.setAttribute("aria-live", "polite");
  host.setAttribute("aria-relevant", "additions");
  document.body.appendChild(host);
  var icons = {
    success: '<path d="M10 1a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm-1.2 13L4.5 9.7l1.4-1.4 2.9 2.9 5.3-5.3 1.4 1.4-6.7 6.7Z"/>',
    danger: '<path d="M10 1a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm-1 4h2v6H9V5Zm0 8h2v2H9v-2Z"/>',
    warning: '<path d="M10 2 1 18h18L10 2Zm-1 6h2v5H9V8Zm0 6h2v2H9v-2Z"/>',
    info: '<path d="M10 1a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm-1 4h2v2H9V5Zm0 4h2v6H9V9Z"/>'
  };
  function remove(t) { if (!t.isConnected || t.classList.contains("leaving")) return; t.classList.add("leaving"); setTimeout(function () { t.remove(); }, 180); }
  window.UmToast = {
    show: function (o) {
      var tone = o.tone || "info";
      var duration = o.duration != null ? o.duration : (tone === "danger" ? 0 : 5000);
      var t = document.createElement("div");
      t.className = "toast " + tone;
      t.setAttribute("role", tone === "danger" ? "alert" : "status");
      t.innerHTML = '<svg class="t-ico" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">' + icons[tone] + "</svg>" +
        "<div><b></b>" + (o.message ? "<p></p>" : "") + (o.action ? '<div class="t-actions"><button class="btn btn-default btn-sm" type="button"></button></div>' : "") + "</div>" +
        '<button class="btn btn-ghost btn-icon btn-sm t-close" type="button" aria-label="Cerrar aviso"><svg viewBox="0 0 20 20" fill="currentColor"><path d="m5.4 4 4.6 4.6L14.6 4 16 5.4 11.4 10l4.6 4.6-1.4 1.4-4.6-4.6L5.4 16 4 14.6 8.6 10 4 5.4 5.4 4Z"/></svg></button>' +
        (duration ? '<span class="t-timer" style="animation: toast-timer ' + duration + 'ms linear forwards"></span>' : "");
      t.querySelector("b").textContent = o.title;
      if (o.message) t.querySelector("p").textContent = o.message;
      if (o.action) { var a = t.querySelector(".t-actions button"); a.textContent = o.action.label; a.addEventListener("click", function () { o.action.onClick && o.action.onClick(); remove(t); }); }
      t.querySelector(".t-close").addEventListener("click", function () { remove(t); });
      host.appendChild(t);
      while (host.children.length > 3) remove(host.firstElementChild);
      if (duration) {
        var left = duration, started = Date.now(), timer = setTimeout(function () { remove(t); }, left), bar = t.querySelector(".t-timer");
        var pause = function () { clearTimeout(timer); left -= Date.now() - started; if (bar) bar.style.animationPlayState = "paused"; };
        var resume = function () { started = Date.now(); timer = setTimeout(function () { remove(t); }, left); if (bar) bar.style.animationPlayState = "running"; };
        t.addEventListener("mouseenter", pause); t.addEventListener("mouseleave", resume);
        t.addEventListener("focusin", pause); t.addEventListener("focusout", resume);
      }
      return t;
    }
  };
})();
