/* app.js — shared helpers across all MediSync AI pages */

const API = "/api";

/** Fetch wrapper that sends/receives JSON and handles errors */
async function apiCall(path, options = {}) {
  const token = localStorage.getItem("medisync_token");
  const headers = options.body && !(options.body instanceof FormData) ? { "Content-Type": "application/json" } : {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API}${path}`, { headers, ...options });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) {
      localStorage.removeItem("medisync_token");
      localStorage.removeItem("medisync_user");
      window.location.href = "login.html";
    }
    const err = new Error(data.detail?.message || data.detail || "Something went wrong");
    err.data = data;
    throw err;
  }
  return data;
}

/* ---------------------------------------------------------------------
   Theme (light / dark)
   --------------------------------------------------------------------- */
function currentTheme() {
  return localStorage.getItem("medisync_theme") || "light";
}
function setTheme(theme) {
  localStorage.setItem("medisync_theme", theme);
  document.documentElement.setAttribute("data-theme", theme);
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.textContent = theme === "dark" ? "☀️" : "🌙";
}
function toggleTheme() {
  setTheme(currentTheme() === "dark" ? "light" : "dark");
}

/* ---------------------------------------------------------------------
   Top navigation bar (with language + theme switchers)
   --------------------------------------------------------------------- */
const LANGUAGE_LABELS = {
  en: "EN", hi: "हिं", bn: "বাং", ta: "தமி", mr: "मरा",
};
const LANGUAGE_NAMES = {
  en: "English", hi: "हिंदी (Hindi)", bn: "বাংলা (Bengali)", ta: "தமிழ் (Tamil)", mr: "मराठी (Marathi)",
};

function renderTopbar(active) {
  const el = document.getElementById("topbar");
  if (!el) return;
  const links = [
    ["index.html", "nav_home"],
    ["scan.html", "nav_scan"],
    ["selfcare.html", "nav_selfcare"],
    ["order.html", "nav_order"],
    ["inventory.html", "nav_inventory"],
    ["about.html", "nav_about"],
  ];
  const lang = currentLang();
  const user = JSON.parse(localStorage.getItem("medisync_user") || "null");
  el.innerHTML = `
    <div class="brand"><span class="dot"></span> MediSync AI</div>
    <nav>${links.map(([href, key]) =>
      `<a href="${href}" class="${active === href ? "active" : ""}" data-i18n="${key}"></a>`).join("")}
      <button class="theme-toggle-btn" id="theme-toggle" type="button" title="Toggle theme">🌙</button>
      <div class="lang-switch">
        <button class="lang-btn" id="lang-toggle" type="button">🌐 ${LANGUAGE_LABELS[lang] || "EN"}</button>
        <div class="lang-menu hidden" id="lang-menu">
          ${Object.keys(LANGUAGE_NAMES).map(code =>
            `<div data-lang="${code}" class="${code === lang ? "active-lang" : ""}">${LANGUAGE_NAMES[code]}</div>`).join("")}
        </div>
      </div>
      ${user ? `
        <div class="lang-switch">
          <button class="lang-btn" id="user-toggle" type="button">👤 ${user.name.split(" ")[0]}</button>
          <div class="lang-menu hidden" id="user-menu">
            <div id="logout-option" data-i18n="logout_btn"></div>
          </div>
        </div>` : ""}
    </nav>
  `;

  document.getElementById("lang-toggle").addEventListener("click", (e) => {
    e.stopPropagation();
    document.getElementById("lang-menu").classList.toggle("hidden");
  });
  document.querySelectorAll("#lang-menu [data-lang]").forEach(opt => {
    opt.addEventListener("click", () => setLang(opt.dataset.lang));
  });

  if (user) {
    document.getElementById("user-toggle").addEventListener("click", (e) => {
      e.stopPropagation();
      document.getElementById("user-menu").classList.toggle("hidden");
    });
    document.getElementById("logout-option").addEventListener("click", logout);
  }

  document.addEventListener("click", () => {
    document.getElementById("lang-menu")?.classList.add("hidden");
    document.getElementById("user-menu")?.classList.add("hidden");
  });

  document.getElementById("theme-toggle").addEventListener("click", toggleTheme);
  setTheme(currentTheme());
}

async function logout() {
  try { await apiCall("/auth/logout", { method: "POST" }); } catch {}
  localStorage.removeItem("medisync_token");
  localStorage.removeItem("medisync_user");
  window.location.href = "login.html";
}

/** Redirects to login if there's no valid session. Returns true if authenticated. */
async function requireAuthOrRedirect() {
  const publicPages = ["login.html", "signup.html"];
  const current = window.location.pathname.split("/").pop() || "index.html";
  if (publicPages.includes(current)) return true;

  const token = localStorage.getItem("medisync_token");
  if (!token) {
    window.location.href = "login.html";
    return false;
  }
  try {
    const user = await apiCall("/auth/me");
    localStorage.setItem("medisync_user", JSON.stringify(user));
    return true;
  } catch {
    window.location.href = "login.html";
    return false;
  }
}

/** Renders the signature verification ladder (steps = [{check, passed, detail}]) */
function renderLadder(steps) {
  return `<div class="ladder">${steps.map((s, i) => `
    <div class="ladder-step ${s.passed ? "pass" : "fail"}" style="animation-delay:${i * 0.12}s">
      <div class="node">${s.passed ? "✓" : "✕"}</div>
      <div class="content">
        <strong>${s.check}</strong>
        <span>${s.detail}</span>
      </div>
    </div>`).join("")}</div>`;
}

/** Simple toast notification */
function toast(message, kind = "info") {
  let box = document.getElementById("toast-box");
  if (!box) {
    box = document.createElement("div");
    box.id = "toast-box";
    box.style.position = "fixed";
    box.style.bottom = "20px";
    box.style.right = "20px";
    box.style.zIndex = "9999";
    document.body.appendChild(box);
  }
  const t = document.createElement("div");
  t.className = "card toast-pop";
  t.style.marginTop = "8px";
  t.style.borderLeft = `4px solid ${kind === "error" ? "var(--blocked)" : "var(--brand-mid)"}`;
  t.style.maxWidth = "320px";
  t.textContent = message;
  box.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

/** Fades cards/sections in as they scroll into view */
function initScrollReveal() {
  const targets = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window) || targets.length === 0) {
    targets.forEach(t => t.classList.add("in-view"));
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add("in-view");
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });
  targets.forEach(t => observer.observe(t));
}

/** Renders floating background blobs used behind hero/header sections */
function renderBgBlobs() {
  document.querySelectorAll(".bg-blobs").forEach(container => {
    container.innerHTML = `
      <div class="blob blob-a"></div>
      <div class="blob blob-b"></div>
      <div class="blob blob-c"></div>
    `;
  });
}

/** Subtle 3D tilt effect on cards as the mouse moves over them */
function initTiltEffect() {
  const cards = document.querySelectorAll(".module-card, .product-card");
  cards.forEach(card => {
    card.addEventListener("mousemove", (e) => {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const rotateX = ((y / rect.height) - 0.5) * -8;
      const rotateY = ((x / rect.width) - 0.5) * 8;
      card.style.transform = `perspective(600px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-4px)`;
    });
    card.addEventListener("mouseleave", () => {
      card.style.transform = "";
    });
  });
}

/* ---------------------------------------------------------------------
   Floating chatbot widget (present on every page)
   --------------------------------------------------------------------- */
function getChatHistory() {
  try {
    return JSON.parse(sessionStorage.getItem("medisync_chat_history") || "[]");
  } catch {
    return [];
  }
}
function saveChatHistory(history) {
  sessionStorage.setItem("medisync_chat_history", JSON.stringify(history));
}

function renderChatWidget() {
  if (document.getElementById("chat-widget-root")) return;

  const root = document.createElement("div");
  root.id = "chat-widget-root";
  root.innerHTML = `
    <button class="chat-bubble" id="chat-bubble-btn" title="${t("chat_title")}">💬</button>
    <div class="chat-panel hidden" id="chat-panel">
      <div class="chat-panel-header">
        <strong data-i18n="chat_title"></strong>
        <button class="chat-close-btn" id="chat-close-btn">✕</button>
      </div>
      <div class="chat-messages" id="chat-messages"></div>
      <div class="chat-input-row">
        <input type="text" id="chat-input" data-i18n-placeholder="chat_placeholder">
        <button id="chat-send-btn" data-i18n="chat_send"></button>
      </div>
      <div class="chat-disclaimer" data-i18n="chat_disclaimer"></div>
    </div>
  `;
  document.body.appendChild(root);
  applyTranslations();

  const panel = document.getElementById("chat-panel");
  const bubble = document.getElementById("chat-bubble-btn");
  const messagesBox = document.getElementById("chat-messages");

  function renderMessages() {
    const history = getChatHistory();
    if (history.length === 0) {
      messagesBox.innerHTML = `<div class="chat-msg assistant">${t("chat_greeting")}</div>`;
      return;
    }
    messagesBox.innerHTML = history.map(m =>
      `<div class="chat-msg ${m.role}">${m.content}</div>`).join("");
    messagesBox.scrollTop = messagesBox.scrollHeight;
  }

  bubble.addEventListener("click", () => {
    panel.classList.toggle("hidden");
    if (!panel.classList.contains("hidden")) renderMessages();
  });
  document.getElementById("chat-close-btn").addEventListener("click", () => panel.classList.add("hidden"));

  async function sendMessage() {
    const input = document.getElementById("chat-input");
    const message = input.value.trim();
    if (!message) return;
    input.value = "";

    const history = getChatHistory();
    history.push({ role: "user", content: message });
    saveChatHistory(history);
    renderMessages();

    const typingDiv = document.createElement("div");
    typingDiv.className = "chat-msg assistant";
    typingDiv.id = "chat-typing";
    typingDiv.textContent = "...";
    messagesBox.appendChild(typingDiv);
    messagesBox.scrollTop = messagesBox.scrollHeight;

    try {
      const data = await apiCall("/chatbot", {
        method: "POST",
        body: JSON.stringify({ message, history: history.slice(0, -1), language: currentLang() }),
      });
      const updated = getChatHistory();
      updated.push({ role: "assistant", content: data.reply });
      saveChatHistory(updated);
      renderMessages();
    } catch (err) {
      document.getElementById("chat-typing")?.remove();
      toast(err.message, "error");
    }
  }

  document.getElementById("chat-send-btn").addEventListener("click", sendMessage);
  document.getElementById("chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendMessage();
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  setTheme(currentTheme());
  const isAuthed = await requireAuthOrRedirect();
  if (!isAuthed) return; // redirecting to login.html, don't render the rest

  const current = window.location.pathname.split("/").pop() || "index.html";
  renderTopbar(current);
  applyTranslations();
  renderBgBlobs();
  initScrollReveal();
  initTiltEffect();
  renderChatWidget();
});
