/** API base:
 * - Served via uvicorn /app -> same origin (/api).
 * - Static frontend on :8080 -> backend http://127.0.0.1:8000/api.
 * - Override with window.__API_BASE__ if needed.
 */
function resolveApiBase() {
  if (typeof window.__API_BASE__ === "string" && window.__API_BASE__.trim()) {
    return window.__API_BASE__.replace(/\/+$/, "");
  }
  const isHttp =
    window.location.protocol === "http:" || window.location.protocol === "https:";
  if (!isHttp) return "http://127.0.0.1:8000/api";

  const isLocalHost =
    window.location.hostname === "127.0.0.1" ||
    window.location.hostname === "localhost" ||
    window.location.hostname === "::1";
  if (isLocalHost && window.location.port === "8080") {
    return "http://127.0.0.1:8000/api";
  }
  return `${window.location.origin}/api`;
}

const API_BASE = resolveApiBase();

/** Idle status when not loading / no error. */
const STATUS_IDLE = "Ready";

const state = {
  patientId: null,
  conversationId: null,
  sending: false,
  conversations: [],
};

// Chat UI with separate form/selector — skip init if elements are missing.
const patientSelect = document.getElementById("patient-select");
const messagesEl = document.getElementById("messages");
const welcomeScreen = document.getElementById("welcomeScreen");
const convListEl = document.getElementById("convList");
if (convListEl) {
  convListEl.addEventListener("click", (e) => {
    if (!e.target.closest(".conv-item")) return;
    if (window.matchMedia("(max-width: 720px)").matches) {
      document.body.classList.remove("conv-drawer-open");
    }
  });
}
const formEl = document.getElementById("chat-form");
const promptEl = document.getElementById("prompt");
const sendBtn = document.getElementById("sendBtn");
const statusText =
  document.getElementById("status-text") ||
  document.querySelector(".topbar-status");

async function api(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

function setSending(v) {
  state.sending = v;
  if (sendBtn) sendBtn.disabled = v;
  if (statusText) {
    statusText.textContent = v ? "Composing reply…" : STATUS_IDLE;
  }
}

/** Plain text for TTS (strip markdown **). */
function stripForTts(raw) {
  return (raw ?? "")
    .toString()
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\n+/g, " ")
    .trim();
}

async function playTtsForText(text, buttonEl) {
  const t = stripForTts(text);
  if (!t) return;
  if (buttonEl) {
    buttonEl.disabled = true;
  }
  if (statusText) statusText.textContent = "Generating speech…";
  try {
    const voice =
      (document.getElementById("tts-voice-select") || {}).value || null;
    const res = await fetch(`${API_BASE}/chat/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: t, voice: voice || null }),
    });
    const errText = await res.text();
    if (!res.ok) throw new Error(errText || res.statusText);
    const data = JSON.parse(errText);
    if (data.audio_base64 && data.audio_mime) {
      const url = `data:${data.audio_mime};base64,${data.audio_base64}`;
      const a = new Audio(url);
      a.play();
    }
  } catch (e) {
    console.error(e);
    if (statusText) statusText.textContent = "Could not play TTS.";
  } finally {
    if (buttonEl) buttonEl.disabled = false;
    if (statusText) statusText.textContent = STATUS_IDLE;
  }
}

function renderMessageContent(raw) {
  const text = (raw ?? "").toString();
  let safe = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  // Bold **...**
  safe = safe.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  const paragraphs = safe.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
  if (!paragraphs.length) return "";
  return paragraphs
    .map((p) => p.replace(/\n/g, "<br/>"))
    .map((p) => {
      return `<p>${p}</p>`;
    })
    .join("");
}

function appendMessage(role, content, createdAt) {
  if (!messagesEl) return;
  const normRole = role === "user" ? "user" : "assistant";
  const row = document.createElement("div");
  row.className = `message-row ${normRole}`;
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";

  const meta = document.createElement("div");
  meta.className = "message-meta";
  const roleSpan = document.createElement("span");
  roleSpan.className = "message-role";
  roleSpan.textContent = normRole === "user" ? "You" : "Pasteur AI";
  meta.appendChild(roleSpan);
  if (createdAt) {
    const timeSpan = document.createElement("span");
    const dt = new Date(createdAt);
    timeSpan.textContent = dt.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
    });
    meta.appendChild(timeSpan);
  }

  const body = document.createElement("div");
  body.innerHTML = renderMessageContent(content);

  bubble.appendChild(meta);
  bubble.appendChild(body);
  row.appendChild(bubble);

  if (normRole === "assistant") {
    const ttsRow = document.createElement("div");
    ttsRow.className = "message-tts-row";
    const ttsBtn = document.createElement("button");
    ttsBtn.type = "button";
    ttsBtn.className = "msg-tts-btn";
    ttsBtn.title = "Read aloud (TTS)";
    ttsBtn.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 010 7.07"/><path d="M19.07 4.93a10 10 0 010 14.14"/></svg><span>Listen</span>';
    ttsBtn.addEventListener("click", () => playTtsForText(content, ttsBtn));
    ttsRow.appendChild(ttsBtn);
    row.appendChild(ttsRow);
  }

  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/** Same structure/CSS as the inline typing row in index — must appear after the user bubble. */
function createTypingIndicator() {
  const row = document.createElement("div");
  row.className = "typing-row";
  const lbl = document.createElement("div");
  lbl.className = "typing-label";
  lbl.textContent = "Pasteur AI";
  const inner = document.createElement("div");
  inner.className = "typing-inner";
  const lw = document.createElement("div");
  lw.className = "typing-logo-wrap";
  const img = document.createElement("img");
  img.src = "assets/logo.svg";
  img.alt = "Pasteur AI Logo";
  lw.appendChild(img);
  const dots = document.createElement("div");
  dots.className = "dots";
  for (let i = 0; i < 3; i++) {
    const d = document.createElement("div");
    d.className = "dot";
    dots.appendChild(d);
  }
  inner.appendChild(lw);
  inner.appendChild(dots);
  row.appendChild(lbl);
  row.appendChild(inner);
  return row;
}

function renderConversationList(conversations) {
  if (!convListEl) return;
  convListEl.innerHTML = "";
  for (const c of conversations) {
    const item = document.createElement("div");
    item.className = "conv-item";
    if (c.id === state.conversationId) {
      item.classList.add("active");
    }
    const label =
      c.title && c.title.trim()
        ? c.title
        : "Conversation " + c.id.slice(0, 8);
    item.textContent = label;
    item.onclick = async () => {
      if (state.conversationId === c.id) return;
      const requestedConvId = c.id;
      state.conversationId = requestedConvId;
      document.querySelectorAll(".conv-item").forEach((el) =>
        el.classList.remove("active")
      );
      item.classList.add("active");
      try {
        const detail = await api(`/conversations/${encodeURIComponent(requestedConvId)}`);
        if (state.conversationId !== requestedConvId) return;
        renderConversation(detail.messages || []);
        showMessagesView();
      } catch (err) {
        console.error(err);
        if (state.conversationId === requestedConvId) state.conversationId = null;
      }
    };
    convListEl.appendChild(item);
  }
}

function renderConversation(messages) {
  if (!messagesEl) return;
  messagesEl.innerHTML = "";
  const list = Array.isArray(messages) ? messages : [];
  for (const m of list) {
    const r = (m.role || "").toString().toLowerCase();
    if (r === "system") continue;
    appendMessage(r === "user" ? "user" : "assistant", m.content, m.created_at);
  }
}

async function loadPatients() {
  if (!patientSelect) return;
  const list = await api("/patients");
  patientSelect.innerHTML = "";

  if (!list.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No patients yet (create in backend)";
    opt.disabled = true;
    opt.selected = true;
    patientSelect.appendChild(opt);
    state.patientId = null;
    return;
  }

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select patient";
  placeholder.disabled = true;
  placeholder.selected = true;
  patientSelect.appendChild(placeholder);

  for (const p of list) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = p.full_name || "Patient " + p.id.slice(0, 5);
    patientSelect.appendChild(opt);
  }

  state.patientId = null;
}

function showMessagesView() {
  if (welcomeScreen) welcomeScreen.style.display = "none";
  if (messagesEl) messagesEl.style.display = "flex";
}

async function loadConversationsForPatient() {
  if (!state.patientId) return;
  const currentPatientId = state.patientId;
  const convs = await api(`/conversations?patient_id=${encodeURIComponent(currentPatientId)}`);
  if (state.patientId !== currentPatientId) return;
  state.conversations = convs;
  renderConversationList(convs);
  // Always start a new conversation when selecting a patient.
  state.conversationId = null;
  if (messagesEl) {
    messagesEl.innerHTML = "";
    messagesEl.style.display = "none";
  }
  if (welcomeScreen) welcomeScreen.style.display = "flex";
}

window.chatResetConversation = function () {
  state.conversationId = null;
  if (messagesEl) {
    messagesEl.innerHTML = "";
    messagesEl.style.display = "none";
  }
  if (welcomeScreen) welcomeScreen.style.display = "flex";
  renderConversationList(state.conversations);
};

// Send message to backend (named separately from sendMessage() in index.html)
async function backendSendMessage(rawText) {
  const text = (rawText ?? "").toString().trim();
  if (!text) return;
   if (!state.patientId) {
    if (statusText) {
      statusText.textContent = "No patient selected";
    }
    return;
  }
  setSending(true);
  const currentPatientId = state.patientId;
  const currentConvId = state.conversationId;
  let typingEl = null;
  if (messagesEl) appendMessage("user", text);
  if (messagesEl) {
    typingEl = createTypingIndicator();
    messagesEl.appendChild(typingEl);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
  try {
    const res = await api("/chat", {
      method: "POST",
      body: JSON.stringify({
        patient_id: currentPatientId,
        conversation_id: currentConvId,
        message: text,
      }),
    });
    if (typingEl?.parentNode) typingEl.remove();
    typingEl = null;
    if (state.patientId !== currentPatientId) return;
    state.conversationId = res.conversation_id;
    if (Array.isArray(res.conversations)) {
      state.conversations = res.conversations;
      renderConversationList(state.conversations);
    } else {
      try {
        const convs = await api(
          `/conversations?patient_id=${encodeURIComponent(state.patientId)}`
        );
        state.conversations = convs;
        renderConversationList(convs);
      } catch (e) {
        console.error(e);
      }
    }
    renderConversation(res.messages || []);
  } catch (err) {
    console.error(err);
    if (typingEl?.parentNode) typingEl.remove();
    typingEl = null;
    if (messagesEl && state.patientId === currentPatientId) {
      appendMessage(
        "assistant",
        "Sorry, something went wrong calling Gemini. Please try again later."
      );
    }
  } finally {
    if (typingEl?.parentNode) typingEl.remove();
    setSending(false);
  }
}

if (formEl && promptEl) {
  formEl.addEventListener("submit", (e) => {
    e.preventDefault();
    const value = promptEl.value;
    if (!value.trim() || state.sending) return;
    promptEl.value = "";
    backendSendMessage(value);
  });

  promptEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      formEl.requestSubmit();
    }
  });
}

if (patientSelect) {
  patientSelect.addEventListener("change", async (e) => {
    const value = e.target.value;
    if (!value) {
      state.patientId = null;
      state.conversationId = null;
      state.conversations = [];
      renderConversationList([]);
      if (messagesEl) { messagesEl.innerHTML = ""; messagesEl.style.display = "none"; }
      if (welcomeScreen) welcomeScreen.style.display = "flex";
      if (statusText) statusText.textContent = STATUS_IDLE;
      return;
    }
    state.patientId = value;
    state.conversationId = null;
    state.conversations = [];
    renderConversationList([]);
    if (messagesEl) { messagesEl.innerHTML = ""; }
    if (welcomeScreen) welcomeScreen.style.display = "flex";
    if (messagesEl) messagesEl.style.display = "none";
    try {
      await loadConversationsForPatient();
    } catch (err) {
      console.error(err);
    }
  });
}

async function loadTtsVoices() {
  const sel = document.getElementById("tts-voice-select");
  if (!sel) return;
  try {
    const res = await fetch(`${API_BASE}/chat/tts/voices`);
    if (!res.ok) return;
    const voices = await res.json();
    if (!Array.isArray(voices) || !voices.length) return;
    const current = sel.value;
    sel.innerHTML = "";
    for (const v of voices) {
      const opt = document.createElement("option");
      opt.value = v.id;
      opt.textContent = v.label || v.id;
      sel.appendChild(opt);
    }
    if (current && [...sel.options].some((o) => o.value === current)) {
      sel.value = current;
    }
  } catch (e) {
    console.warn("loadTtsVoices", e);
  }
}

if (patientSelect) {
  (async function init() {
    try {
      await Promise.all([loadPatients(), loadTtsVoices()]);
      if (statusText) {
        statusText.textContent = STATUS_IDLE;
      }
      if (!window.isSecureContext && !/^localhost$|^127\./.test(location.hostname)) {
        if (statusText) {
          statusText.textContent =
            "Mic/STT needs HTTPS or localhost — open via http://127.0.0.1:8000/static/...";
        }
      }
    } catch (err) {
      console.error(err);
      if (statusText) {
        statusText.textContent = "Could not reach the API backend.";
      }
    }
  })();
}

// —— STT/TTS: recording -> POST /api/chat/audio ——
let voiceRecorder = null;
let voiceChunks = [];
let voiceStream = null;

async function backendSendAudio(blob) {
  if (!state.patientId) {
    if (statusText) statusText.textContent = "No patient selected";
    return;
  }
  const welcome = document.getElementById("welcomeScreen");
  const msgs = document.getElementById("messages");
  if (welcome && welcome.style.display !== "none") {
    welcome.style.display = "none";
    if (msgs) msgs.style.display = "flex";
  }
  setSending(true);
  const fd = new FormData();
  fd.append("patient_id", state.patientId);
  if (state.conversationId) fd.append("conversation_id", state.conversationId);
  fd.append("audio", blob, "recording.webm");
  const voiceSel = document.getElementById("tts-voice-select");
  if (voiceSel && voiceSel.value) {
    fd.append("tts_voice", voiceSel.value);
  }
  if (!blob || blob.size < 16) {
    if (statusText) statusText.textContent = "Recording too short — speak a bit longer.";
    setSending(false);
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/chat/audio`, { method: "POST", body: fd });
    const text = await res.text();
    if (!res.ok) throw new Error(text || res.statusText);
    const data = JSON.parse(text);
    state.conversationId = data.conversation_id;
    try {
      const convs = await api(
        `/conversations?patient_id=${encodeURIComponent(state.patientId)}`
      );
      state.conversations = convs;
      renderConversationList(convs);
    } catch (e) {
      console.error(e);
    }
    renderConversation(data.messages || []);
    if (data.audio_base64 && data.audio_mime) {
      try {
        const url = `data:${data.audio_mime};base64,${data.audio_base64}`;
        new Audio(url).play();
      } catch (e) {
        console.warn("TTS play", e);
      }
    }
  } catch (err) {
    console.error(err);
    if (messagesEl) {
      appendMessage(
        "assistant",
        "Could not process voice input (STT/TTS). Check microphone, HTTPS/localhost, and the API backend."
      );
    }
  } finally {
    setSending(false);
    if (statusText) statusText.textContent = STATUS_IDLE;
  }
}

async function toggleVoiceRecord() {
  const micBtn = document.getElementById("micBtn");
  if (voiceRecorder && voiceRecorder.state === "recording") {
    voiceRecorder.stop();
    return;
  }
  if (!state.patientId) {
    if (statusText) statusText.textContent = "No patient selected";
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    if (statusText) {
      statusText.textContent =
        "Microphone unavailable (use HTTPS or localhost, not file://).";
    }
    return;
  }
  try {
    voiceStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";
    voiceRecorder = mime
      ? new MediaRecorder(voiceStream, { mimeType: mime })
      : new MediaRecorder(voiceStream);
    voiceChunks = [];
    voiceRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size) voiceChunks.push(e.data);
    };
    voiceRecorder.onstop = async () => {
      voiceStream.getTracks().forEach((t) => t.stop());
      voiceStream = null;
      if (micBtn) micBtn.classList.remove("recording");
      const blob = new Blob(voiceChunks, {
        type: voiceRecorder.mimeType || "audio/webm",
      });
      voiceRecorder = null;
      voiceChunks = [];
      await backendSendAudio(blob);
    };
    voiceRecorder.start(250);
    if (micBtn) micBtn.classList.add("recording");
    if (statusText) statusText.textContent = "Recording… tap the mic again to send.";
  } catch (e) {
    console.error(e);
    if (statusText) statusText.textContent = "Could not open microphone.";
  }
}

// Bind after load (inline onclick may not see globals)
const micBtnEl = document.getElementById("micBtn");
if (micBtnEl) {
  micBtnEl.addEventListener("click", () => {
    toggleVoiceRecord();
  });
}

