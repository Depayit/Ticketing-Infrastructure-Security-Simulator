(function () {
  "use strict";

  const session = TTMFunnel.requireCart();
  if (!session) return;

  const { token, cartId } = session;
  const eventName = window.TTM_EVENT?.name || "2026-27 JACOB WORLD TOUR IN BANGKOK";

  TTMUI.renderDefenseFooter(false);
  TTMUI.setPageTitle("Checkout");
  document.getElementById("event-name").textContent = eventName;

  let challengeId = new URLSearchParams(location.search).get("challenge");

  const els = {
    defenseMsg: document.getElementById("defense-msg"),
    panelPay: document.getElementById("panel-pay"),
    panel3ds: document.getElementById("panel-3ds"),
    panelSuccess: document.getElementById("panel-success"),
    step1: document.getElementById("step-pill-1"),
    step2: document.getElementById("step-pill-2"),
    step3: document.getElementById("step-pill-3"),
    orderResult: document.getElementById("order-result"),
    purchaseTimer: document.getElementById("purchase-timer"),
  };

  TTMFunnel.startPurchaseTimer(els.purchaseTimer);

  DefenseTelemetry.track("funnel", { step: "checkout" });

  function showMsg(text, type) {
    els.defenseMsg.textContent = text;
    els.defenseMsg.className = "alert-banner " + (type || "");
    els.defenseMsg.classList.remove("hidden");
  }

  function show3dsPanel(id) {
    challengeId = id;
    els.panelPay.classList.add("hidden");
    els.panel3ds.classList.remove("hidden");
    els.step1.classList.remove("active");
    els.step1.classList.add("done");
    els.step2.classList.add("active");
  }

  function showSuccess(orderId) {
    els.panel3ds.classList.add("hidden");
    els.panelSuccess.classList.remove("hidden");
    els.step2.classList.remove("active");
    els.step2.classList.add("done");
    els.step3.classList.add("active");
    els.orderResult.textContent = "Order ID: " + orderId;
    localStorage.removeItem("defense_cart_id");
  }

  document.getElementById("btn-pay").onclick = async () => {
    const email = document.getElementById("buyer-email").value.trim();
    const cardNumber = document.getElementById("card-number").value.trim();
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
          paymentMethod: "credit_card",
          card: { number: cardNumber },
        },
      }),
    });

    if (res.status === 403) {
      const body = await res.json().catch(() => ({}));
      showMsg("Layer 4 (3DS/Carding): " + (body.detail?.errorCode || body.error || "ถูกบล็อก"), "error");
      return;
    }

    const data = await res.json();
    if (data.errors) {
      const ext = data.errors[0].extensions || {};
      showMsg("Layer 4: " + (ext.errorCode || data.errors[0].message), "error");
      return;
    }

    const checkout = data.data?.checkout;
    if (checkout?.status === "3ds_required" && checkout.challengeId) {
      els.defenseMsg.classList.add("hidden");
      show3dsPanel(checkout.challengeId);
      return;
    }

    showMsg("Checkout ไม่สำเร็จ", "error");
  };

  document.getElementById("btn-verify").onclick = async () => {
    const otp = document.getElementById("otp").value.trim();
    const res = await fetch("/api/3ds/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-session-id": DefenseTelemetry.sessionId },
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
      DefenseTelemetry.track("funnel", { step: "order_complete", orderId: data.orderId });
    } else {
      showMsg("Layer 4: 3DS verification failed", "error");
    }
  };

  if (challengeId) {
    show3dsPanel(challengeId);
  }
})();
