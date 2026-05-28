(function () {
  "use strict";

  const token = TTMFunnel.requireQueueToken();
  if (!token) return;

  const eventId = window.TTM_EVENT?.id || "demo-concert-2026";
  const eventName = window.TTM_EVENT?.name || "2026-27 JACOB WORLD TOUR IN BANGKOK";

  TTMUI.renderDefenseFooter(false);
  TTMUI.setPageTitle("Seat Selection");
  document.getElementById("event-name").textContent = eventName;

  let selectedSeat = null;
  let cartId = null;

  const els = {
    seats: document.getElementById("seats"),
    statusMsg: document.getElementById("status-msg"),
    defenseMsg: document.getElementById("defense-msg"),
    btnCheckout: document.getElementById("btn-checkout"),
    purchaseTimer: document.getElementById("purchase-timer"),
  };

  TTMFunnel.startPurchaseTimer(els.purchaseTimer, () => {
    els.btnCheckout.disabled = true;
    showMsg("หมดเวลาซื้อ — token หมดอายุ", "error");
  });

  DefenseTelemetry.track("funnel", { step: "seat_map" });

  function showMsg(text, type) {
    els.defenseMsg.textContent = text;
    els.defenseMsg.className = "alert-banner " + (type || "");
    els.defenseMsg.classList.remove("hidden");
  }

  async function loadSeats() {
    const res = await fetch("/api/seats/" + eventId, {
      credentials: "include",
      headers: { "x-session-id": DefenseTelemetry.sessionId },
    });
    if (!res.ok) {
      showMsg("Layer 1: ไม่สามารถโหลดที่นั่งได้", "error");
      return;
    }
    const data = await res.json();
    els.seats.innerHTML = "";
    data.seats.forEach((s) => {
      const d = document.createElement("div");
      d.className = "seat " + s.status;
      d.innerHTML =
        '<span class="seat-label">' +
        s.seatId +
        '</span><span class="seat-status">' +
        s.status +
        "</span>";
      if (s.status === "available") {
        d.onmouseenter = () => {
          DefenseTelemetry.track("seat_hover", { seatId: s.seatId, dwellMs: 800 });
        };
        d.onclick = () => selectSeat(s.seatId, d);
      }
      els.seats.appendChild(d);
    });
  }

  async function selectSeat(seatId, el) {
    document.querySelectorAll(".seat").forEach((x) => x.classList.remove("selected"));
    el.classList.add("selected");
    selectedSeat = seatId;
    els.btnCheckout.disabled = true;
    els.statusMsg.textContent = "กำลังล็อกที่นั่ง (ส่ง Telemetry → Fraud Engine)...";
    DefenseTelemetry.track("seat_select", { seatId });
    await DefenseTelemetry.flush();

    const res = await fetch("/api/funnel/add-to-cart", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "x-session-id": DefenseTelemetry.sessionId,
        "x-queueit-token": token,
      },
      body: JSON.stringify({
        input: { eventId, ticketType: seatId, quantity: 1 },
      }),
    });

    if (res.status === 403) {
      const body = await res.json().catch(() => ({}));
      const err = body.errors?.[0] || body;
      showMsg(
        "Layer 3 (AI Fraud): ถูกบล็อก — " +
          (err.message || err.error || JSON.stringify(err.extensions || err)),
        "error"
      );
      els.statusMsg.textContent = "";
      return;
    }

    const data = await res.json();
    if (data.errors) {
      showMsg("Layer 3: " + data.errors[0].message, "error");
      els.statusMsg.textContent = "";
      return;
    }

    if (!data.data?.addToCart?.success) {
      showMsg("ที่นั่งถูกล็อกโดยคนอื่นแล้ว", "error");
      loadSeats();
      return;
    }

    cartId = data.data.addToCart.cartId;
    localStorage.setItem("defense_cart_id", cartId);
    els.defenseMsg.classList.add("hidden");
    els.statusMsg.textContent = "ล็อกที่นั่ง " + seatId + " สำเร็จ (cart: " + cartId + ")";
    els.btnCheckout.disabled = false;
    loadSeats();
  }

  els.btnCheckout.onclick = () => {
    if (!cartId) return;
    location.href = "/checkout";
  };

  loadSeats();
})();
