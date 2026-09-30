(async function () {
  "use strict";

  const token = TTMFunnel.requireQueueToken();
  if (!token) return;

  const memberCode = TTMFunnel.requireMemberCode();
  if (!memberCode) return;

  // Fetch Event Config dynamically
  let eventConfig = { eventId: "demo-concert-2026", eventName: "Event", maxTicketsPerAccount: 1, zones: [] };
  try {
    const chosenEvent = sessionStorage.getItem("defense_active_event_id") || "demo-concert-2026";
    const res = await fetch("/api/event-config?event_id=" + encodeURIComponent(chosenEvent));
    if (res.ok) eventConfig = await res.json();
  } catch (e) {
    console.warn("Failed to fetch event config, using defaults", e);
  }

  const eventId = eventConfig.eventId;
  const eventName = eventConfig.eventName;

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
    showDateRadios: document.querySelectorAll('input[name="show-date"]'),
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
    els.seats.innerHTML = "";
    const qtySelect = document.getElementById("ticket-quantity");
    qtySelect.innerHTML = "";
    for (let i = 1; i <= eventConfig.maxTicketsPerAccount; i++) {
      const opt = document.createElement("option");
      opt.value = i;
      opt.textContent = i;
      qtySelect.appendChild(opt);
    }
    
    eventConfig.zones.forEach((z) => {
      const d = document.createElement("button");
      d.type = "button";
      d.id = "zone-" + z.id;
      d.className = "seat available";
      d.dataset.zoneColor = z.color;
      d.style.setProperty("--zone-color", z.color);
      const label = document.createElement("span");
      label.className = "seat-label";
      label.textContent = z.name;
      const price = document.createElement("span");
      price.className = "seat-status";
      price.textContent = "฿" + z.price.toLocaleString();
      d.append(label, price);
      if (z.isRestricted) {
        const badge = document.createElement("span");
        badge.className = "restricted-view";
        badge.textContent = "มุมมองจำกัด";
        d.appendChild(badge);
      }
      
      d.onmouseenter = () => {
        DefenseTelemetry.track("seat_hover", { seatId: z.id, dwellMs: 800 });
      };
      d.onclick = () => selectSeat(z.id, d);
      els.seats.appendChild(d);
    });
    
    startSeatPolling();
  }

  // Show date selection logic
  let selectedShowDate = null;
  const seatsContainer = document.getElementById("seats");
  const quantitySection = document.getElementById("quantity-section");

  function updateZoneAvailability() {
    if (!selectedShowDate) {
      seatsContainer.style.opacity = "0.4";
      seatsContainer.style.pointerEvents = "none";
    } else {
      seatsContainer.style.opacity = "1";
      seatsContainer.style.pointerEvents = "auto";
    }
  }

  els.showDateRadios.forEach((radio) => {
    radio.addEventListener("change", (e) => {
      selectedShowDate = e.target.value;
      updateZoneAvailability();
    });
  });

  updateZoneAvailability();

  let seatPollTimer = null;
  async function startSeatPolling() {
    if (seatPollTimer) clearTimeout(seatPollTimer);
    try {
      const res = await fetch("/api/seats/" + eventId);
      if (res.ok) {
        const data = await res.json();
        data.seats.forEach((s) => {
          const el = document.getElementById("zone-" + s.seatId);
          if (el) {
            if (s.status === "locked" || s.status === "sold") {
              el.className = "seat held";
              el.disabled = true;
              
              if (selectedSeat === s.seatId) {
                selectedSeat = null;
                document.getElementById("quantity-section").style.display = "none";
                els.btnCheckout.disabled = true;
                els.btnCheckout.textContent = "ล็อกที่นั่ง";
              }
            } else {
              el.className = "seat available" + (selectedSeat === s.seatId ? " selected" : "");
              el.disabled = false;
            }
          }
        });
      }
    } catch (err) {}
    seatPollTimer = setTimeout(startSeatPolling, 3000);
  }

  async function selectSeat(seatId, el) {
    if (el.classList.contains("held") || el.classList.contains("sold")) return;
    document.querySelectorAll(".seat").forEach((x) => x.classList.remove("selected"));
    el.classList.add("selected");
    selectedSeat = seatId;
    document.getElementById("quantity-section").style.display = "block";
    els.btnCheckout.disabled = false;
    els.btnCheckout.textContent = "ล็อกที่นั่ง";
  }
  
  async function performAddToCart() {
    els.btnCheckout.disabled = true;
    els.statusMsg.textContent = "กำลังตรวจสอบและล็อกที่นั่งให้คุณ...";
    DefenseTelemetry.track("seat_select", { seatId: selectedSeat });
    await DefenseTelemetry.flush();

    const qty = parseInt(document.getElementById("ticket-quantity").value, 10);

    const res = await fetch("/api/funnel/add-to-cart", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "x-session-id": DefenseTelemetry.sessionId,
        "x-queueit-token": token,
      },
      body: JSON.stringify({
        input: { eventId, ticketType: selectedSeat, quantity: qty },
      }),
    });

    if (res.status === 428) {
      const gate = await res.json();
      if (gate.status === "need_login") location.href = "/login?next=/seats";
      if (gate.status === "need_captcha") location.href = "/captcha?position=" + encodeURIComponent(gate.position) + "&next=/seats";
      if (gate.status === "need_sensor") location.href = "/";
      return;
    }

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
      const errorCode = data.data?.addToCart?.errorCode;
      showMsg(errorCode === "EVENT_PAUSED" ? "อีเวนต์หยุดขายชั่วคราว" :
        errorCode === "EVENT_SOLD_OUT" ? "บัตรหมดแล้ว" : "ที่นั่งถูกล็อกโดยคนอื่นแล้ว", "error");
      loadSeats();
      return;
    }

    cartId = data.data.addToCart.cartId;
    localStorage.setItem("defense_cart_id", cartId);
    localStorage.setItem("defense_selected_seat", selectedSeat);
    localStorage.setItem("defense_quantity", qty);
    localStorage.setItem("defense_show_date", selectedShowDate);
    els.defenseMsg.classList.add("hidden");
    els.statusMsg.textContent = "ล็อกสำเร็จ (cart: " + cartId + ")";
    
    // Redirect to checkout immediately after successful add-to-cart
    location.href = "/checkout";
  }

  els.btnCheckout.onclick = () => {
    if (!selectedShowDate) {
      els.statusMsg.textContent = "กรุณาเลือกรอบการแสดงก่อน";
      return;
    }
    if (!selectedSeat) return;
    performAddToCart();
  };

  loadSeats();
})();
