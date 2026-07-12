// WeaverCode Dashboard — vanilla JS (بلا CDN، يعمل دون إنترنت)
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const api = (p, opt) => fetch(p, opt).then((r) => r.json());

  // ── الوضع (dark/light/system) ──
  const themeBtn = $("#themeBtn");
  function applyTheme(t) {
    if (t === "system") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("wc-theme", t);
  }
  applyTheme(localStorage.getItem("wc-theme") || "system");
  themeBtn.onclick = () => {
    const cur = localStorage.getItem("wc-theme") || "system";
    applyTheme(cur === "dark" ? "light" : cur === "light" ? "system" : "dark");
  };

  // ── التبويبات ──
  $$(".tab").forEach((t) => {
    t.onclick = () => {
      $$(".tab").forEach((x) => x.classList.remove("active"));
      $$(".tabpane").forEach((x) => x.classList.remove("active"));
      t.classList.add("active");
      $("#tab-" + t.dataset.tab).classList.add("active");
      if (t.dataset.tab === "files") loadFiles();
      if (t.dataset.tab === "chats") loadChats();
      if (t.dataset.tab === "settings") loadSettings();
      if (t.dataset.tab === "github") loadGithub();
    };
  });

  // ── الحالة ──
  async function refreshStatus() {
    try {
      const s = await api("/api/status");
      const badge = $("#stateBadge");
      const state = (s.daemon && s.daemon.state) || "offline";
      badge.textContent = state === "working" ? "يعمل" : state === "idle" ? "جاهز" : state;
      badge.className = "badge " + (state === "working" ? "working" : state === "idle" ? "idle" : "offline");
      $("#modelChip").textContent = (s.model || "—") + " · " + (s.provider || "");
    } catch (e) {}
  }
  setInterval(refreshStatus, 3000);
  refreshStatus();

  // ── شريط الأوامر ──
  const cmdInput = $("#cmdInput");
  const history = []; let hIdx = -1;
  async function send() {
    const v = cmdInput.value.trim();
    if (!v) return;
    history.push(v); hIdx = history.length;
    cmdInput.value = "";
    if (v.startsWith("/")) {
      const r = await api("/api/command", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: v }),
      });
      pushFeed("status", "أمر: " + v, JSON.stringify(r).slice(0, 200));
    } else {
      await api("/api/task", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: v, mode: "main" }),
      });
      pushFeed("thinking", "أُضيفت المهمة للطابور", v);
    }
  }
  $("#sendBtn").onclick = send;
  cmdInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") send();
    else if (e.key === "ArrowUp" && hIdx > 0) { hIdx--; cmdInput.value = history[hIdx] || ""; }
    else if (e.key === "ArrowDown" && hIdx < history.length - 1) { hIdx++; cmdInput.value = history[hIdx] || ""; }
  });

  // ── البثّ المباشر (WebSocket) ──
  const ICONS = {
    thinking: "⟳", tool_start: "🔧", tool_end: "✓", file_view: "📄",
    file_edit: "✏️", file_create: "📄+", bash_run: "💻", response: "🕸️",
    error: "❌", done: "✅", status: "•",
  };
  function pushFeed(type, message, detail) {
    const feed = $("#feed");
    const el = document.createElement("div");
    el.className = "feed-item";
    el.innerHTML = '<span class="fi-icon">' + (ICONS[type] || "•") + "</span>" +
      "<span>" + escapeHtml(message) + "</span>" +
      (detail ? '<div class="fi-detail">' + escapeHtml(detail) + "</div>" : "");
    feed.prepend(el);
    while (feed.children.length > 100) feed.removeChild(feed.lastChild);
  }
  function setActivity(on, text) {
    const bar = $("#activityBar");
    if (on) { bar.classList.remove("hidden"); $("#activityText").textContent = text || "Still working on it..."; }
    else bar.classList.add("hidden");
  }
  function connectSSE() {
    // Server-Sent Events — يعمل عبر HTTP عادي (بلا WebSocket، بلا تبعيات)
    const es = new EventSource("/events");
    es.onmessage = (ev) => {
      let d; try { d = JSON.parse(ev.data); } catch (e) { return; }
      pushFeed(d.type, d.message, d.detail);
      if (["thinking", "tool_start", "file_view", "file_edit", "file_create", "bash_run"].includes(d.type))
        setActivity(true, d.message);
      if (d.type === "done" || d.type === "response" || d.type === "error") {
        setActivity(false);
        if (d.diff_added || d.diff_removed) {
          $("#diffCounter").classList.remove("hidden");
          $("#diffAdd").textContent = d.diff_added; $("#diffDel").textContent = d.diff_removed;
        }
      }
    };
    es.onerror = () => { /* EventSource يعيد الاتصال تلقائياً */ };
  }
  connectSSE();

  // ── الملفات ──
  let allFiles = []; let curFilter = "all";
  async function loadFiles() {
    const r = await api("/api/files");
    allFiles = r.files || [];
    $("#outputsDir").textContent = "المجلد: " + (r.outputs_dir || "");
    renderFiles();
  }
  function renderFiles() {
    const grid = $("#fileGrid");
    const filtered = allFiles.filter((f) => {
      if (curFilter === "all") return true;
      if (curFilter === "other") return !["py", "json", "db", "zip"].includes(f.type);
      return f.type === curFilter;
    });
    grid.innerHTML = filtered.length ? "" : '<div class="muted small">لا ملفات بعد.</div>';
    filtered.forEach((f) => {
      const c = document.createElement("div");
      c.className = "file-card";
      c.innerHTML =
        '<div class="file-icon">' + iconFor(f.type) + "</div>" +
        '<div class="file-name">' + escapeHtml(f.name) + "</div>" +
        '<div class="file-size">' + humanSize(f.size) + "</div>" +
        '<a class="file-dl" href="/api/files/download/' + encodeURIComponent(f.path) + '">⬇️ تحميل</a>';
      grid.appendChild(c);
    });
  }
  $$(".fbtn").forEach((b) => b.onclick = () => {
    $$(".fbtn").forEach((x) => x.classList.remove("active"));
    b.classList.add("active"); curFilter = b.dataset.f; renderFiles();
  });

  // ── المحادثات ──
  async function loadChats(search) {
    const r = await api("/api/conversations?limit=30" + (search ? "&search=" + encodeURIComponent(search) : ""));
    const list = $("#chatList");
    list.innerHTML = (r.conversations || []).length ? "" : '<div class="muted small">لا محادثات.</div>';
    (r.conversations || []).forEach((c) => {
      const el = document.createElement("div");
      el.className = "chat-item";
      el.innerHTML = '<div class="chat-prompt">' + escapeHtml(c.prompt || "") + "</div>" +
        '<div class="chat-time">' + fmtTime(c.timestamp) + " · " + (c.tools || []).join(", ") + "</div>" +
        '<div class="chat-resp">' + escapeHtml(c.response || "") + "</div>";
      el.onclick = () => el.classList.toggle("open");
      list.appendChild(el);
    });
  }
  let searchT;
  $("#chatSearch").addEventListener("input", (e) => {
    clearTimeout(searchT); searchT = setTimeout(() => loadChats(e.target.value), 300);
  });

  // ── الإعدادات ──
  async function loadSettings() {
    const r = await api("/api/settings");
    const s = r.settings || {};
    $("#modelInput").value = s.WEAVER_MODEL || "";
    $("#keyInput").value = "";
    $("#keyInput").placeholder = s.WEAVER_API_KEY || "WEAVER_API_KEY";
  }
  $("#keyToggle").onclick = () => {
    const k = $("#keyInput"); k.type = k.type === "password" ? "text" : "password";
  };
  $("#providerSel").onchange = async (e) => {
    if (!e.target.value) return;
    await api("/api/command", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: "/provider " + e.target.value }),
    });
    loadSettings(); refreshStatus();
  };
  $("#saveSettings").onclick = async () => {
    const body = {};
    if ($("#modelInput").value.trim()) body.WEAVER_MODEL = $("#modelInput").value.trim();
    if ($("#keyInput").value.trim()) body.WEAVER_API_KEY = $("#keyInput").value.trim();
    await api("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    $("#settingsMsg").textContent = "✅ حُفظت الإعدادات."; refreshStatus();
  };
  $("#testConn").onclick = async () => {
    $("#settingsMsg").textContent = "…جارٍ الاختبار";
    const r = await api("/api/settings/test-connection", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    $("#settingsMsg").textContent = (r.success ? "✅ " : "❌ ") + (r.output || "");
  };

  // ── GitHub ──
  async function loadGithub() {
    const r = await api("/api/github");
    $("#ghInfo").textContent = "الفرع: " + (r.branch || "?") + " · " + (r.remote || "");
    $("#ghCommits").innerHTML = (r.commits || []).map((c) => "<li>" + escapeHtml(c) + "</li>").join("");
  }
  $("#ghPush").onclick = async () => {
    $("#ghOutput").textContent = "…جارٍ الرفع";
    const r = await api("/api/github/push", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: $("#ghMsg").value }),
    });
    $("#ghOutput").textContent = r.output || "تم"; loadGithub();
  };

  // ── مساعدات ──
  function iconFor(t) { return { py: "🐍", json: "📋", db: "🗄️", zip: "📦", md: "📝", txt: "📄", png: "🖼️", jpg: "🖼️" }[t] || "📄"; }
  function humanSize(n) { if (n < 1024) return n + " B"; if (n < 1048576) return (n / 1024).toFixed(1) + " KB"; if (n < 1073741824) return (n / 1048576).toFixed(1) + " MB"; return (n / 1073741824).toFixed(2) + " GB"; }
  function fmtTime(ts) { if (!ts) return ""; const d = new Date(ts * 1000); return d.toLocaleString("ar"); }
  function escapeHtml(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
})();
