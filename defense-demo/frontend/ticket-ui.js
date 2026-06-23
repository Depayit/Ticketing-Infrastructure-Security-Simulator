(function (global) {
  "use strict";

  function renderDefenseFooter(queueIdEl) {
    const footer = document.querySelector(".Ticket-footer");
    if (!footer || footer.dataset.rendered) return;
    footer.dataset.rendered = "1";
    footer.innerHTML =
      '<div class="defense-layers">' +
      '<span class="layer-pill layer-ip">Layer 1 · IP/WAF</span>' +
      '<span class="layer-pill layer-queue">Layer 2 · Queue</span>' +
      '<span class="layer-pill layer-ai">Layer 3 · AI Fraud</span>' +
      '<span class="layer-pill layer-3ds">Layer 4 · 3-D Secure</span>' +
      "</div>" +
      (queueIdEl ? '<div class="queue-id" id="queue-id"></div>' : "");
  }

  function setPageTitle(suffix) {
    const name = window.ticket_EVENT?.name || "Ticket Event";
    document.title = "ThaiTicket Major — " + (suffix ? suffix + " · " : "") + name;
  }

  global.TTMUI = { renderDefenseFooter, setPageTitle };
})(window);
