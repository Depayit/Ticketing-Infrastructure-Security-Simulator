(function () {
  "use strict";

  const session = TTMFunnel.requireCart();
  if (!session) return;
  const { token, cartId } = session;

  TTMUI.renderDefenseFooter(false);
  TTMUI.setPageTitle("Checkout");

  // Populate seat info from localStorage
  const seatId = localStorage.getItem("defense_selected_seat") || "—";
  const qty = parseInt(localStorage.getItem("defense_quantity") || "1", 10);
  
  const orderSeatEl = document.getElementById("order-seat");
  if (orderSeatEl) orderSeatEl.textContent = seatId;
  const orderQtyEl = document.getElementById("order-quantity");
  if (orderQtyEl) orderQtyEl.textContent = qty + " ใบ";

  let challengeId = new URLSearchParams(location.search).get("challenge");

  // Fetch Event Config dynamically
  (async function() {
    try {
      const res = await fetch("/api/event-config");
      if (res.ok) {
        const config = await res.json();
        document.getElementById("event-name").textContent = config.eventName;
        const zone = config.zones.find(z => z.id === seatId) || { price: 0 };
        const totalPrice = zone.price * qty;
        const orderPriceEl = document.getElementById("order-price");
        if (orderPriceEl) {
          orderPriceEl.textContent = totalPrice > 0 ? totalPrice.toLocaleString() + " ฿" : "— ฿";
        }
      }
    } catch (e) {
      console.warn("Could not load event config", e);
    }
  })();

  // Render Registration Forms
  const regFormsContainer = document.getElementById("registration-forms");
  if (regFormsContainer) {
    for (let i = 1; i <= qty; i++) {
      const formCard = document.createElement("div");
      formCard.className = "payment-card"; // Reuse card style for consistency
      formCard.style.display = "block";
      formCard.style.marginBottom = "10px";
      formCard.style.padding = "16px";
      formCard.style.cursor = "default";
      
      const title = document.createElement("div");
      title.style.fontWeight = "bold";
      title.style.marginBottom = "10px";
      title.textContent = "ลงทะเบียนลำดับที่ " + i;
      
      const input = document.createElement("input");
      input.type = "text";
      input.name = "ticket_name_" + i;
      input.placeholder = "ชื่อ-นามสกุลบน Ticket*";
      input.style.width = "100%";
      input.style.padding = "10px";
      input.style.border = "1px solid #ccc";
      input.style.borderRadius = "6px";
      input.required = true;
      
      formCard.appendChild(title);
      formCard.appendChild(input);
      regFormsContainer.appendChild(formCard);
    }
  }

  const els = {
    defenseMsg: document.getElementById("defense-msg"),
    panelPay: document.getElementById("panel-pay"),
    panel3ds: document.getElementById("panel-3ds"),
    panelQr: document.getElementById("panel-qr"),
    panelSuccess: document.getElementById("panel-success"),
    step1: document.getElementById("step-pill-1"),
    step2: document.getElementById("step-pill-2"),
    step3: document.getElementById("step-pill-3"),
    orderResult: document.getElementById("order-result"),
    purchaseTimer: document.getElementById("purchase-timer"),
    timerBar: document.getElementById("timer-bar"),
    stickyBar: document.getElementById("sticky-bar"),
    ccFormSection: document.getElementById("cc-form-section"),
  };

  // Stepper lines
  const stepperLines = document.querySelectorAll(".stepper-line");

  TTMFunnel.startPurchaseTimer(els.purchaseTimer, function () {
    els.timerBar.classList.add("timer-expired");
  });

  DefenseTelemetry.track("funnel", { step: "checkout" });

  /* ── Helpers ──────────────────────────────────────── */
  function showMsg(text, type) {
    els.defenseMsg.textContent = text;
    els.defenseMsg.className = "alert-banner " + (type || "");
    els.defenseMsg.classList.remove("hidden");
    els.defenseMsg.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function setStepperDone(stepEl, lineIdx) {
    stepEl.classList.remove("active");
    stepEl.classList.add("done");
    if (stepperLines[lineIdx]) stepperLines[lineIdx].classList.add("done");
  }

  function show3dsPanel(id) {
    challengeId = id;
    els.panelPay.classList.add("hidden");
    els.panel3ds.classList.remove("hidden");
    els.stickyBar.classList.add("hidden");
    setStepperDone(els.step1, 0);
    els.step2.classList.add("active");
    // Focus OTP input
    setTimeout(() => document.getElementById("otp")?.focus(), 300);
  }

  function showQrPanel(id) {
    challengeId = id;
    els.panelPay.classList.add("hidden");
    els.panelQr.classList.remove("hidden");
    els.stickyBar.classList.add("hidden");
    setStepperDone(els.step1, 0);
    els.step2.classList.add("active");
  }

  function showSuccess(orderId) {
    els.panel3ds.classList.add("hidden");
    els.panelQr.classList.remove("hidden");
    els.panelQr.classList.add("hidden");
    els.panelSuccess.classList.remove("hidden");
    els.stickyBar.classList.add("hidden");
    els.timerBar.classList.add("hidden");
    setStepperDone(els.step2, 1);
    els.step3.classList.add("active");
    els.orderResult.textContent = "Order ID: " + orderId;
    
    // Clear all session states
    localStorage.removeItem("defense_queue_token");
    localStorage.removeItem("defense_member_code");
    localStorage.removeItem("defense_cart_id");
    localStorage.removeItem("defense_selected_seat");
    localStorage.removeItem("defense_quantity");
    localStorage.removeItem("defense_show_date");
    sessionStorage.removeItem("ttm_waiting_room_state");
    
    alert("การชำระเงินเสร็จสิ้น! ระบบจะนำคุณกลับไปหน้าห้องล็อกอิน");
    location.href = "/";
  }

  /* ── Payment Method Selection ────────────────────── */
  const paymentCards = document.querySelectorAll(".payment-card");
  paymentCards.forEach((card) => {
    card.addEventListener("click", () => {
      paymentCards.forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");

      const method = card.dataset.method;
      // Show/hide CC form
      if (els.ccFormSection) {
        els.ccFormSection.style.display = method === "credit_card" ? "" : "none";
      }
    });
  });

  /* ── Promo Card Selection (toggle) ──────────────── */
  document.querySelectorAll(".promo-card").forEach((card) => {
    card.addEventListener("click", () => {
      card.classList.toggle("selected");
    });
  });

  /* ── Checkout / Pay ─────────────────────────────── */
  const btnPay = document.getElementById("btn-pay");
  btnPay.onclick = async () => {
    const email = document.getElementById("buyer-email").value.trim();
    const cardNumber = document.getElementById("card-number").value.trim();
    const selectedMethod = document.querySelector('input[name="payment-method"]:checked')?.value || "credit_card";

    const attendees = [];
    const nameInputs = document.querySelectorAll('input[name^="ticket_name_"]');
    nameInputs.forEach(input => {
      if (input.value.trim()) {
        attendees.push(input.value.trim());
      }
    });

    btnPay.classList.add("loading");
    btnPay.disabled = true;

    try {
      const res = await fetch("/api/funnel/checkout", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "x-session-id": DefenseTelemetry.sessionId,
          "x-queueit-token": token,
        },
        body: JSON.stringify({
          input: {
            cartId,
            queueToken: token,
            buyer: { email },
            attendees: attendees,
            paymentMethod: selectedMethod,
            card: { number: cardNumber },
          },
        }),
      });

      if (res.status === 403) {
        const body = await res.json().catch(() => ({}));
        showMsg(
          "Layer 4 (3DS/Carding): " +
            (body.detail?.errorCode || body.error || "ถูกบล็อก"),
          "error"
        );
        return;
      }

      const data = await res.json();
      if (data.errors) {
        const ext = data.errors[0].extensions || {};
        showMsg(
          "Layer 4: " + (ext.errorCode || data.errors[0].message),
          "error"
        );
        return;
      }

      const checkout = data.data?.checkout;
      if (checkout?.status === "3ds_required" && checkout.challengeId) {
        els.defenseMsg.classList.add("hidden");
        show3dsPanel(checkout.challengeId);
        return;
      }

      if (checkout?.status === "qr_required" && checkout.challengeId) {
        els.defenseMsg.classList.add("hidden");
        showQrPanel(checkout.challengeId);
        return;
      }

      showMsg("Checkout ไม่สำเร็จ", "error");
    } finally {
      btnPay.classList.remove("loading");
      btnPay.disabled = false;
    }
  };

  /* ── 3-D Secure OTP Verify ─────────────────────── */
  const btnVerify = document.getElementById("btn-verify");
  btnVerify.onclick = async () => {
    const otp = document.getElementById("otp").value.trim();

    btnVerify.classList.add("loading");
    btnVerify.disabled = true;

    try {
      const res = await fetch("/api/3ds/verify", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-session-id": DefenseTelemetry.sessionId,
        },
        body: JSON.stringify({ challenge_id: challengeId, otp }),
      });

      if (res.status === 402) {
        showMsg("Layer 4: OTP ผิด — ที่นั่งถูกปล่อยกลับแล้ว", "error");
        return;
      }

      const data = await res.json();
      if (data.success) {
        els.defenseMsg.classList.add("hidden");
        showSuccess(data.orderId);
        DefenseTelemetry.track("funnel", {
          step: "order_complete",
          orderId: data.orderId,
        });
      } else {
        showMsg("Layer 4: 3DS verification failed", "error");
      }
    } finally {
      btnVerify.classList.remove("loading");
      btnVerify.disabled = false;
    }
  };

  /* ── QR Verify (Demo) ─────────────────────── */
  const btnVerifyQr = document.getElementById("btn-verify-qr");
  if (btnVerifyQr) {
    btnVerifyQr.onclick = async () => {
      btnVerifyQr.classList.add("loading");
      btnVerifyQr.disabled = true;

      try {
        const res = await fetch("/api/qr/verify", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-session-id": DefenseTelemetry.sessionId,
          },
          body: JSON.stringify({ challenge_id: challengeId }),
        });

        if (res.status === 404) {
          showMsg("QR หมดอายุ — ที่นั่งถูกปล่อยกลับแล้ว", "error");
          return;
        }

        const data = await res.json();
        if (data.success) {
          els.defenseMsg.classList.add("hidden");
          showSuccess(data.orderId);
          DefenseTelemetry.track("funnel", {
            step: "order_complete",
            orderId: data.orderId,
            method: "qr"
          });
        } else {
          showMsg("QR verification failed", "error");
        }
      } finally {
        btnVerifyQr.classList.remove("loading");
        btnVerifyQr.disabled = false;
      }
    };
  }

  /* ── Resend OTP (demo: just focus) ─────────────── */
  const btnResend = document.getElementById("btn-resend-otp");
  if (btnResend) {
    btnResend.onclick = (e) => {
      e.preventDefault();
      document.getElementById("otp").value = "";
      document.getElementById("otp").focus();
      showMsg("OTP ใหม่ถูกส่งแล้ว (demo: 123456)", "success");
    };
  }

  /* ── Resume if returning with challenge ─────────── */
  if (challengeId) {
    show3dsPanel(challengeId);
  }
})();
