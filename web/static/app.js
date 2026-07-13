// WeaverCode Dashboard — SPA بلا تبعيات (تصميم Claude Code)
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const api = (p, opt) => fetch(p, opt).then((r) => r.json());
  const post = (p, body) => api(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

  const viewStack = ["v-sessions"];
  function show(id, dir) {
    const cur = $(".view.active");
    const el = document.getElementById(id);
    if (!el || (cur && cur.id === id)) { if (el && !el.classList.contains("active")) { el.classList.add("active"); } }
    // انتقال ناعم (انزلاق حسب الاتجاه)
    if (cur && cur !== el) {
      cur.classList.remove("active");
      cur.classList.add(dir === "back" ? "leave-back" : "leave-fwd");
      setTimeout(() => cur.classList.remove("leave-back", "leave-fwd"), 260);
    }
    el.classList.remove("leave-back", "leave-fwd");
    el.classList.add("active", dir === "back" ? "enter-back" : "enter-fwd");
    setTimeout(() => el.classList.remove("enter-back", "enter-fwd"), 260);
    $("#newBtn").classList.toggle("hidden", id !== "v-sessions");
    if (id === "v-sessions") loadSessions();
    if (id === "v-files") loadFiles();
    if (id === "v-settings") loadSettings();
    if (id === "v-github") loadGithub();
    if (id === "v-compose") loadCompose();
    if (id === "v-integrations") loadIntegrations();
    window.scrollTo(0, 0);
  }
  function go(id) {
    viewStack.push(id);
    try { history.pushState({ i: viewStack.length }, "", "#" + id.replace("v-", "")); } catch (e) {}
    show(id, "fwd");
  }
  function back() { if (viewStack.length > 1) history.back(); }
  window.addEventListener("popstate", () => {
    if (viewStack.length > 1) { viewStack.pop(); show(viewStack[viewStack.length - 1], "back"); }
  });
  $$("[data-back]").forEach((b) => b.onclick = back);

  // ── القائمة ──
  $("#menuBtn").onclick = () => $("#menu").classList.add("open");
  $$("[data-close]").forEach((b) => b.onclick = () => $("#" + b.dataset.close).classList.remove("open"));
  $("#menu").addEventListener("click", (e) => { if (e.target.id === "menu") $("#menu").classList.remove("open"); });
  $$(".menu-item").forEach((b) => b.onclick = () => { $("#menu").classList.remove("open"); go("v-" + b.dataset.view); });
  $("#filterBtn").onclick = () => go("v-files");

  // ── الحالة ──
  let ENV = {};
  async function refreshStatus() {
    try {
      const s = await api("/api/status");
      ENV = s;
      const dot = $("#stateDot");
      const state = (s.daemon && s.daemon.state) || "offline";
      dot.className = "state-dot " + (state === "working" ? "working" : state === "idle" ? "idle" : "");
      $("#menuStatus").textContent = "النموذج: " + (s.model || "—") + " · " + (s.provider || "") +
        (s.key_set ? " · المفتاح ✓" : " · المفتاح ✗");
    } catch (e) {}
  }
  setInterval(refreshStatus, 4000); refreshStatus();

  // ── الجلسات ──
  function rel(ts) {
    if (!ts) return "";
    const d = Math.max(0, Date.now() / 1000 - ts);
    if (d < 3600) return Math.floor(d / 60) + "m";
    if (d < 86400) return Math.floor(d / 3600) + "h";
    if (d < 7 * 86400) return Math.floor(d / 86400) + "d";
    return new Date(ts * 1000).toLocaleDateString("ar", { day: "numeric", month: "short" });
  }
  function group(ts) {
    const day = new Date(); day.setHours(0, 0, 0, 0);
    const t0 = day.getTime() / 1000, d = Date.now() / 1000 - ts;
    if (ts >= t0) return "اليوم";
    if (d < 7 * 86400) return "هذا الأسبوع";
    if (d < 31 * 86400) return "هذا الشهر";
    return "أقدم";
  }
  async function loadSessions() {
    const r = await api("/api/conversations?limit=100");
    const convs = r.conversations || [];
    const box = $("#sessions");
    if (!convs.length) {
      box.innerHTML = '<div class="empty-note">لا محادثات بعد.<br>اضغط «محادثة جديدة» للبدء.</div>';
      return;
    }
    box.innerHTML = "";
    let last = "";
    convs.forEach((c) => {
      const g = group(c.timestamp);
      if (g !== last) { last = g; const h = document.createElement("div"); h.className = "date-h"; h.textContent = g; box.appendChild(h); }
      const card = document.createElement("div");
      card.className = "sess-card";
      const repo = ghRepo || "المستودع المحلي";
      const isToday = g === "اليوم";
      card.innerHTML =
        '<div class="sess-time">' + rel(c.timestamp) + "</div>" +
        '<div class="sess-main"><div class="sess-title">' + escapeHtml((c.prompt || "محادثة").slice(0, 60)) + "</div>" +
        '<div class="sess-sub"><span class="ellip">' + escapeHtml(repo) + '</span> ☁</div></div>' +
        '<div class="sess-badge' + (isToday ? " dot" : "") + '">◌</div>';
      card.onclick = () => openSession(c);
      box.appendChild(card);
    });
  }

  // ── فتح محادثة سابقة ──
  function bubble(role, html) {
    const who = role === "user" ? "أنت" : "🕸️ WeaverCode";
    return '<div class="bubble ' + role + '"><div class="who">' + who + "</div>" + html + "</div>";
  }
  function openSession(c) {
    $("#chatTitle").textContent = (c.prompt || "محادثة").slice(0, 30);
    $("#chatMsgs").innerHTML = bubble("user", escapeHtml(c.prompt || "")) +
      bubble("agent", md(c.response || "(لا رد محفوظ)"));
    go("v-chat");
    scrollChat();
  }

  // ── محادثة جديدة (compose) ──
  $("#newBtn").onclick = () => go("v-compose");
  function loadCompose() {
    $("#modelPick").textContent = (ENV.model || "النموذج") + " ▾";
    $("#provChip").textContent = (ENV.provider || "المزود") + " ☁️";
    $("#repoChip").querySelector("span").textContent = ghRepo || "المستودع المحلي";
    $("#buildInput").value = "";
  }
  $("#modelPick").onclick = () => go("v-settings");
  $$(".sug").forEach((b) => b.onclick = () => { $("#buildInput").value = b.dataset.sug; $("#buildInput").focus(); });
  $("#buildSend").onclick = startBuild;
  $("#buildInput").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); startBuild(); } });
  async function startBuild() {
    const v = $("#buildInput").value.trim();
    if (!v) return;
    await post("/api/task", { prompt: v, mode: $("#buildMode").value });
    // افتح شاشة المحادثة الحيّة
    $("#chatTitle").textContent = v.slice(0, 30);
    $("#chatMsgs").innerHTML = bubble("user", escapeHtml(v));
    go("v-chat");
    scrollChat();
  }

  // ── متابعة داخل المحادثة ──
  $("#chatSend").onclick = sendFollow;
  $("#chatInput").addEventListener("keydown", (e) => { if (e.key === "Enter") sendFollow(); });
  async function sendFollow() {
    const v = $("#chatInput").value.trim(); if (!v) return;
    $("#chatMsgs").insertAdjacentHTML("beforeend", bubble("user", escapeHtml(v)));
    $("#chatInput").value = "";
    await post("/api/task", { prompt: v, mode: "main" });
    scrollChat();
  }
  function scrollChat() { const m = $("#chatMsgs"); m.scrollTop = m.scrollHeight; window.scrollTo(0, document.body.scrollHeight); }

  // ── البثّ الحيّ (SSE) → يظهر داخل شاشة المحادثة ──
  const EV_ICON = { thinking: "⟳", tool_start: "🔧", file_view: "📄", file_edit: "✏️", file_create: "📄", bash_run: "💻", error: "❌", done: "✅" };
  function connectSSE() {
    const es = new EventSource("/events");
    es.onmessage = (ev) => {
      let d; try { d = JSON.parse(ev.data); } catch (e) { return; }
      const chat = $("#v-chat");
      if (!chat.classList.contains("active")) { refreshStatus(); return; }
      if (d.type === "response") {
        $("#chatMsgs").insertAdjacentHTML("beforeend", bubble("agent", md(d.detail || d.message)));
      } else if (d.type === "done") {
        $("#chatMsgs").insertAdjacentHTML("beforeend", '<div class="bubble event">✅ اكتملت</div>');
      } else if (d.type !== "status") {
        const ic = EV_ICON[d.type] || "•";
        $("#chatMsgs").insertAdjacentHTML("beforeend", '<div class="bubble event">' + ic + " " + escapeHtml(d.message) + (d.detail ? " · " + escapeHtml(d.detail.slice(0, 50)) : "") + "</div>");
      }
      scrollChat();
    };
  }
  connectSSE();

  // ── الملفات ──
  async function loadFiles() {
    const r = await api("/api/files");
    $("#outputsDir").textContent = "المجلد: " + (r.outputs_dir || "");
    const box = $("#fileList");
    const files = r.files || [];
    box.innerHTML = files.length ? "" : '<div class="empty-note">لا ملفات بعد.</div>';
    files.forEach((f) => {
      const el = document.createElement("div");
      el.className = "file-row";
      el.innerHTML = '<span>' + iconFor(f.type) + '</span><span class="fn">' + escapeHtml(f.name) + '</span>' +
        '<span class="fs">' + humanSize(f.size) + '</span>' +
        '<a href="/api/files/download/' + encodeURIComponent(f.path) + '">⬇️</a>';
      box.appendChild(el);
    });
  }

  // ── الإعدادات ──
  async function loadSettings() {
    const r = await api("/api/settings"); const s = r.settings || {};
    $("#modelInput").value = s.WEAVER_MODEL || "";
    $("#keyInput").value = ""; $("#keyInput").placeholder = s.WEAVER_API_KEY || "WEAVER_API_KEY";
  }
  $("#keyToggle").onclick = () => { const k = $("#keyInput"); k.type = k.type === "password" ? "text" : "password"; };
  $("#providerSel").onchange = async (e) => { if (!e.target.value) return; await post("/api/command", { command: "/provider " + e.target.value }); loadSettings(); refreshStatus(); };
  $("#saveSettings").onclick = async () => {
    const body = {};
    if ($("#modelInput").value.trim()) body.WEAVER_MODEL = $("#modelInput").value.trim();
    if ($("#keyInput").value.trim()) body.WEAVER_API_KEY = $("#keyInput").value.trim();
    await post("/api/settings", body); $("#settingsMsg").textContent = "✅ حُفظت."; refreshStatus();
  };
  $("#testConn").onclick = async () => { $("#settingsMsg").textContent = "…جارٍ الاختبار"; const r = await post("/api/settings/test-connection", {}); $("#settingsMsg").textContent = (r.success ? "✅ " : "❌ ") + (r.output || ""); };

  // ── GitHub ──
  let ghRepo = "";
  async function loadGithub() {
    const r = await api("/api/github");
    ghRepo = (r.remote || "").replace(/^https?:\/\/github\.com\//, "").replace(/\.git$/, "");
    $("#ghInfo").textContent = "الفرع: " + (r.branch || "?") + " · " + (r.remote || "");
    $("#ghCommits").innerHTML = (r.commits || []).map((c) => "<div>" + escapeHtml(c) + "</div>").join("");
  }
  $("#ghPush").onclick = async () => {
    if (!confirm("سيُنفَّذ git add/commit/push على مستودعك المحلي. متابعة؟")) return;
    $("#ghOutput").textContent = "…جارٍ الرفع";
    const r = await post("/api/github/push", { message: $("#ghMsg").value });
    $("#ghOutput").textContent = r.output || "تم"; loadGithub();
  };
  loadGithub();

  // ── الارتباطات (Integrations) ──
  let intg = [];
  async function loadIntegrations() {
    const r = await api("/api/integrations");
    intg = r.integrations || [];
    renderIntegrations();
  }
  function renderIntegrations() {
    const box = $("#intgList");
    box.innerHTML = "";
    intg.forEach((it, idx) => {
      const card = document.createElement("div");
      card.className = "intg-card" + (it.enabled ? "" : " off");
      const url = it.url || "";
      card.innerHTML =
        '<div class="intg-ic">' + escapeHtml(it.icon || "🔗") + "</div>" +
        '<div class="intg-main"><div class="intg-name">' + escapeHtml(it.name) +
        (it.token ? ' <span class="tok">🔑</span>' : "") + "</div>" +
        '<div class="intg-url ellip">' + escapeHtml(url || "—") + "</div></div>" +
        '<div class="intg-actions">' +
        (url ? '<a class="chip-btn" href="' + encodeURI(url) + '" target="_blank" rel="noopener">افتح</a>' : "") +
        '<button class="ic" data-edit="' + idx + '" title="تعديل">✎</button>' +
        '<button class="ic" data-tog="' + idx + '" title="تفعيل">' + (it.enabled ? "🟢" : "⚪") + "</button>" +
        "</div>";
      box.appendChild(card);
    });
    $$("#intgList [data-tog]").forEach((b) => b.onclick = () => { const i = +b.dataset.tog; intg[i].enabled = !intg[i].enabled; saveIntg(); });
    $$("#intgList [data-edit]").forEach((b) => b.onclick = () => editIntg(+b.dataset.edit));
  }
  async function saveIntg() { await post("/api/integrations", { integrations: intg }); loadIntegrations(); }
  function editIntg(i) {
    const it = intg[i];
    const url = prompt("الرابط لخدمة " + it.name + ":", it.url || "");
    if (url === null) return;
    const token = prompt("مفتاح/توكِن (اختياري، يُخزَّن محلياً):", it.token || "");
    it.url = url.trim();
    if (token !== null) it.token = token.trim();
    saveIntg();
  }
  $("#addIntg").onclick = () => {
    const name = prompt("اسم الخدمة (مثل Notion):"); if (!name) return;
    const url = prompt("الرابط:", "https://"); if (url === null) return;
    intg.push({ id: "custom_" + Date.now(), name: name.trim(), icon: "🔗", url: url.trim(), token: "", enabled: true, builtin: false });
    saveIntg();
  };

  // ── مساعدات ──
  function iconFor(t) { return { py: "🐍", json: "📋", db: "🗄️", zip: "📦", md: "📝", txt: "📄", png: "🖼️", jpg: "🖼️", sh: "⚙️", js: "📜" }[t] || "📄"; }
  function humanSize(n) { if (n < 1024) return n + " B"; if (n < 1048576) return (n / 1024).toFixed(1) + " KB"; if (n < 1073741824) return (n / 1048576).toFixed(1) + " MB"; return (n / 1073741824).toFixed(2) + " GB"; }
  function escapeHtml(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  function md(s) {
    let t = escapeHtml(String(s == null ? "" : s));
    t = t.replace(/```([\s\S]*?)```/g, (m, c) => '<pre class="code">' + c.replace(/^\n/, "") + "</pre>");
    t = t.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    t = t.replace(/^#{1,6}\s?(.*)$/gm, "<b>$1</b>");
    t = t.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
    t = t.replace(/^\s*[-*]\s+(.*)$/gm, "• $1");
    t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    t = t.replace(/\n/g, "<br>");
    return t;
  }

  // بدء
  show("v-sessions");
})();
