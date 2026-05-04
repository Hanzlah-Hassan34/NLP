const STORAGE_KEY = "dentabot.phase5.sessions";
const ACTIVE_KEY = "dentabot.phase5.active";

const el = {
  sessionList: document.getElementById("session-list"),
  chatWindow: document.getElementById("chat-window"),
  composer: document.getElementById("composer"),
  input: document.getElementById("message-input"),
  sendBtn: document.getElementById("send-btn"),
  recordBtn: document.getElementById("record-btn"),
  stopBtn: document.getElementById("stop-btn"),
  voiceStatus: document.getElementById("voice-status"),
  newBtn: document.getElementById("new-chat-btn"),
  resetBtn: document.getElementById("reset-btn"),
  status: document.getElementById("ws-status"),
  template: document.getElementById("message-template"),
};

const app = {
  ws: null,
  connected: false,
  sessions: [],
  activeId: null,
  inFlightSessionId: null,
  pendingBySession: {},
  mediaRecorder: null,
  voiceChunks: [],
  voiceMimeType: "audio/webm",
};

function uid(prefix = "s") {
  return `${prefix}-${Math.random().toString(16).slice(2, 10)}`;
}

function nowLabel(ts) {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(app.sessions));
  if (app.activeId) localStorage.setItem(ACTIVE_KEY, app.activeId);
}

function loadState() {
  const stored = localStorage.getItem(STORAGE_KEY);
  app.sessions = stored ? JSON.parse(stored) : [];
  app.activeId = localStorage.getItem(ACTIVE_KEY);

  if (!app.sessions.length) {
    createSession();
    return;
  }

  app.sessions.forEach((s) => {
    if (!Array.isArray(s.messages)) s.messages = [];
  });

  if (!app.sessions.some((s) => s.id === app.activeId)) {
    app.activeId = app.sessions[0].id;
  }
}

function getSessionById(id) {
  return app.sessions.find((s) => s.id === id);
}

function currentSession() {
  return getSessionById(app.activeId);
}

function createSession() {
  const s = {
    id: uid("chat"),
    title: "New conversation",
    createdAt: Date.now(),
    messages: [],
  };
  app.sessions.unshift(s);
  app.activeId = s.id;
  saveState();
  render();
}

function deleteSession(sessionId) {
  const idx = app.sessions.findIndex((s) => s.id === sessionId);
  if (idx < 0) return;

  if (app.connected && app.ws) {
    app.ws.send(JSON.stringify({ type: "reset", session_id: sessionId }));
  }

  delete app.pendingBySession[sessionId];
  if (app.inFlightSessionId === sessionId) {
    app.inFlightSessionId = null;
  }

  app.sessions.splice(idx, 1);
  if (!app.sessions.length) {
    createSession();
    return;
  }

  if (app.activeId === sessionId) {
    app.activeId = app.sessions[Math.max(0, idx - 1)].id;
  }

  saveState();
  render();
}

function setStatus(online) {
  app.connected = online;
  el.status.textContent = online ? "Online" : "Offline";
  el.status.classList.toggle("online", online);
  el.status.classList.toggle("offline", !online);
}

function setComposerEnabled(enabled) {
  el.input.disabled = !enabled;
  el.sendBtn.disabled = !enabled;
  el.recordBtn.disabled = !enabled;
}

function refreshComposerAvailability() {
  setComposerEnabled(app.connected && !app.inFlightSessionId);
}

function setVoiceStatus(text) {
  el.voiceStatus.textContent = text;
}

function updateSessionTitle(session) {
  const firstUser = session.messages.find((m) => m.role === "user");
  session.title = firstUser ? firstUser.content.slice(0, 30) : "New conversation";
}

function findPendingAssistantMessage(sessionId) {
  const session = getSessionById(sessionId);
  if (!session) return null;

  const pendingId = app.pendingBySession[sessionId];
  if (pendingId) {
    const byId = session.messages.find((m) => m.id === pendingId);
    if (byId) return byId;
  }

  for (let i = session.messages.length - 1; i >= 0; i -= 1) {
    const msg = session.messages[i];
    if (msg.role === "assistant" && msg.streaming) return msg;
  }
  return null;
}

function handleTokenEvent(message) {
  const sessionId = message.session_id;
  const session = getSessionById(sessionId);
  if (!session) return;

  const pending = findPendingAssistantMessage(sessionId);
  if (!pending) return;

  pending.content += message.data?.token || "";

  if (app.activeId === sessionId) {
    const bubble = document.querySelector(`[data-mid="${pending.id}"] .bubble`);
    if (bubble) {
      bubble.textContent = pending.content;
      el.chatWindow.scrollTop = el.chatWindow.scrollHeight;
    }
  }
}

function finalizeAssistantMessage(sessionId, finalText, isError = false) {
  const session = getSessionById(sessionId);
  if (!session) return;

  let pending = findPendingAssistantMessage(sessionId);
  if (!pending) {
    pending = {
      id: uid("m"),
      role: "assistant",
      content: "",
      ts: Date.now(),
      streaming: true,
      error: false,
    };
    session.messages.push(pending);
  }

  pending.content = finalText;
  pending.streaming = false;
  pending.error = isError;
  delete app.pendingBySession[sessionId];

  if (app.inFlightSessionId === sessionId) {
    app.inFlightSessionId = null;
    refreshComposerAvailability();
  }

  updateSessionTitle(session);
  saveState();

  if (app.activeId === sessionId) {
    renderChat();
  } else {
    renderSidebar();
  }
}

function connectSocket() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${window.location.host}/ws/chat`;
  app.ws = new WebSocket(url);

  app.ws.onopen = () => {
    setStatus(true);
    refreshComposerAvailability();
  };

  app.ws.onclose = () => {
    setStatus(false);
    refreshComposerAvailability();
    setTimeout(connectSocket, 1000);
  };

  app.ws.onerror = () => {
    setStatus(false);
    refreshComposerAvailability();
  };

  app.ws.onmessage = (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }

    if (msg.type === "token") {
      handleTokenEvent(msg);
      return;
    }

    if (msg.type === "complete") {
      finalizeAssistantMessage(msg.session_id, msg.data?.reply || "");
      return;
    }

    if (msg.type === "error") {
      const sid = msg.session_id || app.inFlightSessionId || app.activeId;
      if (sid) {
        finalizeAssistantMessage(sid, `Error: ${msg.data?.detail || "Unknown error"}`, true);
      }
    }
  };
}

function renderSidebar() {
  el.sessionList.innerHTML = "";
  app.sessions.forEach((s) => {
    const row = document.createElement("div");
    row.className = "session-row";

    const btn = document.createElement("button");
    btn.className = `session-item ${s.id === app.activeId ? "active" : ""}`;
    const preview = s.messages.length ? s.messages[s.messages.length - 1].content.slice(0, 26) : "No messages yet";
    btn.innerHTML = `<div class="session-title">${escapeHtml(s.title)}</div><div class="session-sub">${escapeHtml(preview)} • ${nowLabel(s.createdAt)}</div>`;
    btn.onclick = () => {
      app.activeId = s.id;
      saveState();
      render();
    };

    const del = document.createElement("button");
    del.className = "session-delete";
    del.textContent = "Delete";
    del.title = "Delete conversation";
    del.onclick = (e) => {
      e.stopPropagation();
      deleteSession(s.id);
    };

    row.appendChild(btn);
    row.appendChild(del);
    el.sessionList.appendChild(row);
  });
}

function createMessageRow(message) {
  const node = el.template.content.firstElementChild.cloneNode(true);
  node.classList.add(message.role === "user" ? "user" : "assistant");
  if (message.streaming && message.role === "assistant") node.classList.add("streaming");
  if (message.id) node.setAttribute("data-mid", message.id);
  node.querySelector(".bubble").textContent = message.content;
  return node;
}

function addSystemHint(text) {
  const row = createMessageRow({ id: uid("hint"), role: "assistant", content: text });
  el.chatWindow.appendChild(row);
}

function renderChat() {
  el.chatWindow.innerHTML = "";
  const session = currentSession();
  if (!session) return;

  if (!session.messages.length) {
    addSystemHint("Start a conversation. Streaming response is enabled.");
    return;
  }

  session.messages.forEach((m) => {
    el.chatWindow.appendChild(createMessageRow(m));
  });

  el.chatWindow.scrollTop = el.chatWindow.scrollHeight;
}

function render() {
  renderSidebar();
  renderChat();
  refreshComposerAvailability();
}

function sendChat(text) {
  const session = currentSession();
  if (!session || !app.connected || !app.ws || app.inFlightSessionId) return;

  const userMsg = { id: uid("m"), role: "user", content: text, ts: Date.now() };
  const botMsg = { id: uid("m"), role: "assistant", content: "", ts: Date.now(), streaming: true };

  session.messages.push(userMsg);
  session.messages.push(botMsg);
  app.pendingBySession[session.id] = botMsg.id;
  app.inFlightSessionId = session.id;

  updateSessionTitle(session);
  saveState();
  render();

  app.ws.send(
    JSON.stringify({
      type: "chat",
      session_id: session.id,
      message: text,
      stream: true,
    })
  );
}

function resetCurrentSession() {
  const session = currentSession();
  if (!session) return;

  if (app.inFlightSessionId === session.id) {
    app.inFlightSessionId = null;
  }
  delete app.pendingBySession[session.id];

  session.messages = [];
  session.title = "New conversation";

  if (app.connected && app.ws) {
    app.ws.send(JSON.stringify({ type: "reset", session_id: session.id }));
  }

  saveState();
  render();
}

async function sendVoice(audioBlob) {
  const session = currentSession();
  if (!session || !app.connected || app.inFlightSessionId) return;

  const userMsg = { id: uid("m"), role: "user", content: "[Voice message]", ts: Date.now() };
  const botMsg = { id: uid("m"), role: "assistant", content: "", ts: Date.now(), streaming: true };

  session.messages.push(userMsg);
  session.messages.push(botMsg);
  app.pendingBySession[session.id] = botMsg.id;
  app.inFlightSessionId = session.id;
  updateSessionTitle(session);
  saveState();
  render();

  const form = new FormData();
  const extension = app.voiceMimeType.includes("webm") ? "webm" : "wav";
  form.append("session_id", session.id);
  form.append("audio_extension", extension);
  form.append("audio", audioBlob, `voice.${extension}`);

  setVoiceStatus("Transcribing...");

  try {
    const resp = await fetch("/v1/voice/reply", {
      method: "POST",
      body: form,
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data?.detail || "Voice request failed");
    }

    userMsg.content = `[Voice] ${data.transcript || "(no transcript)"}`;
    const latency = ` (${data.total_ms}ms | ASR ${data.asr_ms}ms, LLM ${data.llm_ms}ms, TTS ${data.tts_ms}ms)`;
    finalizeAssistantMessage(session.id, `${data.reply}${latency}`);

    if (data.audio_base64) {
      const audioUrl = `data:audio/wav;base64,${data.audio_base64}`;
      const player = new Audio(audioUrl);
      await player.play().catch(() => {});
    }

    setVoiceStatus("Voice idle");
  } catch (err) {
    finalizeAssistantMessage(session.id, `Voice error: ${err.message || "Unknown error"}`, true);
    setVoiceStatus("Voice error");
  }
}

async function startVoiceCapture() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setVoiceStatus("Mic API not supported");
    return;
  }
  if (app.inFlightSessionId || app.mediaRecorder) return;

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    app.voiceChunks = [];
    const preferredType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";
    app.voiceMimeType = preferredType;
    app.mediaRecorder = new MediaRecorder(stream, { mimeType: app.voiceMimeType });

    app.mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        app.voiceChunks.push(event.data);
      }
    };

    app.mediaRecorder.onstop = async () => {
      const blob = new Blob(app.voiceChunks, { type: app.voiceMimeType });
      app.voiceChunks = [];
      app.mediaRecorder.stream.getTracks().forEach((t) => t.stop());
      app.mediaRecorder = null;
      el.recordBtn.disabled = false;
      el.stopBtn.disabled = true;
      await sendVoice(blob);
    };

    app.mediaRecorder.start();
    el.recordBtn.disabled = true;
    el.stopBtn.disabled = false;
    setVoiceStatus("Recording...");
  } catch {
    setVoiceStatus("Microphone permission denied");
  }
}

function stopVoiceCapture() {
  if (!app.mediaRecorder || app.mediaRecorder.state === "inactive") return;
  app.mediaRecorder.stop();
  setVoiceStatus("Processing...");
}

function autoGrow() {
  el.input.style.height = "auto";
  el.input.style.height = `${Math.min(el.input.scrollHeight, 160)}px`;
}

function escapeHtml(s) {
  return s.replace(/[&<>\"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

el.composer.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = el.input.value.trim();
  if (!text) return;
  sendChat(text);
  el.input.value = "";
  autoGrow();
});

el.input.addEventListener("input", autoGrow);
el.newBtn.addEventListener("click", () => createSession());
el.resetBtn.addEventListener("click", () => resetCurrentSession());
el.recordBtn.addEventListener("click", () => startVoiceCapture());
el.stopBtn.addEventListener("click", () => stopVoiceCapture());

loadState();
render();
connectSocket();
autoGrow();
setVoiceStatus("Voice idle");
