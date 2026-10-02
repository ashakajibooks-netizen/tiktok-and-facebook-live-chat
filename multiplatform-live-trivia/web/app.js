/**
 * Multiplatform LIVE Trivia - Host Dashboard & Overlay Engine
 */
(() => {
  // 1. Detect View Mode
  const isOverlayMode =
    window.location.pathname.includes("/overlay") ||
    new URLSearchParams(window.location.search).get("overlay") === "true";

  if (isOverlayMode) {
    document.body.classList.add("overlay-mode");
  }

  // 2. DOM Elements
  const stateBadge = document.getElementById("state-badge");
  const questionCount = document.getElementById("question-count");
  const questionBox = document.getElementById("question-box");
  const answerReveal = document.getElementById("answer-reveal");
  const timerBar = document.getElementById("timer-bar");
  const timerDigits = document.getElementById("timer-digits");
  const leaderboardList = document.getElementById("leaderboard-list");
  const leaderboardTitle = document.getElementById("leaderboard-title");
  const btnStart = document.getElementById("btn-start");
  const btnStop = document.getElementById("btn-stop");
  const tiktokStatus = document.getElementById("tiktok-status");
  const fbStatus = document.getElementById("fb-status");
  const queueStats = document.getElementById("queue-stats");

  // 3. State Clocks & Countdown
  let currentSnapshot = null;
  let countdownTimerId = null;
  const QUESTION_WINDOW_SEC = 10.0;

  // 4. WebSocket Management
  let socket = null;
  let reconnectInterval = 1000;

  function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      reconnectInterval = 1000;
      updateStateBadge("CONNECTED", "waiting");
    };

    socket.onmessage = (event) => {
      try {
        const snapshot = JSON.parse(event.data);
        renderSnapshot(snapshot);
      } catch (err) {
        console.error("Error parsing WebSocket snapshot:", err);
      }
    };

    socket.onclose = () => {
      updateStateBadge("DISCONNECTED", "stopped");
      setTimeout(connectWebSocket, Math.min(reconnectInterval *= 1.5, 10000));
    };

    socket.onerror = (err) => {
      socket.close();
    };
  }

  // 5. Snapshot Rendering
  function renderSnapshot(snap) {
    currentSnapshot = snap;

    // Header counter & state
    questionCount.textContent = `Q ${snap.question_number}/${snap.total_questions}`;
    updateStateBadge(snap.state);

    // Question & Answer Reveal
    if (snap.question) {
      questionBox.textContent = snap.question;
    } else if (snap.state === "WAITING_FOR_START") {
      questionBox.textContent = "Waiting for host to trigger START...";
    } else if (snap.state === "FINISHED") {
      questionBox.textContent = "Game Complete! Congratulations to the winners.";
    }

    if (snap.state === "RESULT" && snap.correct_answer) {
      answerReveal.style.display = "block";
      answerReveal.textContent = `Correct Answer: ${snap.correct_answer}`;
    } else {
      answerReveal.style.display = "none";
    }

    // Host Buttons state
    if (btnStart) {
      btnStart.disabled = snap.state !== "WAITING_FOR_START";
    }
    if (btnStop) {
      btnStop.disabled = snap.state === "STOPPED" || snap.state === "FINISHED";
    }

    // Timer Sync
    syncCountdown(snap);

    // Leaderboard (Top 5 during game, Top 3 on FINISHED)
    renderLeaderboard(snap);

    // Telemetry (TikTok / FB statuses)
    if (!isOverlayMode && snap.platforms) {
      updatePlatformTelemetry(snap.platforms);
      if (queueStats) {
        queueStats.textContent = `Queue: ${snap.queue_size}/${snap.queue_capacity} (Dropped: ${snap.dropped_messages})`;
      }
    }
  }

  // 6. Countdown Animation
  function syncCountdown(snap) {
    clearInterval(countdownTimerId);

    if (snap.state === "ACTIVE" && snap.deadline) {
      const updateClock = () => {
        // Fallback relative timer estimate based on deadline
        const nowSec = performance.now() / 1000;
        // Snap deadline delta calculation
        const remaining = Math.max(0, snap.time_remaining !== undefined ? snap.time_remaining : (snap.deadline - nowSec));
        
        timerDigits.textContent = Math.ceil(remaining);
        const percent = Math.min(100, Math.max(0, (remaining / QUESTION_WINDOW_SEC) * 100));
        timerBar.style.width = `${percent}%`;

        timerBar.classList.remove("warning", "critical");
        if (remaining <= 3) {
          timerBar.classList.add("critical");
        } else if (remaining <= 5) {
          timerBar.classList.add("warning");
        }

        if (remaining <= 0) {
          clearInterval(countdownTimerId);
        }
      };

      updateClock();
      countdownTimerId = setInterval(updateClock, 100);
    } else {
      timerBar.style.width = snap.state === "ACTIVE" ? "100%" : "0%";
      timerDigits.textContent = snap.state === "ACTIVE" ? "10" : "0";
    }
  }

  // 7. Leaderboard Table
  function renderLeaderboard(snap) {
    if (!leaderboardList) return;
    leaderboardList.innerHTML = "";

    const isFinal = snap.state === "FINISHED";
    const maxEntries = isFinal ? 3 : 5;
    if (leaderboardTitle) {
      leaderboardTitle.textContent = isFinal ? "🏆 Final Winners (Top 3)" : "Top 5 Players";
    }

    const players = (snap.leaderboard || []).slice(0, maxEntries);

    if (players.length === 0) {
      leaderboardList.innerHTML = `<div style="color:var(--text-muted);font-size:0.85rem;padding:6px 0;">No scores recorded yet.</div>`;
      return;
    }

    players.forEach((p, idx) => {
      const row = document.createElement("div");
      row.className = "leaderboard-row";
      const platformClass = (p.platform || "").toLowerCase().includes("tiktok") ? "tiktok" : "facebook";

      row.innerHTML = `
        <div class="player-info">
          <span class="player-rank">#${idx + 1}</span>
          <span class="platform-pill ${platformClass}">${p.platform || "LIVE"}</span>
          <span class="player-name">${escapeHtml(p.display_name || p.username || "Anonymous")}</span>
        </div>
        <span class="player-score">${p.score} pts</span>
      `;
      leaderboardList.appendChild(row);
    });
  }

  function updatePlatformTelemetry(platforms) {
    if (tiktokStatus && platforms.tiktok) {
      setDotStatus(tiktokStatus, platforms.tiktok);
    }
    if (fbStatus && platforms.facebook) {
      setDotStatus(fbStatus, platforms.facebook);
    }
  }

  function setDotStatus(container, stateStr) {
    const dot = container.querySelector(".status-dot");
    const label = container.querySelector(".status-text");
    dot.className = "status-dot";

    const s = (stateStr || "").toUpperCase();
    if (s === "CONNECTED") dot.classList.add("connected");
    else if (s === "CONNECTING") dot.classList.add("connecting");
    else if (s === "DISCONNECTED" || s === "ENDED") dot.classList.add("disconnected");

    label.textContent = s;
  }

  function updateStateBadge(state, forceClass) {
    if (!stateBadge) return;
    stateBadge.textContent = state;
    stateBadge.className = "state-badge";
    if (forceClass) {
      stateBadge.classList.add(forceClass);
    } else {
      const s = (state || "").toLowerCase();
      if (s === "active") stateBadge.classList.add("active");
      else if (s.includes("waiting")) stateBadge.classList.add("waiting");
      else if (s.includes("draining")) stateBadge.classList.add("draining");
      else if (s.includes("result")) stateBadge.classList.add("result");
      else if (s.includes("stop")) stateBadge.classList.add("stopped");
    }
  }

  // 8. Host Actions & Spacebar Behavior
  async function triggerStart() {
    if (!currentSnapshot || currentSnapshot.state !== "WAITING_FOR_START") return;
    try {
      await fetch("/game/start", { method: "POST" });
    } catch (e) {
      console.error("Failed to post /game/start:", e);
    }
  }

  async function triggerStop() {
    try {
      await fetch("/game/stop", { method: "POST" });
    } catch (e) {
      console.error("Failed to post /game/stop:", e);
    }
  }

  if (btnStart) btnStart.addEventListener("click", triggerStart);
  if (btnStop) btnStop.addEventListener("click", triggerStop);

  // Keydown SPACE strictly when page is focused (Section 36)
  window.addEventListener("keydown", (e) => {
    if (isOverlayMode) return;
    if (e.code === "Space" || e.key === " ") {
      // Do not trigger if typing in an input element
      const tag = document.activeElement ? document.activeElement.tagName : "";
      if (tag === "INPUT" || tag === "TEXTAREA") return;

      e.preventDefault();
      triggerStart();
    }
  });

  function escapeHtml(str) {
    return str.replace(/[&<>'"]/g, 
      tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
  }

  // Initialize
  connectWebSocket();
})();