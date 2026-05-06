const API = "http://localhost:8000";

let currentSessionId = null;
let recognition      = null;
let isListening      = false;

// ── Auth check ────────────────────────────────────────────────────────────────
const token     = localStorage.getItem("token");
const userName  = localStorage.getItem("name");
const userEmail = localStorage.getItem("email");

if (!token) window.location.href = "login.html";

// ── On page load ──────────────────────────────────────────────────────────────
window.onload = async () => {
  const firstLetter = userName ? userName[0].toUpperCase() : "S";
  document.getElementById("userName").textContent   = userName || "Student";
  document.getElementById("userEmail").textContent  = userEmail || "";
  document.getElementById("userAvatar").textContent = firstLetter;

  const firstName = userName ? userName.split(" ")[0] : "";
  const welcomeBubble = document.querySelector(".bubble-bot");
  if (welcomeBubble) {
    welcomeBubble.innerHTML = `Hello ${firstName}! I'm the GCEK Exam Assistant.<br><br>Ask me anything about exam rules, hall tickets, attendance, malpractice regulations, or grading policies.`;
  }

  await loadSessions();
  document.getElementById("userInput").focus();
};

// ── Authenticated fetch ───────────────────────────────────────────────────────
async function authFetch(url, options = {}) {
  return fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
      ...(options.headers || {})
    }
  });
}

// ── Load sessions ─────────────────────────────────────────────────────────────
async function loadSessions() {
  try {
    const res  = await authFetch(`${API}/sessions`);
    const data = await res.json();
    renderSessions(data);
  } catch (err) {
    console.error("Failed to load sessions:", err);
  }
}

function renderSessions(sessions) {
  const list = document.getElementById("sessionList");
  list.innerHTML = "";

  if (!sessions.length) {
    list.innerHTML = `<div style="font-size:12px;color:#484f58;padding:8px 10px;">No chats yet</div>`;
    return;
  }

  sessions.forEach(s => {
    const item = document.createElement("div");
    item.className = "session-item" + (s.id === currentSessionId ? " active" : "");
    item.setAttribute("data-id", s.id);
    item.innerHTML = `
      <div class="session-title">${s.title}</div>
      <div class="session-actions">
        <span class="del-btn" onclick="deleteSession(event, ${s.id})">✕</span>
      </div>`;
    item.onclick = () => loadSession(s.id);
    list.appendChild(item);
  });
}

function addSessionToSidebar(sessionId, title) {
  const list  = document.getElementById("sessionList");
  const empty = list.querySelector("div[style]");
  if (empty) empty.remove();

  const item = document.createElement("div");
  item.className = "session-item active";
  item.setAttribute("data-id", sessionId);
  item.innerHTML = `
    <div class="session-title">${title}</div>
    <div class="session-actions">
      <span class="del-btn" onclick="deleteSession(event, ${sessionId})">✕</span>
    </div>`;
  item.onclick = () => loadSession(sessionId);
  list.insertBefore(item, list.firstChild);
}

function setActiveSession(sessionId) {
  document.querySelectorAll(".session-item").forEach(el => {
    el.classList.toggle("active", parseInt(el.getAttribute("data-id")) === sessionId);
  });
}

// ── Load messages of a session ────────────────────────────────────────────────
async function loadSession(sessionId) {
  currentSessionId = sessionId;
  document.getElementById("chips").style.display = "none";
  document.getElementById("messages").innerHTML  = "";
  setActiveSession(sessionId);

  try {
    const res  = await authFetch(`${API}/sessions/${sessionId}/messages`);
    const msgs = await res.json();
    msgs.forEach(m => addMessage(m.content, m.role === "user", m.sources || [], m.id));
  } catch (err) {
    console.error("Failed to load session:", err);
  }
}

// ── Delete session ────────────────────────────────────────────────────────────
async function deleteSession(e, sessionId) {
  e.stopPropagation();
  if (!confirm("Delete this chat?")) return;
  await authFetch(`${API}/sessions/${sessionId}`, { method: "DELETE" });
  const item = document.querySelector(`[data-id="${sessionId}"]`);
  if (item) item.remove();
  if (currentSessionId === sessionId) newChat();
}

// ── Add message bubble ────────────────────────────────────────────────────────
function addMessage(text, isUser, sources = [], msgId = null) {
  const messagesEl  = document.getElementById("messages");
  const firstLetter = userName ? userName[0].toUpperCase() : "S";

  const msg = document.createElement("div");
  msg.className = "msg " + (isUser ? "user" : "bot");

  const avatar = document.createElement("div");
  avatar.className  = "avatar " + (isUser ? "avatar-user" : "avatar-bot");
  avatar.textContent = isUser ? firstLetter : "G";

  const wrap   = document.createElement("div");
  wrap.className = "bubble-wrap";

  const bubble = document.createElement("div");
  bubble.className  = "bubble " + (isUser ? "bubble-user" : "bubble-bot");
  bubble.innerHTML  = text.replace(/\n/g, "<br>");
  wrap.appendChild(bubble);

  if (sources && sources.length > 0) {
    const sourcesWrap = document.createElement("div");
    sourcesWrap.style.marginTop = "6px";
    sources.forEach(s => {
      const badge = document.createElement("span");
      badge.className   = "source-badge";
      const short = s.file
        .replace("Ordinance and Regulation for ", "")
        .replace(" NEP-2020 wef AY2023-24.pdf", "")
        .replace("Rules of Examinations for NEP-2020 UG and PG Programms wef AY2023-24.pdf", "Exam Rules");
      badge.textContent = `${short} — Page ${s.page}`;
      sourcesWrap.appendChild(badge);
    });
    wrap.appendChild(sourcesWrap);
  }

  if (!isUser && msgId) {
    const feedbackRow = document.createElement("div");
    feedbackRow.className = "feedback-row";
    feedbackRow.innerHTML = `
      <span style="font-size:11px;color:#484f58;">Was this helpful?</span>
      <button class="fb-btn" onclick="sendFeedback(${msgId}, 'up', this)">👍</button>
      <button class="fb-btn" onclick="sendFeedback(${msgId}, 'down', this)">👎</button>`;
    wrap.appendChild(feedbackRow);
  }

  msg.appendChild(avatar);
  msg.appendChild(wrap);
  messagesEl.appendChild(msg);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// ── Feedback ──────────────────────────────────────────────────────────────────
async function sendFeedback(messageId, rating, btn) {
  try {
    await authFetch(`${API}/feedback`, {
      method: "POST",
      body: JSON.stringify({ message_id: messageId, rating })
    });
    btn.parentElement.innerHTML = `<span style="font-size:11px;color:#1D9E75;">Thanks for your feedback!</span>`;
  } catch (err) {
    console.error("Feedback error:", err);
  }
}

// ── Typing indicator ──────────────────────────────────────────────────────────
function showTyping() {
  const messagesEl = document.getElementById("messages");
  const msg        = document.createElement("div");
  msg.className    = "msg bot";
  msg.id           = "typing-indicator";
  msg.innerHTML    = `
    <div class="avatar avatar-bot">G</div>
    <div class="bubble-wrap">
      <div class="typing-bubble"><span></span><span></span><span></span></div>
    </div>`;
  messagesEl.appendChild(msg);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function hideTyping() {
  document.getElementById("typing-indicator")?.remove();
}

// ── Send message ──────────────────────────────────────────────────────────────
async function sendMessage() {
  const inputEl  = document.getElementById("userInput");
  const question = inputEl.value.trim();
  if (!question) return;

  document.getElementById("chips").style.display = "none";
  addMessage(question, true);
  inputEl.value = "";

  const sendBtn     = document.getElementById("sendBtn");
  inputEl.disabled  = true;
  sendBtn.disabled  = true;
  showTyping();

  try {
    const res = await authFetch(`${API}/chat`, {
      method: "POST",
      body: JSON.stringify({ question, session_id: currentSessionId })
    });

    const data = await res.json();
    hideTyping();

    if (!res.ok) {
      if (res.status === 401) { localStorage.clear(); window.location.href = "login.html"; return; }
      addMessage("Sorry, something went wrong. Please try again.", false);
      return;
    }

    if (!currentSessionId) {
      currentSessionId = data.session_id;
      addSessionToSidebar(data.session_id, question.slice(0, 50));
    }

    addMessage(data.answer, false, data.sources, data.message_id);

  } catch (err) {
    hideTyping();
    addMessage("Cannot connect to the server. Make sure the API is running on port 8000.", false);
  } finally {
    inputEl.disabled  = false;
    sendBtn.disabled  = false;
    inputEl.focus();
  }
}

// ── Suggestion chips ──────────────────────────────────────────────────────────
function askSuggestion(question) {
  document.getElementById("userInput").value = question;
  sendMessage();
}

// ── New chat ──────────────────────────────────────────────────────────────────
function newChat() {
  currentSessionId = null;
  const firstName  = userName ? userName.split(" ")[0] : "";

  document.getElementById("messages").innerHTML = `
    <div class="msg bot">
      <div class="avatar avatar-bot">G</div>
      <div class="bubble-wrap">
        <div class="bubble bubble-bot">
          Hello ${firstName}! I'm the GCEK Exam Assistant.<br><br>
          Ask me anything about exam rules, hall tickets, attendance, malpractice regulations, or grading policies.
        </div>
      </div>
    </div>`;

  document.getElementById("chips").style.display = "flex";
  document.getElementById("userInput").value     = "";
  document.getElementById("userInput").focus();
  document.querySelectorAll(".session-item").forEach(el => el.classList.remove("active"));
}

// ── Logout ────────────────────────────────────────────────────────────────────
function logout() {
  localStorage.clear();
  window.location.href = "login.html";
}

// ── Voice input ───────────────────────────────────────────────────────────────
function toggleVoice() {
  // Check browser support
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    alert("Voice input is not supported in this browser. Please use Chrome or Edge.");
    return;
  }

  // If already listening, stop
  if (isListening) {
    recognition.stop();
    stopListening();
    return;
  }

  // Start listening
  recognition = new SpeechRecognition();
  recognition.lang            = "en-IN";   // Indian English
  recognition.continuous      = false;
  recognition.interimResults  = true;
  recognition.maxAlternatives = 1;

  const micBtn  = document.getElementById("micBtn");
  const inputEl = document.getElementById("userInput");

  recognition.onstart = () => {
    isListening = true;
    micBtn.classList.add("listening");
    inputEl.placeholder = "🎤 Listening... speak your question";
    inputEl.value = "";
  };

  recognition.onresult = (event) => {
    let transcript = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript;
    }
    inputEl.value = transcript;

    // Auto send when speech is final
    if (event.results[event.results.length - 1].isFinal) {
      stopListening();
      setTimeout(() => sendMessage(), 600);
    }
  };

  recognition.onerror = (event) => {
    console.error("Speech recognition error:", event.error);
    if (event.error === "not-allowed") {
      alert("Microphone access was denied.\n\nTo fix: Click the 🔒 icon in your browser address bar → Allow microphone.");
    } else if (event.error === "no-speech") {
      inputEl.placeholder = "No speech detected. Try again.";
      setTimeout(() => inputEl.placeholder = "Ask about exam rules, schedules, hall tickets...", 2000);
    }
    stopListening();
  };

  recognition.onend = () => {
    stopListening();
  };

  recognition.start();
}

function stopListening() {
  isListening = false;
  const micBtn  = document.getElementById("micBtn");
  const inputEl = document.getElementById("userInput");
  if (micBtn)  micBtn.classList.remove("listening");
  if (inputEl) inputEl.placeholder = "Ask about exam rules, schedules, hall tickets...";
}