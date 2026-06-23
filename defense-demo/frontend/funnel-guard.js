(function (global) {
  "use strict";

  function requireQueueToken() {
    const token = localStorage.getItem("defense_queue_token");
    if (!token) {
      alert("กรุณาผ่านห้องรอก่อนเลือกที่นั่ง");
      location.href = "/";
      return null;
    }
    return token;
  }

  function requireMemberCode() {
    const code = localStorage.getItem("defense_member_code");
    if (!code) {
      location.href = "/member-code";
      return null;
    }
    return code;
  }

  function requireCart() {
    const token = requireQueueToken();
    if (!token) return null;
    const code = requireMemberCode();
    if (!code) return null;
    const cartId = localStorage.getItem("defense_cart_id");
    if (!cartId) {
      alert("กรุณาเลือกที่นั่งก่อนชำระเงิน");
      location.href = "/seats";
      return null;
    }
    return { token, cartId };
  }

  function purchaseDeadlineMs() {
    const issued = parseFloat(localStorage.getItem("defense_token_issued_at") || "0");
    const limitMin = window.TTM_EVENT?.purchaseLimitMinutes || 10;
    if (!issued) return null;
    return issued * 1000 + limitMin * 60 * 1000;
  }

  function startPurchaseTimer(el, onExpire) {
    const deadline = purchaseDeadlineMs();
    if (!deadline || !el) return null;

    function tick() {
      const left = deadline - Date.now();
      if (left <= 0) {
        el.textContent = "หมดเวลาซื้อแล้ว";
        el.classList.add("timer-expired");
        if (onExpire) onExpire();
        return;
      }
      const min = Math.floor(left / 60000);
      const sec = Math.floor((left % 60000) / 1000);
      el.textContent = "เวลาซื้อเหลือ " + min + ":" + String(sec).padStart(2, "0");
    }

    tick();
    return setInterval(tick, 1000);
  }

  global.TTMFunnel = {
    requireQueueToken,
    requireMemberCode,
    requireCart,
    purchaseDeadlineMs,
    startPurchaseTimer,
  };
})(window);
