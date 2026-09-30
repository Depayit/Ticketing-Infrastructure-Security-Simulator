(function (global) {
  "use strict";

  function renderDefenseFooter(queueIdEl) {
    const footer = document.querySelector(".Ticket-footer");
    if (!footer || footer.dataset.rendered) return;
    footer.dataset.rendered = "1";
    footer.innerHTML =
      '<span class="footer-brand">DEFENSE LIVE</span>' +
      '<span class="footer-note">ระบบจำลองสำหรับการศึกษาและทดสอบ ไม่มีการขายบัตรหรือรับชำระเงินจริง</span>' +
      (queueIdEl ? '<div class="queue-id" id="queue-id"></div>' : "");
  }

  function setPageTitle(suffix) {
    const name = window.ticket_EVENT?.name || "Ticket Event";
    document.title = "Defense Live — " + (suffix ? suffix + " · " : "") + name;
  }

  global.TTMUI = { renderDefenseFooter, setPageTitle };
})(window);
