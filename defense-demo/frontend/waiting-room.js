(function () {
  "use strict";

  const EVENT = window.TTM_EVENT || {
    id: "demo-concert-2026",
    name: "2026-27 JACOB WORLD TOUR IN BANGKOK",
  };

  const STORAGE_KEY = "ttm_waiting_room_state";
  const params = new URLSearchParams(location.search);
  const isDemo = params.get("demo") === "1";

  const CONFIG = {
    eventId: EVENT.id,
    eventName: EVENT.name,
    preLoginMinutes: isDemo ? 1 : 30,
    queueDurationMs: isDemo ? 12000 : 45000,
    activityCheckMs: isDemo ? 8000 : 45000,
    activityTimeoutMs: isDemo ? 15000 : 60000,
    pollIntervalMs: 1500,
  };

  const now = Date.now();
  const saleStartMs = isDemo
    ? now + 8000
    : parseInt(localStorage.getItem("ttm_sale_start_ms") || "0", 10) || now + 5 * 60 * 1000;

  if (!localStorage.getItem("ttm_sale_start_ms")) {
    localStorage.setItem("ttm_sale_start_ms", String(saleStartMs));
  }

  const preLoginStartMs = saleStartMs - CONFIG.preLoginMinutes * 60 * 1000;
  const queueId = getOrCreateQueueId();

  let state = loadState();
  let countdownTimer = null;
  let queueTimer = null;
  let pollTimer = null;
  let activityTimer = null;
  let activityDeadline = null;
  let queueProgress = state.queueProgress || 0;
  let pollingActive = false;
  let lastQueuePosition = null;
  let sensorReady = false;
  let botScore = null;
  let queueJoined = false;

  const els = {
    demoBadge: document.getElementById("demo-badge"),
    phaseTooEarly: document.getElementById("phase-too-early"),
    phaseLogin: document.getElementById("phase-login"),
    phaseCountdown: document.getElementById("phase-countdown"),
    phaseQueue: document.getElementById("phase-queue"),
    phaseAdmitted: document.getElementById("phase-admitted"),
    entryOverlay: document.getElementById("entry-overlay"),
    activityModal: document.getElementById("activity-modal"),
    eventTitle: document.querySelectorAll(".event-title"),
    saleStartLabel: document.getElementById("sale-start-label"),
    countdownDisplay: document.getElementById("countdown-display"),
    statusUpdated: document.querySelectorAll(".status-updated"),
    queueId: null,
    progressFill: document.getElementById("progress-fill"),
    progressUser: document.getElementById("progress-user"),
    queuePosition: document.getElementById("queue-position"),
    loginForm: document.getElementById("login-form"),
    btnJoinQueue: document.getElementById("btn-join-queue"),
    btnActivityConfirm: document.getElementById("btn-activity-confirm"),
    btnEnterSeats: document.getElementById("btn-enter-seats"),
    preLoginNote: document.getElementById("pre-login-note"),
    earlyMessage: document.getElementById("early-message"),
    defenseError: document.getElementById("defense-error"),
    botScoreLabel: document.getElementById("bot-score-label"),
    akamaiChallengeModal: document.getElementById("akamai-challenge-modal"),
    btnAkamaiChallenge: document.getElementById("btn-akamai-challenge"),
  };

  TTMUI.renderDefenseFooter(true);
  els.queueId = document.getElementById("queue-id");
  TTMUI.setPageTitle("Waiting Room");

  function getOrCreateQueueId() {
    let id = sessionStorage.getItem("ttm_queue_id");
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem("ttm_queue_id", id);
    }
    return id;
  }

  function loadState() {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "{}");
    } catch {
      return {};
    }
  }

  function saveState(patch) {
    state = { ...state, ...patch };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function formatTime(date) {
    return date.toLocaleTimeString("th-TH", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  }

  function updateStatusTimestamp() {
    const label = formatTime(new Date());
    els.statusUpdated.forEach((el) => {
      el.textContent = label;
    });
  }

  function showDefenseError(msg) {
    if (!els.defenseError) return;
    els.defenseError.textContent = msg;
    els.defenseError.classList.remove("hidden");
  }

  function hideDefenseError() {
    els.defenseError?.classList.add("hidden");
  }

  async function funnelRequest(endpoint, payload) {
    const res = await fetch(endpoint, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "x-session-id": window.DefenseTelemetry?.sessionId || AkamaiSensor?.getSessionId?.() || "",
      },
      body: JSON.stringify(payload || {}),
    });

    if (res.status === 403) {
      const body = await res.json().catch(() => ({}));
      const msg = body.error || body.detail?.error || body.detail || "ถูกบล็อก";
      const layer = body.layer === "akamai" || msg.includes("AKAMAI") ? "Akamai" : "IP/WAF";
      showDefenseError("Layer (" + layer + "): " + msg);
      if (msg.includes("AKAMAI") || msg.includes("CHALLENGE")) {
        showAkamaiChallenge();
      }
      throw new Error("WAF_BLOCKED");
    }
    if (res.status === 429) {
      showDefenseError("Layer 1 (IP/WAF): Rate limit — ลองใหม่อีกครั้ง");
      throw new Error("RATE_LIMITED");
    }

    return res.json();
  }

  function hideAllPhases() {
    [
      els.phaseTooEarly,
      els.phaseLogin,
      els.phaseCountdown,
      els.phaseQueue,
      els.phaseAdmitted,
      els.entryOverlay,
      els.activityModal,
    ].forEach((el) => el && el.classList.add("hidden"));
  }

  function showPhase(el) {
    hideAllPhases();
    if (el) el.classList.remove("hidden");
    updateStatusTimestamp();
  }

  function setEventCopy() {
    els.eventTitle.forEach((el) => {
      el.textContent = CONFIG.eventName;
    });
    if (els.saleStartLabel) {
      els.saleStartLabel.textContent = formatTime(new Date(saleStartMs));
    }
    if (els.queueId) {
      els.queueId.textContent = "Queue ID: " + queueId;
    }
    if (els.demoBadge) {
      els.demoBadge.classList.toggle("hidden", !isDemo);
    }
    if (els.preLoginNote) {
      els.preLoginNote.textContent = isDemo
        ? "โหมด Demo: เข้าได้ก่อนเปิดขาย 1 นาที · นับถอยหลัง ~8 วินาที"
        : "เข้าสู่ระบบได้ก่อนเวลาเปิดขาย " + CONFIG.preLoginMinutes + " นาที";
    }
  }

  function renderCountdown(ms) {
    const totalSec = Math.max(0, Math.ceil(ms / 1000));
    const minutes = Math.floor(totalSec / 60);
    const seconds = totalSec % 60;
    if (els.countdownDisplay) {
      els.countdownDisplay.innerHTML =
        String(minutes).padStart(2, "0") +
        ' <span style="font-size:1rem;font-weight:600;color:#6b7280">Minutes</span> ' +
        String(seconds).padStart(2, "0") +
        ' <span style="font-size:1rem;font-weight:600;color:#6b7280">Seconds</span>';
    }
  }

  function clearTimers() {
    [countdownTimer, queueTimer, pollTimer, activityTimer].forEach((t) => {
      if (t) clearInterval(t);
    });
    if (pollTimer) clearTimeout(pollTimer);
    countdownTimer = queueTimer = pollTimer = activityTimer = null;
  }

  function determinePhase() {
    const t = Date.now();
    if (state.admitted) return "admitted";
    if (state.inQueue) return "queue";
    if (state.joinedQueue === false && t >= saleStartMs) return "entry";
    if (state.loggedIn && t < saleStartMs) return "countdown";
    if (t >= preLoginStartMs) return "login";
    return "too_early";
  }

  function showTooEarly() {
    showPhase(els.phaseTooEarly);
    if (els.earlyMessage) {
      els.earlyMessage.textContent =
        "ห้องรอยังไม่เปิด กรุณากลับมาใหม่เมื่อถึงเวลา " + formatTime(new Date(preLoginStartMs));
    }
    countdownTimer = setInterval(() => {
      if (Date.now() >= preLoginStartMs) {
        clearInterval(countdownTimer);
        boot();
      }
    }, 1000);
  }

  function showLogin() {
    showPhase(els.phaseLogin);
  }

  function showCountdown() {
    showPhase(els.phaseCountdown);
    function tick() {
      const remaining = saleStartMs - Date.now();
      renderCountdown(remaining);
      updateStatusTimestamp();
      if (remaining <= 0) {
        clearInterval(countdownTimer);
        showEntryZone();
      }
    }
    tick();
    countdownTimer = setInterval(tick, 250);
  }

  function showEntryZone() {
    saveState({ loggedIn: true, joinedQueue: false });
    els.entryOverlay.classList.remove("hidden");
    els.phaseCountdown.classList.remove("hidden");
    updateStatusTimestamp();
    DefenseTelemetry.track("funnel", { step: "entry_zone" });
  }

  function showQueue() {
    showPhase(els.phaseQueue);
    saveState({ inQueue: true, joinedQueue: true });
    updateProgress(queueProgress);
    startQueueProgress();
    startActivityChecks();
    DefenseTelemetry.track("funnel", { step: "waiting_room" });
  }

  function showAdmitted(token, issuedAt) {
    clearTimers();
    saveState({ admitted: true, inQueue: false, queueToken: token });
    localStorage.setItem("defense_queue_token", token);
    if (issuedAt) {
      DefenseTelemetry.setTokenIssuedAt(issuedAt);
    } else {
      DefenseTelemetry.setTokenIssuedAt(Date.now() / 1000);
    }
    DefenseTelemetry.track("funnel", { step: "admitted" });
    showPhase(els.phaseAdmitted);
    updateProgress(100);
  }

  function updateProgress(pct) {
    queueProgress = Math.max(0, Math.min(100, pct));
    saveState({ queueProgress });
    if (els.progressFill) els.progressFill.style.width = queueProgress + "%";
    if (els.progressUser) els.progressUser.style.left = queueProgress + "%";
  }

  function updateBotScoreLabel(score) {
    if (!els.botScoreLabel || score == null) return;
    els.botScoreLabel.classList.remove("hidden");
    const human = score <= 25 ? "สูง (มนุษย์)" : score <= 55 ? "ปานกลาง" : "ต่ำ (เสี่ยงบอท)";
    els.botScoreLabel.textContent =
      "Akamai Bot Score: " + score + " / 100 (0=มนุษย์) · Priority: " + human;
  }

  function updateQueuePosition(pos, score) {
    if (!pos || !els.queuePosition) return;
    lastQueuePosition = pos;
    const scoreTxt = score != null ? " · Bot Score " + score : "";
    els.queuePosition.textContent =
      "Queue position ~" + pos + " (Queue-it randomized · priority by score)" + scoreTxt;
  }

  function showAkamaiChallenge() {
    els.akamaiChallengeModal?.classList.remove("hidden");
  }

  function hideAkamaiChallenge() {
    els.akamaiChallengeModal?.classList.add("hidden");
  }

  async function initAkamaiSensor() {
    if (!window.AkamaiSensor) return;
    try {
      const result = await AkamaiSensor.submitSensor();
      if (result.session_id && window.DefenseTelemetry?.syncSessionId) {
        DefenseTelemetry.syncSessionId(result.session_id);
      }
      sensorReady = true;
      botScore = result.bot_score;
      updateBotScoreLabel(botScore);
      if (result.challenged) showAkamaiChallenge();
      else hideAkamaiChallenge();
    } catch (e) {
      console.warn("Akamai sensor failed", e);
      showDefenseError("Akamai Sensor: " + (e.message || "failed"));
    }
  }

  function startQueueProgress() {
    const start = Date.now();
    queueTimer = setInterval(() => {
      const elapsed = Date.now() - start;
      const simulated = Math.min(88, (elapsed / CONFIG.queueDurationMs) * 88);
      if (lastQueuePosition) {
        const fromQueue = Math.max(0, 100 - Math.min(lastQueuePosition, 500) / 5);
        updateProgress(Math.max(simulated, Math.min(fromQueue, 88)));
      } else {
        updateProgress(simulated);
      }
      updateStatusTimestamp();
      if (queueProgress >= 82 && !pollingActive) {
        pollingActive = true;
        pollQueueStatus();
      }
    }, 400);
  }

  async function pollQueueStatus() {
    try {
      const data = await funnelRequest("/api/funnel/queue-status", {
        eventId: CONFIG.eventId,
        joinQueue: !queueJoined,
      });
      if (!queueJoined) queueJoined = true;
      hideDefenseError();
      const qs = data.data?.queueStatus;

      if (qs?.botScore != null) {
        botScore = qs.botScore;
        updateBotScoreLabel(botScore);
      }

      if (qs?.status === "challenge" || qs?.challengeRequired) {
        showAkamaiChallenge();
        if (qs?.queuePosition) updateQueuePosition(qs.queuePosition, qs.botScore);
        pollTimer = setTimeout(pollQueueStatus, CONFIG.pollIntervalMs);
        return;
      }

      hideAkamaiChallenge();

      if (qs?.queuePosition) {
        updateQueuePosition(qs.queuePosition, qs.botScore);
      }

      if (qs?.status === "admitted" && qs.token) {
        clearTimers();
        updateProgress(100);
        setTimeout(() => showAdmitted(qs.token, qs.issuedAt), 500);
        return;
      }
    } catch (err) {
      if (err.message !== "WAF_BLOCKED" && err.message !== "RATE_LIMITED") {
        console.warn("queue poll failed", err);
      }
    }

    pollTimer = setTimeout(pollQueueStatus, CONFIG.pollIntervalMs);
  }

  function startActivityChecks() {
    scheduleActivityCheck();
  }

  function scheduleActivityCheck() {
    activityTimer = setTimeout(() => {
      if (!state.inQueue || state.admitted) return;
      showActivityModal();
    }, CONFIG.activityCheckMs);
  }

  function showActivityModal() {
    els.phaseQueue.classList.remove("hidden");
    els.activityModal.classList.remove("hidden");
    activityDeadline = Date.now() + CONFIG.activityTimeoutMs;
    const timeout = setInterval(() => {
      if (Date.now() > activityDeadline && !els.activityModal.classList.contains("hidden")) {
        clearInterval(timeout);
        handleActivityTimeout();
      }
    }, 1000);
  }

  function hideActivityModal() {
    els.activityModal.classList.add("hidden");
    els.phaseQueue.classList.remove("hidden");
    scheduleActivityCheck();
  }

  function handleActivityTimeout() {
    saveState({ inQueue: false, joinedQueue: false, queueProgress: 0 });
    clearTimers();
    queueProgress = 0;
    pollingActive = false;
    alert("คุณไม่ได้ตอบยืนยัน — ออกจากคิวแล้ว กรุณาเข้าคิวใหม่");
    showEntryZone();
  }

  function boot() {
    clearTimers();
    setEventCopy();
    updateStatusTimestamp();
    setInterval(updateStatusTimestamp, 5000);

    const phase = determinePhase();
    switch (phase) {
      case "too_early":
        showTooEarly();
        break;
      case "login":
        showLogin();
        break;
      case "countdown":
        showCountdown();
        break;
      case "entry":
        showEntryZone();
        break;
      case "queue":
        showQueue();
        if (queueProgress >= 82) {
          pollingActive = true;
          pollQueueStatus();
        }
        break;
      case "admitted":
        showPhase(els.phaseAdmitted);
        break;
      default:
        showLogin();
    }
  }

  els.loginForm?.addEventListener("submit", (e) => {
    e.preventDefault();
    const email = document.getElementById("login-email")?.value?.trim();
    const password = document.getElementById("login-password")?.value;
    if (!email || !password) return;
    saveState({ loggedIn: true, email });
    DefenseTelemetry.track("funnel", { step: "login", email });
    if (Date.now() >= saleStartMs) showEntryZone();
    else showCountdown();
  });

  els.btnJoinQueue?.addEventListener("click", async () => {
    if (!sensorReady) {
      await initAkamaiSensor();
    }
    els.entryOverlay.classList.add("hidden");
    queueJoined = false;
    showQueue();
  });

  els.btnAkamaiChallenge?.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/challenge/pass", {
        method: "POST",
        credentials: "include",
        headers: {
          "x-session-id": DefenseTelemetry?.sessionId || AkamaiSensor.getSessionId(),
        },
      });
      if (!res.ok) throw new Error("challenge failed");
      const data = await res.json();
      botScore = data.bot_score;
      updateBotScoreLabel(botScore);
      hideAkamaiChallenge();
      await initAkamaiSensor();
      if (state.inQueue) pollQueueStatus();
    } catch (e) {
      showDefenseError("Challenge: " + e.message);
    }
  });

  els.btnActivityConfirm?.addEventListener("click", () => {
    hideActivityModal();
    DefenseTelemetry.track("funnel", { step: "activity_confirmed" });
  });

  els.btnEnterSeats?.addEventListener("click", () => {
    location.href = "/seats";
  });

  initAkamaiSensor().finally(() => boot());
})();
