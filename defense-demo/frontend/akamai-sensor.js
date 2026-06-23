/**
 * Akamai Bot Manager — Client-side Sensor Simulation
 *
 * Collects browser fingerprint signals and submits them to the gateway's
 * /api/sensor endpoint.  The gateway then computes a bot_score and sets
 * Akamai-style cookies (_abck, ak_bmsc, bm_sv).
 *
 * This is a *demo* stub — the real Akamai sensor is obfuscated and
 * cryptographic.  Here we just gather genuine browser signals so the
 * gateway can score a real browser ≈ 15-25 (low / human).
 */
(function (global) {
  "use strict";

  const SENSOR_ENDPOINT = "/api/sensor";

  /* Session ID — shared with DefenseTelemetry when available */
  let sessionId = localStorage.getItem("defense_session_id");
  if (!sessionId) {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      sessionId = crypto.randomUUID();
    } else {
      sessionId = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
        var r = (Math.random() * 16) | 0,
          v = c === "x" ? r : (r & 0x3) | 0x8;
        return v.toString(16);
      });
    }
    localStorage.setItem("defense_session_id", sessionId);
  }

  /* ── Fingerprint Signals ────────────────────────────── */

  function canvasHash() {
    try {
      const c = document.createElement("canvas");
      c.width = 200;
      c.height = 50;
      const ctx = c.getContext("2d");
      ctx.textBaseline = "top";
      ctx.font = "14px 'Arial'";
      ctx.fillStyle = "#f60";
      ctx.fillRect(0, 0, 200, 50);
      ctx.fillStyle = "#069";
      ctx.fillText("AkamaiSensor:demo", 2, 15);
      ctx.fillStyle = "rgba(102,204,0,0.7)";
      ctx.fillText("canvas-fp", 4, 32);
      return simpleHash(c.toDataURL());
    } catch {
      return null;
    }
  }

  function audioHash() {
    try {
      if (!window.OfflineAudioContext && !window.webkitOfflineAudioContext) return null;
      return "audio-" + simpleHash(navigator.userAgent + screen.colorDepth);
    } catch {
      return null;
    }
  }

  function webglVendor() {
    try {
      const c = document.createElement("canvas");
      const gl = c.getContext("webgl") || c.getContext("experimental-webgl");
      if (!gl) return null;
      const ext = gl.getExtension("WEBGL_debug_renderer_info");
      return ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : null;
    } catch {
      return null;
    }
  }

  function webglRenderer() {
    try {
      const c = document.createElement("canvas");
      const gl = c.getContext("webgl") || c.getContext("experimental-webgl");
      if (!gl) return null;
      const ext = gl.getExtension("WEBGL_debug_renderer_info");
      return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null;
    } catch {
      return null;
    }
  }

  function simpleHash(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0;
    }
    return "h" + Math.abs(hash).toString(36);
  }

  function collectSignals() {
    const signals = {
      signal_count: 120 + Math.floor(Math.random() * 40), // 120-160 realistic range
      user_agent: navigator.userAgent,
      platform: navigator.platform || "",
      language: navigator.language || "",
      languages: (navigator.languages || []).join(","),
      screen_w: screen.width,
      screen_h: screen.height,
      color_depth: screen.colorDepth,
      pixel_ratio: window.devicePixelRatio || 1,
      timezone_offset: new Date().getTimezoneOffset(),
      hardware_concurrency: navigator.hardwareConcurrency || 0,
      max_touch_points: navigator.maxTouchPoints || 0,
      canvas_hash: canvasHash(),
      audio_hash: audioHash(),
      webgl_vendor: webglVendor(),
      webgl_renderer: webglRenderer(),
      cookie_enabled: navigator.cookieEnabled,
      do_not_track: navigator.doNotTrack || "unset",
      pdf_viewer: !!(navigator.pdfViewerEnabled),
      ts: Date.now(),
    };

    // Fingerprint — combined hash
    const fp = simpleHash(
      [
        signals.user_agent,
        signals.screen_w,
        signals.screen_h,
        signals.color_depth,
        signals.canvas_hash,
        signals.webgl_renderer,
        signals.timezone_offset,
        signals.hardware_concurrency,
      ].join("|")
    );
    signals.fingerprint = fp;

    return signals;
  }

  /* ── Submit Sensor ──────────────────────────────────── */

  async function submitSensor() {
    const signals = collectSignals();
    const payload = btoa(JSON.stringify(signals));

    const res = await fetch(SENSOR_ENDPOINT, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "x-session-id": sessionId,
      },
      body: JSON.stringify({
        sensor_data: payload,
        session_id: sessionId,
        fingerprint: signals.fingerprint,
      }),
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || body.detail?.error || "SENSOR_SUBMIT_FAILED");
    }

    const data = await res.json();

    // Update session ID if the server assigned one
    if (data.session_id && data.session_id !== sessionId) {
      sessionId = data.session_id;
      localStorage.setItem("defense_session_id", sessionId);
    }

    return {
      ok: data.ok,
      session_id: sessionId,
      bot_score: data.bot_score,
      challenged: data.challenged || false,
    };
  }

  function getSessionId() {
    return sessionId;
  }

  /* ── Public API ─────────────────────────────────────── */
  global.AkamaiSensor = {
    submitSensor,
    getSessionId,
    collectSignals,
  };
})(window);
