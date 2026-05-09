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
const STATUS_IDLE = "Sẵn sàng";

const state = {
  patientId: null,
  conversationId: null,
  sending: false,
  conversations: [],
  renderedConversationCount: 0,
  voiceSending: false,
  recording: false,
  activeAudioRequestId: 0,
  activeTtsPlaybackId: 0,
  ttsPlaying: false,
  activeTtsButton: null,
  activeTtsAbortController: null,
  audioPrimed: false,
  showAssistantTextPreview: false,
};

// Chat UI with separate form/selector — skip init if elements are missing.
const patientSelect = document.getElementById("patient-select");
const welcomePatientSelect = document.getElementById("welcome-patient-select");
const welcomeStartBtn = document.getElementById("welcome-start-chat-btn");
const welcomePatientHint = document.getElementById("welcome-patient-hint");
const messagesEl = document.getElementById("messages");
const welcomeScreen = document.getElementById("welcomeScreen");
const convListEl = document.getElementById("convList");
const CONVERSATION_PAGE_SIZE = 12;

function shouldLoadMoreConversations() {
  if (!convListEl) return false;
  return convListEl.scrollTop + convListEl.clientHeight >= convListEl.scrollHeight - 24;
}

function loadMoreConversations() {
  if (!Array.isArray(state.conversations) || state.renderedConversationCount >= state.conversations.length) {
    return;
  }
  state.renderedConversationCount = Math.min(
    state.renderedConversationCount + CONVERSATION_PAGE_SIZE,
    state.conversations.length
  );
  renderConversationList(state.conversations);
}

if (convListEl) {
  convListEl.addEventListener("scroll", () => {
    if (shouldLoadMoreConversations()) loadMoreConversations();
  });
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
const assistantTextToggle = document.getElementById("assistant-text-toggle");
const ASSISTANT_TEXT_PREVIEW_KEY = "pasteur-assistant-text-preview";
const sidebarLogoEl = document.querySelector(".sidebar-logo");
const topbarBrandEl = document.querySelector(".topbar-brand");

function goToHomeScreen() {
  if (typeof window.startNewChat === "function") {
    window.startNewChat();
    return;
  }
  // Fallback if inline helper is unavailable.
  state.conversationId = null;
  if (messagesEl) {
    messagesEl.innerHTML = "";
    messagesEl.style.display = "none";
  }
  if (welcomeScreen) welcomeScreen.style.display = "flex";
  renderConversationList(state.conversations || []);
}

function getAssistantTextPreview(content) {
  const clean = stripForTts(content);
  if (!clean) return "Đã tạo câu trả lời bằng giọng nói.";
  const firstSentence = clean.split(/[.!?]\s+/).filter(Boolean)[0] || clean;
  const preview = firstSentence.trim();
  if (preview.length <= 110) return preview;
  return preview.slice(0, 110).trim() + "...";
}

function applyAssistantTextPreviewUi() {
  if (!assistantTextToggle) return;
  assistantTextToggle.checked = !!state.showAssistantTextPreview;
}

function parseFastApiErrorBody(rawText) {
  const fallback = (rawText || "").trim();
  if (!fallback) return "";
  try {
    const j = JSON.parse(fallback);
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail))
      return j.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  } catch (_) {}
  return fallback;
}

async function api(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(parseFastApiErrorBody(text) || res.statusText);
  }
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch (_) {
    return {};
  }
}

function setSending(v) {
  state.sending = v;
  if (sendBtn) sendBtn.disabled = v;
  if (statusText) {
    // Keep topbar status stable; typing UI is shown in message list.
    statusText.textContent = STATUS_IDLE;
  }
}

function showStatusTemp(message, timeoutMs = 8000) {
  if (!statusText) return;
  statusText.textContent = message;
  window.clearTimeout(state.__statusResetTimer);
  state.__statusResetTimer = window.setTimeout(() => {
    if (!state.sending && !state.voiceSending && !state.recording) {
      statusText.textContent = STATUS_IDLE;
    }
  }, timeoutMs);
}

/** Van ban thuan cho TTS (bo markdown **). */
function stripForTts(raw) {
  return (raw ?? "")
    .toString()
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\n+/g, " ")
    .trim();
}

function stopActiveAudio() {
  if (!window.__pasteurAudioPlayer) return;
  try {
    window.__pasteurAudioPlayer.pause();
  } catch (_) {}
  const prevUrl = window.__pasteurAudioPlayer.__blobUrl;
  if (prevUrl) {
    try {
      URL.revokeObjectURL(prevUrl);
    } catch (_) {}
  }
  try {
    window.__pasteurAudioPlayer.currentTime = 0;
  } catch (_) {}
}

function setTtsButtonUi(buttonEl, isPlaying) {
  if (!buttonEl) return;
  buttonEl.innerHTML = isPlaying
    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="6" width="12" height="12"/></svg><span>Dừng</span>'
    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 010 7.07"/><path d="M19.07 4.93a10 10 0 010 14.14"/></svg><span>Nghe</span>';
}

function stopTtsPlayback(reason = "user_stop") {
  state.activeTtsPlaybackId += 1;
  state.ttsPlaying = false;
  const prevBtn = state.activeTtsButton;
  state.activeTtsButton = null;
  if (prevBtn) setTtsButtonUi(prevBtn, false);
  if (state.activeTtsAbortController) {
    try {
      state.activeTtsAbortController.abort();
    } catch (_) {}
    state.activeTtsAbortController = null;
  }
  stopActiveAudio();
  if (statusText && reason === "user_stop") statusText.textContent = STATUS_IDLE;
}

function isExpectedPlayInterrupt(err) {
  if (!err) return false;
  return err.name === "AbortError";
}

function isAutoplayBlockedError(err) {
  if (!err) return false;
  return err.name === "NotAllowedError";
}

function waitForPlaybackEnded(player, playbackId) {
  return new Promise((resolve, reject) => {
    if (!player) {
      resolve();
      return;
    }
    const onEnded = () => {
      cleanup();
      resolve();
    };
    const onError = () => {
      cleanup();
      reject(new Error("Audio playback error"));
    };
    const onAbortLike = () => {
      if (playbackId !== state.activeTtsPlaybackId) {
        cleanup();
        const e = new Error("Playback aborted");
        e.name = "AbortError";
        reject(e);
      }
    };
    const cleanup = () => {
      player.removeEventListener("ended", onEnded);
      player.removeEventListener("error", onError);
      player.removeEventListener("pause", onAbortLike);
    };
    player.addEventListener("ended", onEnded, { once: true });
    player.addEventListener("error", onError, { once: true });
    player.addEventListener("pause", onAbortLike);
  });
}

function primeAudioOutputFromGesture() {
  if (state.audioPrimed) return;
  try {
    const a = new Audio();
    a.muted = true;
    const p = a.play();
    if (p && typeof p.then === "function") {
      p.then(() => {
        a.pause();
        state.audioPrimed = true;
      }).catch(() => {});
    } else {
      state.audioPrimed = true;
    }
  } catch (_) {}
}

async function playAudioFromBlob(blob, playbackId) {
  console.info("[TTS] playAudioFromBlob", {
    size: blob?.size || 0,
    type: blob?.type || "unknown",
    playbackId,
  });
  const url = URL.createObjectURL(blob);
  stopActiveAudio();
  const player = new Audio(url);
  player.__blobUrl = url;
  player.addEventListener("error", () => {
    const mediaError = player.error;
    console.error("[TTS] audio element error", {
      playbackId,
      code: mediaError?.code,
      message: mediaError?.message || "unknown",
    });
  });
  window.__pasteurAudioPlayer = player;
  try {
    await player.play();
  } catch (err) {
    if (isExpectedPlayInterrupt(err) || playbackId !== state.activeTtsPlaybackId) return;
    throw err;
  }
  console.info("[TTS] blob playback started", { playbackId });
  await waitForPlaybackEnded(player, playbackId);
}

function canStreamMp3WithMediaSource() {
  if (typeof window === "undefined") return false;
  if (!("MediaSource" in window)) return false;
  if (typeof MediaSource.isTypeSupported !== "function") return false;
  return (
    MediaSource.isTypeSupported("audio/mpeg") ||
    MediaSource.isTypeSupported("audio/mp3") ||
    MediaSource.isTypeSupported("audio/mpeg; codecs=\"mp3\"")
  );
}

async function playAudioFromReadableStreamViaMse(res, playbackId) {
  const mediaSource = new MediaSource();
  const streamUrl = URL.createObjectURL(mediaSource);
  stopActiveAudio();

  const player = new Audio(streamUrl);
  player.__blobUrl = streamUrl;
  window.__pasteurAudioPlayer = player;

  const mimeType = MediaSource.isTypeSupported("audio/mpeg")
    ? "audio/mpeg"
    : MediaSource.isTypeSupported("audio/mp3")
      ? "audio/mp3"
      : "audio/mpeg; codecs=\"mp3\"";

  const reader = res.body.getReader();

  await new Promise((resolve, reject) => {
    mediaSource.addEventListener(
      "sourceopen",
      () => {
        let sourceBuffer;
        let appending = false;
        let streamDone = false;
        const pendingChunks = [];

        const flushQueue = () => {
          if (!sourceBuffer || appending || sourceBuffer.updating) return;
          if (!pendingChunks.length) {
            if (streamDone && mediaSource.readyState === "open") {
              try {
                mediaSource.endOfStream();
              } catch (_) {}
              resolve();
            }
            return;
          }
          appending = true;
          const next = pendingChunks.shift();
          try {
            sourceBuffer.appendBuffer(next);
          } catch (err) {
            reject(err);
          }
        };

        try {
          sourceBuffer = mediaSource.addSourceBuffer(mimeType);
          sourceBuffer.mode = "sequence";
        } catch (err) {
          reject(err);
          return;
        }

        sourceBuffer.addEventListener("updateend", () => {
          appending = false;
          flushQueue();
        });
        sourceBuffer.addEventListener("error", () => {
          reject(new Error("SourceBuffer error"));
        });

        player
          .play()
          .catch((err) => {
            if (!isExpectedPlayInterrupt(err)) reject(err);
          });

        const pump = async () => {
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              streamDone = true;
              flushQueue();
              break;
            }
            if (playbackId !== state.activeTtsPlaybackId) {
              try {
                await reader.cancel();
              } catch (_) {}
              resolve();
              break;
            }
            if (value && value.byteLength) {
              pendingChunks.push(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength));
              flushQueue();
            }
          }
        };

        pump().catch(reject);
      },
      { once: true }
    );
  });

  console.info("[TTS] MSE stream playback started", { playbackId, mimeType });
  await waitForPlaybackEnded(player, playbackId);
}

async function playAudioFromReadableStream(res, playbackId, mimeType = "audio/mpeg") {
  const canStream = canStreamMp3WithMediaSource() && !!res.body;
  console.info("[TTS] stream mode", { canStream, mimeType, playbackId });
  if (canStream) {
    try {
      await playAudioFromReadableStreamViaMse(res, playbackId);
      return;
    } catch (streamErr) {
      console.warn("[TTS] MSE stream failed, fallback to blob", streamErr);
    }
  }
  const blob = await res.blob();
  console.info("[TTS] stream -> blob", { size: blob?.size || 0, type: blob?.type || "unknown", playbackId });
  if (!blob || blob.size === 0) throw new Error("Audio stream trả về rỗng");
  await playAudioFromBlob(blob, playbackId);
}

async function fetchTtsBlobFallback(text, voice) {
  const res = await fetch(`${API_BASE}/chat/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice: voice || null }),
  });
  const raw = await res.text();
  if (!res.ok) {
    throw new Error(raw || res.statusText);
  }
  let data = {};
  try {
    data = JSON.parse(raw);
  } catch (_) {
    throw new Error("Phản hồi fallback TTS không hợp lệ.");
  }
  if (!data.audio_base64 || !data.audio_mime) {
    throw new Error("Fallback TTS không có dữ liệu audio.");
  }
  const b64 = data.audio_base64;
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Blob([bytes], { type: data.audio_mime || "audio/mpeg" });
}

async function playTtsStream(text, voice) {
  const playbackId = ++state.activeTtsPlaybackId;
  const abortController = new AbortController();
  state.activeTtsAbortController = abortController;
  console.info("[TTS] request stream", {
    playbackId,
    voice: voice || "default",
    textLen: (text || "").length,
  });
  try {
    const res = await fetch(`${API_BASE}/chat/tts/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice: voice || null }),
      signal: abortController.signal,
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(errText || res.statusText);
    }
    console.info("[TTS] stream response", {
      playbackId,
      status: res.status,
      contentType: res.headers.get("content-type"),
    });
    await playAudioFromReadableStream(res, playbackId, "audio/mpeg");
  } catch (err) {
    if (isExpectedPlayInterrupt(err) || isAutoplayBlockedError(err)) {
      throw err;
    }
    console.warn("[TTS] stream failed, trying /chat/tts fallback", err);
    const fallbackBlob = await fetchTtsBlobFallback(text, voice);
    if (playbackId !== state.activeTtsPlaybackId) return;
    await playAudioFromBlob(fallbackBlob, playbackId);
  } finally {
    if (state.activeTtsAbortController === abortController) {
      state.activeTtsAbortController = null;
    }
  }
}

async function playTtsForText(text, buttonEl) {
  primeAudioOutputFromGesture();
  const t = stripForTts(text);
  if (!t) return;
  if (state.ttsPlaying && state.activeTtsButton === buttonEl) {
    stopTtsPlayback("user_stop");
    return;
  }
  if (state.ttsPlaying) stopTtsPlayback("switch_track");
  state.ttsPlaying = true;
  state.activeTtsButton = buttonEl || null;
  if (buttonEl) setTtsButtonUi(buttonEl, true);
  if (statusText) statusText.textContent = "Đang tạo giọng đọc…";
  try {
    const voice =
      (document.getElementById("tts-voice-select") || {}).value || null;
    await playTtsStream(t, voice);
  } catch (e) {
    console.error("[TTS] playTtsForText failed", e);
    if (statusText) {
      statusText.textContent = isAutoplayBlockedError(e)
        ? "Trình duyệt đang chặn phát loa tự động. Hãy bật quyền Sound/Autoplay cho trang."
        : "Không phát được TTS.";
    }
  } finally {
    const stillThisPlayback = state.activeTtsButton === buttonEl;
    state.ttsPlaying = false;
    state.activeTtsButton = null;
    if (stillThisPlayback && buttonEl) setTtsButtonUi(buttonEl, false);
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
  // Always render full assistant text to avoid hidden/truncated responses.
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
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 010 7.07"/><path d="M19.07 4.93a10 10 0 010 14.14"/></svg><span>Nghe</span>';
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
  const list = Array.isArray(conversations) ? conversations : [];
  const hasActiveConversation = list.some((c) => c.id === state.conversationId);
  if (hasActiveConversation) {
    const activeIndex = list.findIndex((c) => c.id === state.conversationId);
    const requiredVisibleCount = activeIndex + 1;
    state.renderedConversationCount = Math.max(
      state.renderedConversationCount || CONVERSATION_PAGE_SIZE,
      requiredVisibleCount
    );
  } else if (!state.renderedConversationCount) {
    state.renderedConversationCount = CONVERSATION_PAGE_SIZE;
  }
  const visibleCount = Math.min(state.renderedConversationCount, list.length);
  convListEl.innerHTML = "";
  for (const c of list.slice(0, visibleCount)) {
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
  const list = Array.isArray(messages) ? [...messages] : [];
  // Backend relation order có thể không ổn định tuyệt đối; ép thứ tự hiển thị theo thời gian.
  list.sort((a, b) => {
    const ta = a?.created_at ? Date.parse(a.created_at) : 0;
    const tb = b?.created_at ? Date.parse(b.created_at) : 0;
    if (ta !== tb) return ta - tb;

    const ra = (a?.role || "").toString().toLowerCase();
    const rb = (b?.role || "").toString().toLowerCase();
    if (ra !== rb) {
      if (ra === "user") return -1;
      if (rb === "user") return 1;
    }

    const ia = (a?.id || "").toString();
    const ib = (b?.id || "").toString();
    return ia.localeCompare(ib);
  });
  for (const m of list) {
    const r = (m.role || "").toString().toLowerCase();
    if (r === "system") continue;
    appendMessage(r === "user" ? "user" : "assistant", m.content, m.created_at);
  }
}

function syncPatientSelectUi(patientId) {
  const value = patientId || "";
  if (patientSelect && patientSelect.value !== value) patientSelect.value = value;
  if (welcomePatientSelect && welcomePatientSelect.value !== value) {
    welcomePatientSelect.value = value;
  }
  if (welcomeStartBtn) welcomeStartBtn.disabled = !value;
}

async function activatePatient(patientId) {
  const value = (patientId || "").toString().trim();
  if (!value) {
    state.patientId = null;
    state.conversationId = null;
    state.conversations = [];
    state.renderedConversationCount = CONVERSATION_PAGE_SIZE;
    renderConversationList([]);
    if (messagesEl) {
      messagesEl.innerHTML = "";
      messagesEl.style.display = "none";
    }
    if (welcomeScreen) welcomeScreen.style.display = "flex";
    if (statusText) statusText.textContent = "Hãy chọn hồ sơ bệnh nhân để bắt đầu.";
    syncPatientSelectUi("");
    return;
  }

  state.patientId = value;
  state.conversationId = null;
  state.conversations = [];
  state.renderedConversationCount = CONVERSATION_PAGE_SIZE;
  renderConversationList([]);
  if (messagesEl) {
    messagesEl.innerHTML = "";
    messagesEl.style.display = "none";
  }
  if (welcomeScreen) welcomeScreen.style.display = "flex";
  syncPatientSelectUi(value);
  if (statusText) statusText.textContent = "Đang tải lịch sử hội thoại…";

  try {
    await loadConversationsForPatient();
    if (statusText) statusText.textContent = STATUS_IDLE;
  } catch (err) {
    console.error(err);
    if (statusText) statusText.textContent = "Không tải được lịch sử hội thoại.";
  }
}

async function loadPatients() {
  if (!patientSelect) return;
  const list = await api("/patients");
  patientSelect.innerHTML = "";
  if (welcomePatientSelect) welcomePatientSelect.innerHTML = "";

  if (!list.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "Chưa có hồ sơ bệnh nhân";
    opt.disabled = true;
    opt.selected = true;
    patientSelect.appendChild(opt);
    if (welcomePatientSelect) {
      const wOpt = opt.cloneNode(true);
      welcomePatientSelect.appendChild(wOpt);
      welcomePatientSelect.disabled = true;
    }
    if (welcomeStartBtn) welcomeStartBtn.disabled = true;
    if (welcomePatientHint) {
      welcomePatientHint.textContent = "Vui lòng tạo bệnh nhân ở backend trước khi chat.";
    }
    state.patientId = null;
    return;
  }

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Chọn bệnh nhân";
  placeholder.disabled = true;
  placeholder.selected = true;
  patientSelect.appendChild(placeholder);
  if (welcomePatientSelect) {
    const welcomePlaceholder = placeholder.cloneNode(true);
    welcomePlaceholder.textContent = "Chọn bệnh nhân để bắt đầu chat";
    welcomePatientSelect.appendChild(welcomePlaceholder);
    welcomePatientSelect.disabled = false;
  }

  for (const p of list) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = p.full_name || "Bệnh nhân " + p.id.slice(0, 5);
    patientSelect.appendChild(opt);
    if (welcomePatientSelect) {
      const wOpt = document.createElement("option");
      wOpt.value = p.id;
      wOpt.textContent = opt.textContent;
      welcomePatientSelect.appendChild(wOpt);
    }
  }

  state.patientId = null;
  state.conversationId = null;
  state.conversations = [];
  state.renderedConversationCount = CONVERSATION_PAGE_SIZE;
  renderConversationList([]);
  if (messagesEl) {
    messagesEl.innerHTML = "";
    messagesEl.style.display = "none";
  }
  if (welcomeScreen) welcomeScreen.style.display = "flex";
  syncPatientSelectUi("");
  if (welcomePatientHint) {
    welcomePatientHint.textContent = "Chọn bệnh nhân để bắt đầu hội thoại.";
  }
  if (statusText) statusText.textContent = "Hãy chọn hồ sơ bệnh nhân để bắt đầu.";
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
  state.renderedConversationCount = CONVERSATION_PAGE_SIZE;
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
  // Ensure voice/text paths both switch from welcome to chat timeline.
  if (welcomeScreen && welcomeScreen.style.display !== "none") {
    showMessagesView();
  }
   if (!state.patientId) {
    if (statusText) {
      statusText.textContent = "Chưa chọn bệnh nhân";
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
    if (res.assistant_message) {
      const voiceSel = document.getElementById("tts-voice-select");
      const selectedVoice =
        voiceSel && voiceSel.value ? voiceSel.value : null;
      playTtsStream(stripForTts(res.assistant_message), selectedVoice).catch(
        (e) => {
          if (isAutoplayBlockedError(e)) {
            showStatusTemp(
              "Đã có câu trả lời, nhưng loa bị chặn autoplay. Bấm nút Đọc hoặc bật quyền Sound/Autoplay."
            );
            return;
          }
          if (!isExpectedPlayInterrupt(e)) {
            console.warn("[TTS] auto-play for text response failed", e);
          }
        }
      );
    }
  } catch (err) {
    console.error(err);
    if (typingEl?.parentNode) typingEl.remove();
    typingEl = null;
    if (messagesEl && state.patientId === currentPatientId) {
      const detail =
        err && typeof err.message === "string" && err.message.trim()
          ? err.message.trim()
          : "Không gọi được dịch vụ chat. Kiểm tra backend và GEMINI_API_KEY.";
      appendMessage("assistant", detail);
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
    await activatePatient(value);
  });
}

if (welcomePatientSelect) {
  welcomePatientSelect.addEventListener("change", async (e) => {
    await activatePatient(e.target.value);
  });
}

if (welcomeStartBtn) {
  welcomeStartBtn.addEventListener("click", () => {
    if (!state.patientId) {
      if (statusText) statusText.textContent = "Hãy chọn bệnh nhân trước khi bắt đầu.";
      return;
    }
    const inputField = document.getElementById("inputField");
    if (inputField && typeof inputField.focus === "function") inputField.focus();
    if (statusText) statusText.textContent = "Bạn có thể nhập câu hỏi ngay bây giờ.";
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

function initAssistantTextPreference() {
  try {
    const saved = localStorage.getItem(ASSISTANT_TEXT_PREVIEW_KEY);
    state.showAssistantTextPreview = saved === "1";
  } catch (_) {
    state.showAssistantTextPreview = false;
  }
  applyAssistantTextPreviewUi();
  if (assistantTextToggle) {
    assistantTextToggle.addEventListener("change", (e) => {
      state.showAssistantTextPreview = !!e.target.checked;
      try {
        localStorage.setItem(
          ASSISTANT_TEXT_PREVIEW_KEY,
          state.showAssistantTextPreview ? "1" : "0"
        );
      } catch (_) {}
      if (state.conversationId) {
        api(`/conversations/${encodeURIComponent(state.conversationId)}`)
          .then((detail) => renderConversation(detail.messages || []))
          .catch((err) => console.warn("refresh conversation after toggle", err));
      }
    });
  }
}

if (patientSelect) {
  (async function init() {
    try {
      initAssistantTextPreference();
      await Promise.all([loadPatients(), loadTtsVoices()]);
      if (statusText) {
        statusText.textContent = STATUS_IDLE;
      }
      if (!window.isSecureContext && !/^localhost$|^127\./.test(location.hostname)) {
        if (statusText) {
          statusText.textContent =
            "Mic/STT cần HTTPS hoặc localhost — hãy mở qua http://127.0.0.1:8000/static/...";
        }
      }
    } catch (err) {
      console.error(err);
      if (statusText) {
        statusText.textContent = "Không kết nối được backend API.";
      }
    }
  })();
}

// —— STT/TTS: recording -> POST /api/chat/audio ——
let voiceRecorder = null;
let voiceChunks = [];
let voiceStream = null;
let recordingStartedAt = 0;
let speechRecognition = null;
let speechActive = false;
let speechFinalText = "";
let speechStoppedByUser = false;
let speechFallbackToRecorder = false;

function getSpeechRecognitionCtor() {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function normalizeTranscriptText(value) {
  return (value || "").replace(/\s+/g, " ").trim();
}

function canUseBrowserSpeechRecognition() {
  return !!getSpeechRecognitionCtor();
}

function stopBrowserSpeechRecognition() {
  if (!speechRecognition || !speechActive) return;
  speechStoppedByUser = true;
  try {
    speechRecognition.stop();
  } catch (_) {}
}

async function startBrowserSpeechRecognition() {
  const Ctor = getSpeechRecognitionCtor();
  if (!Ctor) return false;

  if (speechRecognition && speechActive) return true;
  speechFinalText = "";
  speechStoppedByUser = false;
  speechFallbackToRecorder = false;

  const recognition = new Ctor();
  speechRecognition = recognition;
  recognition.lang = "vi-VN";
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    speechActive = true;
    state.recording = true;
    setMicUiState({ recording: true, disabled: false });
    if (statusText) statusText.textContent = "Đang nghe… nói xong có thể bấm mic để dừng.";
  };

  recognition.onresult = (event) => {
    let finalText = "";
    let interimText = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const text = event.results[i]?.[0]?.transcript || "";
      if (event.results[i].isFinal) finalText += text + " ";
      else interimText += text + " ";
    }
    if (finalText) speechFinalText += finalText;
    const preview = normalizeTranscriptText(speechFinalText || interimText);
    if (preview && statusText) statusText.textContent = "Đã nghe: " + preview;
  };

  recognition.onerror = async () => {
    speechActive = false;
    state.recording = false;
    setMicUiState({ recording: false, disabled: false });
    speechFallbackToRecorder = true;
    if (statusText) statusText.textContent = "Nhận diện giọng nói trình duyệt lỗi, đang chuyển sang ghi âm…";
    const started = await startMediaRecorderRecording();
    if (!started) {
      speechFallbackToRecorder = false;
      if (statusText) statusText.textContent = "Không chuyển được sang chế độ ghi âm.";
    }
  };

  recognition.onend = async () => {
    speechActive = false;
    state.recording = false;
    setMicUiState({ recording: false, disabled: false });
    if (speechFallbackToRecorder) {
      speechFallbackToRecorder = false;
      return;
    }
    const transcript = normalizeTranscriptText(speechFinalText);
    speechFinalText = "";
    if (speechStoppedByUser && !transcript) {
      if (statusText) statusText.textContent = STATUS_IDLE;
      speechStoppedByUser = false;
      return;
    }
    if (!transcript) {
      if (statusText) statusText.textContent = "Không nghe rõ, thử nói gần mic hơn.";
      speechStoppedByUser = false;
      return;
    }
    speechStoppedByUser = false;
    if (statusText) statusText.textContent = "Đang gửi nội dung giọng nói…";
    await backendSendMessage(transcript);
  };

  try {
    recognition.start();
    return true;
  } catch (_) {
    return false;
  }
}

async function startMediaRecorderRecording() {
  try {
    if (voiceStream) {
      voiceStream.getTracks().forEach((t) => t.stop());
      voiceStream = null;
    }
    voiceStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
        sampleRate: 16000,
        sampleSize: 16,
      },
    });
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
    voiceRecorder.onerror = (evt) => {
      console.error("voiceRecorder.onerror", evt);
      state.recording = false;
      setMicUiState({ recording: false, disabled: false });
      if (statusText) statusText.textContent = "Lỗi ghi âm. Vui lòng thử lại.";
    };
    voiceRecorder.onstop = async () => {
      if (voiceStream) {
        voiceStream.getTracks().forEach((t) => t.stop());
      }
      voiceStream = null;
      state.recording = false;
      setMicUiState({ recording: false, disabled: true });
      const durationMs = Date.now() - recordingStartedAt;
      const blob = new Blob(voiceChunks, {
        type: voiceRecorder.mimeType || "audio/webm",
      });
      voiceRecorder = null;
      voiceChunks = [];
      if (durationMs < 450 || blob.size < 16) {
        setMicUiState({ disabled: false });
        if (statusText) statusText.textContent = "Bản ghi quá ngắn, hãy nói lâu hơn một chút.";
        return;
      }
      await backendSendAudio(blob);
    };
    voiceRecorder.start(250);
    recordingStartedAt = Date.now();
    state.recording = true;
    setMicUiState({ recording: true, disabled: false });
    if (statusText) statusText.textContent = "Đang ghi… nhấn mic lần nữa để gửi.";
    return true;
  } catch (e) {
    console.error(e);
    state.recording = false;
    setMicUiState({ recording: false, disabled: false });
    if (statusText) statusText.textContent = "Không mở được microphone.";
    return false;
  }
}

function setMicUiState({ recording = false, disabled = false } = {}) {
  const micBtn = document.getElementById("micBtn");
  if (!micBtn) return;
  micBtn.classList.toggle("recording", recording);
  micBtn.disabled = !!disabled;
}

async function backendSendAudio(blob) {
  if (state.voiceSending) return;
  if (!state.patientId) {
    if (statusText) statusText.textContent = "Chưa chọn bệnh nhân";
    return;
  }
  const requestId = ++state.activeAudioRequestId;
  const audioFlowStartMs = performance.now();
  const currentPatientId = state.patientId;
  const currentConversationId = state.conversationId;
  const welcome = document.getElementById("welcomeScreen");
  const msgs = document.getElementById("messages");
  if (welcome && welcome.style.display !== "none") {
    welcome.style.display = "none";
    if (msgs) msgs.style.display = "flex";
  }
  state.voiceSending = true;
  setMicUiState({ disabled: true });
  setSending(true);
  const fd = new FormData();
  fd.append("patient_id", currentPatientId);
  if (currentConversationId) fd.append("conversation_id", currentConversationId);
  const blobType = ((blob && blob.type) || "").toLowerCase();
  let audioExt = "webm";
  if (blobType.includes("wav")) audioExt = "wav";
  else if (blobType.includes("mpeg") || blobType.includes("mp3")) audioExt = "mp3";
  else if (blobType.includes("mp4") || blobType.includes("m4a")) audioExt = "mp4";
  fd.append("audio", blob, `recording.${audioExt}`);
  const voiceSel = document.getElementById("tts-voice-select");
  if (voiceSel && voiceSel.value) {
    fd.append("tts_voice", voiceSel.value);
  }
  fd.append("include_tts", "false");
  if (!blob || blob.size < 16) {
    if (statusText) statusText.textContent = "Bản ghi quá ngắn, hãy nói thêm một chút.";
    state.voiceSending = false;
    setMicUiState({ disabled: false });
    setSending(false);
    return;
  }
  try {
    const sttApiStartMs = performance.now();
    const res = await fetch(`${API_BASE}/chat/audio`, { method: "POST", body: fd });
    const sttApiDoneMs = performance.now();
    const text = await res.text();
    const responseReadDoneMs = performance.now();
    if (!res.ok) throw new Error(text || res.statusText);
    let data = {};
    try {
      data = JSON.parse(text);
    } catch (parseErr) {
      throw new Error("Phản hồi audio không hợp lệ từ backend.");
    }
    const parseDoneMs = performance.now();
    if (requestId !== state.activeAudioRequestId || state.patientId !== currentPatientId) {
      return;
    }
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
    if (Array.isArray(data.messages) && data.messages.length) {
      renderConversation(data.messages);
    } else {
      if (data.transcript) appendMessage("user", data.transcript);
      if (data.assistant_message) appendMessage("assistant", data.assistant_message);
    }
    const renderDoneMs = performance.now();
    console.info("[VOICE_TIMING] /chat/audio completed", {
      requestId,
      total_ms: Math.round(renderDoneMs - audioFlowStartMs),
      api_roundtrip_ms: Math.round(sttApiDoneMs - sttApiStartMs),
      response_read_ms: Math.round(responseReadDoneMs - sttApiDoneMs),
      json_parse_ms: Math.round(parseDoneMs - responseReadDoneMs),
      render_ms: Math.round(renderDoneMs - parseDoneMs),
      transcript_chars: (data.transcript || "").length,
      assistant_chars: (data.assistant_message || "").length,
    });
    // Da nhan xong response chat: tra UI ve idle ngay, khong doi TTS phat xong.
    setSending(false);
    if (statusText) statusText.textContent = STATUS_IDLE;
    if (data.assistant_message) {
      const selectedVoice = (voiceSel && voiceSel.value) ? voiceSel.value : null;
      const ttsKickoffMs = performance.now();
      playTtsStream(stripForTts(data.assistant_message), selectedVoice).then(() => {
        const ttsDoneMs = performance.now();
        console.info("[VOICE_TIMING] TTS playback pipeline completed", {
          requestId,
          tts_pipeline_ms: Math.round(ttsDoneMs - ttsKickoffMs),
        });
      }).catch((e) => {
        const ttsFailMs = performance.now();
        console.warn("[VOICE_TIMING] TTS playback pipeline failed", {
          requestId,
          tts_pipeline_ms: Math.round(ttsFailMs - ttsKickoffMs),
          error: e?.message || String(e),
        });
        if (isAutoplayBlockedError(e)) {
          showStatusTemp(
            "Đã có câu trả lời, nhưng loa bị chặn autoplay. Bấm nút Đọc hoặc bật quyền Sound/Autoplay."
          );
          return;
        }
        if (!isExpectedPlayInterrupt(e)) {
          console.warn("[TTS] auto-play for audio response failed", e);
        }
      });
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
    state.voiceSending = false;
    setMicUiState({ disabled: false });
    // Truong hop da tra ve idle som o tren thi giu nguyen; neu co loi thi reset lai.
    if (state.sending) setSending(false);
    if (statusText && statusText.textContent === "Đang soạn trả lời…") {
      statusText.textContent = STATUS_IDLE;
    }
  }
}

async function toggleVoiceRecord() {
  primeAudioOutputFromGesture();
  if (state.sending || state.voiceSending) return;
  if (speechActive) {
    stopBrowserSpeechRecognition();
    return;
  }
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
        "Microphone unavailable (use HTTPS or localhost, not file://).";
    }
    return;
  }
  if (canUseBrowserSpeechRecognition()) {
    const srStartMs = performance.now();
    const started = await startBrowserSpeechRecognition();
    if (started) {
      console.info("[VOICE_TIMING] Browser SpeechRecognition started", {
        start_overhead_ms: Math.round(performance.now() - srStartMs),
      });
    }
    if (started) return;
  }
  const mrStartMs = performance.now();
  const startedMediaRecorder = await startMediaRecorderRecording();
  console.info("[VOICE_TIMING] MediaRecorder start attempt", {
    started: !!startedMediaRecorder,
    start_overhead_ms: Math.round(performance.now() - mrStartMs),
  });
}

// Bind after load (inline onclick may not see globals)
const micBtnEl = document.getElementById("micBtn");
if (micBtnEl) {
  micBtnEl.addEventListener("click", () => {
    toggleVoiceRecord();
  });
}

if (sidebarLogoEl) {
  sidebarLogoEl.addEventListener("click", () => {
    goToHomeScreen();
  });
}

if (topbarBrandEl) {
  topbarBrandEl.addEventListener("click", () => {
    goToHomeScreen();
  });
}

