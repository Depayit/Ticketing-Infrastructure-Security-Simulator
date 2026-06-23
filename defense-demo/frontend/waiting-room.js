(function () {
  "use strict";

  const EVENT = window.ticket_EVENT || {
    id: "demo-concert-2026",
    name: "BTS WORLD TOUR 'ARIRANG' IN BANGKOK",
  };

  const STORAGE_KEY = "ticket_waiting_room_state";
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
  let saleStartMs = parseInt(localStorage.getItem("ticket_sale_start_ms") || "0", 10) || now + 5 * 60 * 1000;

  if (!localStorage.getItem("ticket_sale_start_ms")) {
    localStorage.setItem("ticket_sale_start_ms", String(saleStartMs));
  }

  let preLoginStartMs = saleStartMs - CONFIG.preLoginMinutes * 60 * 1000;
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
  let pollCount = 0;

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
    let id = sessionStorage.getItem("ticket_queue_id");
    if (!id) {
      if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
        id = crypto.randomUUID();
      } else {
        id = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function(c) {
          var r = Math.random() * 16 | 0, v = c == "x" ? r : (r & 0x3 | 0x8);
          return v.toString(16);
        });
      }
      sessionStorage.setItem("ticket_queue_id", id);
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
    pollCount = 0;
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
    if (pollCount >= 15) {
      showDefenseError("Layer 2 (Queue): เกินขีดจำกัดการโพล (สูงสุด 15 ครั้ง) — กรุณาเข้าคิวใหม่");
      clearTimers();
      return;
    }
    pollCount++;
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

      if (qs?.status === "pre_queue") {
        saleStartMs = qs.startTime * 1000;
        localStorage.setItem("ticket_sale_start_ms", String(saleStartMs));
        clearTimers();
        saveState({ inQueue: false, joinedQueue: false, loggedIn: true });
        showCountdown();
        return;
      }

      if (qs?.status === "admitted" && qs.token) {
        clearTimers();
        updateProgress(100);
        setTimeout(() => triggerFinalCaptcha(qs.token, qs.issuedAt), 500);
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

  async function boot() {
    try {
      const data = await funnelRequest("/api/funnel/queue-status", {
        eventId: CONFIG.eventId,
        joinQueue: false,
      });
      const qs = data?.data?.queueStatus;
      if (qs?.status === "pre_queue" && qs?.startTime) {
        saleStartMs = qs.startTime * 1000;
        localStorage.setItem("ticket_sale_start_ms", String(saleStartMs));
      } else if (qs?.startTime === 0) {
        saleStartMs = Date.now() - 1000; // already started
      }
      preLoginStartMs = saleStartMs - CONFIG.preLoginMinutes * 60 * 1000;
    } catch (err) {
      console.warn("initial queue status fetch failed", err);
    }

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
    const captcha = document.getElementById("login-captcha")?.checked;
    
    if (!email || !password || !captcha) {
      if (!captcha) alert("กรุณายืนยันว่าคุณไม่ใช่โปรแกรมอัตโนมัติ (CAPTCHA)");
      return;
    }
    
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
    location.href = "/member-code";
  });

  /* --- FINAL CAPTCHA LOGIC --- */
  let captchaTimeoutId = null;
  let captchaSeconds = 60;
  let activeCaptchaType = -1;
  let finalToken = null;
  let finalIssuedAt = null;

  function triggerFinalCaptcha(token, issuedAt) {
    finalToken = token;
    finalIssuedAt = issuedAt;
    els.finalCaptchaModal = document.getElementById("final-captcha-modal");
    els.finalCaptchaModal.classList.remove("hidden");
    startCaptchaTimer();
    
    document.querySelectorAll(".captcha-type-container").forEach(el => el.classList.add("hidden"));
    
    activeCaptchaType = Math.floor(Math.random() * 5); // 0 to 4
    
    if (activeCaptchaType === 0) initCaptchaQuiz();
    else if (activeCaptchaType === 1) initCaptchaSlider();
    else if (activeCaptchaType === 2) initCaptchaColor();
    else if (activeCaptchaType === 3) initCaptchaSort("fan");
    else if (activeCaptchaType === 4) initCaptchaSort("lyric");
  }

  function startCaptchaTimer() {
    captchaSeconds = 60;
    const timerEl = document.getElementById("captcha-countdown");
    timerEl.innerText = `00:00:${captchaSeconds}`;
    timerEl.style.color = "#111";
    
    captchaTimeoutId = setInterval(() => {
      captchaSeconds--;
      let secStr = captchaSeconds < 10 ? "0" + captchaSeconds : captchaSeconds;
      timerEl.innerText = `00:00:${secStr}`;
      if (captchaSeconds <= 10) timerEl.style.color = "#dc2626";
      
      if (captchaSeconds <= 0) {
        captchaFail("หมดเวลา กรุณาต่อคิวใหม่");
      }
    }, 1000);
  }

  function captchaFail(reason) {
    clearInterval(captchaTimeoutId);
    alert(reason);
    location.reload();
  }

  function captchaSuccess() {
    clearInterval(captchaTimeoutId);
    els.finalCaptchaModal.classList.add("hidden");
    showAdmitted(finalToken, finalIssuedAt);
  }

  function initCaptchaQuiz() {
    document.getElementById("captcha-quiz").classList.remove("hidden");
    const questions = [
      { q: "เวทีคอนเสิร์ตครั้งแรกของ BTS ในประเทศไทยคือเวทีคอนเสิร์ตใด", a: "7 สีคอนเสิร์ต", opts: ["BTS WORLD TOUR 'ARIRANG' IN BANGKOK", "BTS WORLD TOUR 'LOVE YOURSELF' BANGKOK", "BTS LIVE TRILOGY EPISODE III THE WINGS TOUR in Bangkok", "7 สีคอนเสิร์ต"] }
    ];
    const q = questions[0];
    document.getElementById("quiz-question-text").innerText = q.q;
    const container = document.getElementById("quiz-options-container");
    container.innerHTML = "";
    
    const shuffledOpts = [...q.opts].sort(() => Math.random() - 0.5);
    shuffledOpts.forEach(opt => {
      const btn = document.createElement("button");
      btn.className = "quiz-option-btn";
      btn.innerText = opt;
      btn.onclick = () => {
        if (opt === q.a) captchaSuccess();
        else captchaFail("ตอบคำถามผิด กรุณาต่อคิวใหม่");
      };
      container.appendChild(btn);
    });
  }

  function initCaptchaSlider() {
    document.getElementById("captcha-slider").classList.remove("hidden");
    const input = document.getElementById("slider-input");
    const piece = document.getElementById("slider-piece");
    const btn = document.getElementById("btn-verify-slider");
    
    // Dynamically create the target slot if it doesn't exist
    let slot = document.getElementById("slider-slot");
    if (!slot) {
      slot = document.createElement("div");
      slot.id = "slider-slot";
      const area = document.querySelector(".slider-puzzle-area");
      if (area) area.appendChild(slot);
    }
    
    const targetPercent = 50 + Math.random() * 35;
    input.value = 0;
    piece.style.left = "10px";
    slot.style.left = `calc(${targetPercent}% - ${targetPercent * 0.5}px)`;
    
    input.oninput = (e) => {
      const val = parseInt(e.target.value);
      piece.style.left = `calc(${val}% - ${val * 0.5}px)`;
    };
    
    btn.onclick = () => {
      const val = parseInt(input.value);
      if (Math.abs(val - targetPercent) < 8) captchaSuccess();
      else captchaFail("เลื่อนจิ๊กซอว์ไม่ตรง กรุณาต่อคิวใหม่");
    };
  }

  function initCaptchaColor() {
    document.getElementById("captcha-color").classList.remove("hidden");
    const targetBox = document.getElementById("color-target");
    const grid = document.getElementById("color-grid");
    const btn = document.getElementById("btn-verify-color");
    
    const colors = ["#f97316", "#ec4899", "#eab308", "#0ea5e9", "#22c55e", "#ef4444", "#8b5cf6", "#64748b", "#0f172a", "#14b8a6", "#d946ef", "#84cc16"];
    const targetColor = colors[Math.floor(Math.random() * colors.length)];
    targetBox.style.backgroundColor = targetColor;
    
    grid.innerHTML = "";
    let selectedColor = null;
    
    const shuffledColors = [...colors].sort(() => Math.random() - 0.5);
    shuffledColors.forEach(c => {
      const div = document.createElement("div");
      div.className = "color-box";
      div.style.backgroundColor = c;
      div.onclick = () => {
        document.querySelectorAll(".color-box").forEach(el => el.classList.remove("selected"));
        div.classList.add("selected");
        selectedColor = c;
        btn.disabled = false;
        btn.innerText = "Verify";
        btn.classList.remove("disabled");
      };
      grid.appendChild(div);
    });
    
    btn.onclick = () => {
      if (selectedColor === targetColor) captchaSuccess();
      else captchaFail("เลือกสีผิด กรุณาต่อคิวใหม่");
    };
  }

  function initCaptchaSort(type) {
    document.getElementById("captcha-sort-" + type).classList.remove("hidden");
    const list = document.getElementById("sortable-" + type);
    const btn = document.getElementById("btn-verify-" + type);
    list.innerHTML = "";
    
    let items = [];
    if (type === "fan") {
      items = [
        { id: 0, text: "ส่วนที่ 1 (ภาพใบหน้า)", class: "fan-0" },
        { id: 1, text: "ส่วนที่ 2 (คอเสื้อ)", class: "fan-1" },
        { id: 2, text: "ส่วนที่ 3 (ข้อความ FINAL EP)", class: "fan-2" },
        { id: 3, text: "ส่วนที่ 4 (ข้อความ FAN MEETING)", class: "fan-3" },
        { id: 4, text: "ส่วนที่ 5 (รายชื่อนักแสดง)", class: "fan-4" }
      ];
    } else {
      items = [
        { id: 0, text: "เอกราชจะไม่ให้ใครข่มขี่", class: "lyric-0" },
        { id: 1, text: "รักสามัคคี ไทยนี้รักสงบ แต่ถึงรบไม่ขลาด", class: "lyric-1" },
        { id: 2, text: "อยู่ดำรงคงไว้ได้ทั้งมวล ด้วยไทยล้วนหมาย", class: "lyric-2" },
        { id: 3, text: "ประเทศไทยรวมเลือดเนื้อชาติเชื้อไทย", class: "lyric-3" },
        { id: 4, text: "เป็นประชารัฐ ไผทของไทยทุกส่วน", class: "lyric-4" }
      ];
    }
    
    const shuffled = [...items].sort(() => Math.random() - 0.5);
    
    shuffled.forEach(item => {
      const div = document.createElement("div");
      div.className = "sortable-item " + (item.class || "");
      div.innerText = item.text;
      div.draggable = true;
      div.dataset.id = item.id;
      
      div.addEventListener("dragstart", () => div.classList.add("dragging"));
      div.addEventListener("dragend", () => div.classList.remove("dragging"));
      list.appendChild(div);
    });
    
    list.addEventListener("dragover", e => {
      e.preventDefault();
      const afterElement = getDragAfterElement(list, e.clientY);
      const draggable = document.querySelector(".dragging");
      if (afterElement == null) {
        list.appendChild(draggable);
      } else {
        list.insertBefore(draggable, afterElement);
      }
    });
    
    btn.onclick = () => {
      let currentOrder = Array.from(list.children).map(el => parseInt(el.dataset.id));
      let isCorrect = currentOrder.every((val, index) => val === index);
      if (isCorrect) captchaSuccess();
      else captchaFail("เรียงภาพผิด กรุณาต่อคิวใหม่");
    };
  }

  function getDragAfterElement(container, y) {
    const draggableElements = [...container.querySelectorAll('.sortable-item:not(.dragging)')];
    return draggableElements.reduce((closest, child) => {
      const box = child.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > closest.offset) {
        return { offset: offset, element: child };
      } else {
        return closest;
      }
    }, { offset: Number.NEGATIVE_INFINITY }).element;
  }

  initAkamaiSensor().finally(() => boot());
})();
