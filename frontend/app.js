/** API base:
 * - Khi mo qua uvicorn /app -> cung origin (/api).
 * - Khi mo bang static server frontend:8080 -> goi backend 127.0.0.1:8000.
 * - Co the override bang window.__API_BASE__ neu can.
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

/** Trạng thái tĩnh khi không tải / không lỗi (gọn, không lặp hướng dẫn bệnh nhân). */
const STATUS_IDLE = "Sẵn sàng";

const state = {
  patientId: null,
  conversationId: null,
  sending: false,
  conversations: [],
};

// Các phần dưới đây chỉ dành cho UI chat có form/selector riêng.
// Hiện tại landing page đang dùng layout khác, nên không khởi tạo nếu không tìm thấy phần tử.
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
    statusText.textContent = v ? "Đang soạn trả lời…" : STATUS_IDLE;
  }
}

/** Van ban thuan cho TTS (bo markdown **). */
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
  if (statusText) statusText.textContent = "Đang tạo giọng đọc…";
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
    if (statusText) statusText.textContent = "Không phát được TTS.";
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
  roleSpan.textContent = normRole === "user" ? "Bạn" : "Pasteur AI";
  meta.appendChild(roleSpan);
  if (createdAt) {
    const timeSpan = document.createElement("span");
    const dt = new Date(createdAt);
    timeSpan.textContent = dt.toLocaleTimeString("vi-VN", {
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
    ttsBtn.title = "Đọc bằng giọng nói (TTS)";
    ttsBtn.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 010 7.07"/><path d="M19.07 4.93a10 10 0 010 14.14"/></svg><span>Đọc</span>';
    ttsBtn.addEventListener("click", () => playTtsForText(content, ttsBtn));
    ttsRow.appendChild(ttsBtn);
    row.appendChild(ttsRow);
  }

  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
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
        : "Cuộc trò chuyện " + c.id.slice(0, 8);
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
    opt.textContent = "Chưa có bệnh nhân (tạo trong backend)";
    opt.disabled = true;
    opt.selected = true;
    patientSelect.appendChild(opt);
    state.patientId = null;
    return;
  }

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Chọn bệnh nhân";
  placeholder.disabled = true;
  placeholder.selected = true;
  patientSelect.appendChild(placeholder);

  for (const p of list) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = p.full_name || "Bệnh nhân " + p.id.slice(0, 5);
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

// Gửi message xuống backend (đặt tên khác để không đụng với sendMessage() trong index.html)
async function backendSendMessage(rawText) {
  const text = (rawText ?? "").toString().trim();
  if (!text) return;
   if (!state.patientId) {
    if (statusText) {
      statusText.textContent = "Chưa chọn bệnh nhân";
    }
    return;
  }
  setSending(true);
  const currentPatientId = state.patientId;
  const currentConvId = state.conversationId;
  if (messagesEl) appendMessage("user", text);
  try {
    const res = await api("/chat", {
      method: "POST",
      body: JSON.stringify({
        patient_id: currentPatientId,
        conversation_id: currentConvId,
        message: text,
      }),
    });
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
    if (messagesEl && state.patientId === currentPatientId) {
      appendMessage(
        "assistant",
        "Xin lỗi, đã có lỗi khi gọi Gemini. Vui lòng thử lại sau."
      );
    }
  } finally {
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
            "Mic/STT cần HTTPS hoặc localhost — mở qua http://127.0.0.1:8000/static/...";
        }
      }
    } catch (err) {
      console.error(err);
      if (statusText) {
        statusText.textContent = "Không kết nối được API backend.";
      }
    }
  })();
}

// —— STT/TTS: ghi âm -> POST /api/chat/audio ——
let voiceRecorder = null;
let voiceChunks = [];
let voiceStream = null;

async function backendSendAudio(blob) {
  if (!state.patientId) {
    if (statusText) statusText.textContent = "Chưa chọn bệnh nhân";
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
    if (statusText) statusText.textContent = "Bản ghi quá ngắn, hãy nói lâu hơn một chút.";
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
        "Không xử lý được ghi âm (STT/TTS). Kiểm tra microphone, HTTPS/localhost, và API backend."
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
    if (statusText) statusText.textContent = "Chưa chọn bệnh nhân";
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    if (statusText) {
      statusText.textContent =
        "Không truy cập được microphone (cần HTTPS hoặc localhost, không mở file://).";
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
    if (statusText) statusText.textContent = "Đang ghi… nhấn mic lần nữa để gửi.";
  } catch (e) {
    console.error(e);
    if (statusText) statusText.textContent = "Không mở được microphone.";
  }
}

// Gan su kien sau khi script load (tranh loi onclick inline khong thay ham global)
const micBtnEl = document.getElementById("micBtn");
if (micBtnEl) {
  micBtnEl.addEventListener("click", () => {
    toggleVoiceRecord();
  });
}

