(function (global) {
  const ENDPOINT = "/api/telemetry";
  let sessionId = localStorage.getItem("defense_session_id");
  if (!sessionId) {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      sessionId = crypto.randomUUID();
    } else {
      sessionId = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c == "x" ? r : (r & 0x3 | 0x8);
        return v.toString(16);
      });
    }
    localStorage.setItem("defense_session_id", sessionId);
  }
  let tokenIssuedAt = parseFloat(localStorage.getItem("defense_token_issued_at") || "0");
  const buffer = [];

  function now() { return Date.now(); }

  function track(type, data) {
    buffer.push({ type, t: now(), ...data });
    if (buffer.length >= 20) flush();
  }

  function setTokenIssuedAt(ts) {
    tokenIssuedAt = ts;
    localStorage.setItem("defense_token_issued_at", String(ts));
  }

  async function flush() {
    if (!buffer.length) return;
    const batch = { session_id: sessionId, token_issued_at: tokenIssuedAt, events: buffer.splice(0) };
    try {
      await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-session-id": sessionId },
        body: JSON.stringify(batch),
        keepalive: true,
      });
    } catch (e) { console.warn("telemetry flush failed", e); }
  }

  document.addEventListener("mousemove", (e) => {
    if (Math.random() > 0.15) return;
    track("mousemove", { x: e.clientX, y: e.clientY });
  });
  document.addEventListener("click", (e) => {
    track("click", { x: e.clientX, y: e.clientY, target: e.target.tagName });
  });
  document.addEventListener("scroll", () => track("scroll", { deltaY: window.scrollY }));

  function syncSessionId(newId) {
    if (newId && newId !== sessionId) {
      sessionId = newId;
      localStorage.setItem("defense_session_id", sessionId);
    }
  }

  global.DefenseTelemetry = { track, flush, setTokenIssuedAt, syncSessionId, get sessionId() { return sessionId; } };
  setInterval(flush, 3000);
  window.addEventListener("beforeunload", flush);
})(window);
