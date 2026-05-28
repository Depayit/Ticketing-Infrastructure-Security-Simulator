(function (global) {
  const ENDPOINT = "/api/telemetry";
  let sessionId = localStorage.getItem("defense_session_id");
  if (!sessionId) {
    sessionId = crypto.randomUUID();
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

  global.DefenseTelemetry = { track, flush, setTokenIssuedAt, sessionId };
  setInterval(flush, 3000);
  window.addEventListener("beforeunload", flush);
})(window);
