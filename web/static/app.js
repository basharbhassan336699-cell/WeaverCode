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
  // عرض إصدار الخادم الفعلي (لتتأكد أنك تشغّل أحدث كود)
  api("/api/version").then((r) => { if (r && r.version) $("#verBadge").textContent = r.version; }).catch(() => {});

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
    const r = await api("/api/sessions?limit=100");
    const convs = r.sessions || [];
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
        '<button class="sess-del" title="حذف المحادثة" data-del="' + escapeHtml(c.id) + '">🗑️</button>';
      card.onclick = (e) => { if (e.target.closest("[data-del]")) return; openSession(c); };
      box.appendChild(card);
    });
    $$("#sessions [data-del]").forEach((b) => b.onclick = async (e) => {
      e.stopPropagation();
      if (!confirm("حذف هذه المحادثة نهائياً؟")) return;
      await post("/api/session/delete", { id: b.dataset.del });
      loadSessions();
    });
  }

  // ── فتح محادثة سابقة ──
  function bubble(role, html) {
    const who = role === "user" ? "أنت" : "🕸️ WeaverCode";
    return '<div class="bubble ' + role + '"><div class="who">' + who + "</div>" + html + "</div>";
  }
  let chatHistory = []; // سياق المحادثة الحالية (يُرسَل مع كل متابعة)
  let currentSessionId = ""; // معرّف المحادثة الحالية (يبقى ثابتاً طوال الدردشة)
  function uuid() {
    return "s_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
  }
  async function openSession(meta) {
    currentSessionId = meta.id || "";
    $("#chatTitle").textContent = (meta.prompt || "محادثة").slice(0, 30);
    $("#chatMsgs").innerHTML = '<div class="bubble event">⟳ تحميل المحادثة…</div>';
    go("v-chat");
    // حمّل كل رسائل المحادثة (لا رسالة واحدة)
    let msgs = [];
    try {
      const r = await api("/api/session?id=" + encodeURIComponent(meta.id));
      msgs = r.messages || [];
    } catch (e) {}
    chatHistory = msgs.map((m) => ({ role: m.role, content: m.content || "" }));
    $("#chatMsgs").innerHTML = msgs.map((m) =>
      bubble(m.role === "user" ? "user" : "agent",
             m.role === "user" ? escapeHtml(m.content || "") : md(m.content || ""))
    ).join("") || bubble("agent", "(محادثة فارغة)");
    $("#chatAttachList").innerHTML = ""; chatAttached = [];
    scrollChat();
  }

  // ── محادثة جديدة (compose) ──
  $("#newBtn").onclick = () => go("v-compose");
  let attached = []; // ملفات مرفقة
  async function loadCompose() {
    $("#modelPick").textContent = (ENV.model || "النموذج") + " ▾";
    $("#provChip").textContent = (ENV.provider || "المزود") + " ☁️";
    // رقاقة المستودع: صادقة — «متصل» فقط إذا رُبط GitHub فعلياً (له توكِن)
    let ghConnected = false;
    try {
      const r = await api("/api/integrations");
      const gh = (r.integrations || []).find((i) => i.id === "github");
      ghConnected = !!(gh && gh.enabled && gh.token);
    } catch (e) {}
    const chip = $("#repoChip");
    if (ghConnected && ghRepo) {
      chip.innerHTML = '<span class="ellip">🔗 ' + escapeHtml(ghRepo) + " (متصل)</span>";
    } else {
      chip.innerHTML = '<span class="ellip">📁 ' + escapeHtml(localFolder()) + " · محلي</span>";
    }
    $("#buildInput").value = "";
    attached = []; renderAttached();
  }
  function localFolder() { return (ghRepo && ghRepo.split("/").pop()) || "WeaverCode"; }

  // ── إرفاق الملفات (لشاشتَي الإنشاء والمحادثة) ──
  let chatAttached = [];
  function fileToB64(f) { return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(f); }); }
  function renderAtt(listId, arr) {
    const box = $("#" + listId);
    box.innerHTML = arr.map((a, i) => a.loading
      ? '<span class="attach-chip">⏳ ' + escapeHtml(a.name) + "…</span>"
      : '<span class="attach-chip">📎 ' + escapeHtml(a.name) + ' <b data-rm="' + i + '">✕</b></span>').join("");
    $$("#" + listId + " [data-rm]").forEach((b) => b.onclick = () => { arr.splice(+b.dataset.rm, 1); renderAtt(listId, arr); });
  }
  async function handleFiles(files, arr, listId) {
    for (const f of files) {
      if (f.size > 25 * 1024 * 1024) { alert("الملف " + f.name + " أكبر من 25MB"); continue; }
      const slot = { name: f.name, loading: true };
      arr.push(slot); renderAtt(listId, arr);
      try {
        const b64 = await fileToB64(f);
        const r = await post("/api/upload", { name: f.name, data_base64: b64 });
        if (r && r.ok) { slot.loading = false; slot.path = r.path; slot.name = r.name; }
        else { arr.splice(arr.indexOf(slot), 1); alert("تعذّر رفع " + f.name + (r && r.error ? ": " + r.error : "")); }
      } catch (err) { arr.splice(arr.indexOf(slot), 1); alert("خطأ في رفع " + f.name); }
      renderAtt(listId, arr);
    }
  }
  $("#attachBtn").onclick = () => $("#fileInput").click();
  $("#fileInput").addEventListener("change", async (e) => { await handleFiles(e.target.files, attached, "attachList"); e.target.value = ""; });
  function renderAttached() { renderAtt("attachList", attached); }
  $("#chatAttachBtn").onclick = () => $("#chatFileInput").click();
  $("#chatFileInput").addEventListener("change", async (e) => { await handleFiles(e.target.files, chatAttached, "chatAttachList"); e.target.value = ""; });
  $("#modelPick").onclick = () => go("v-settings");
  $$(".sug").forEach((b) => b.onclick = () => { $("#buildInput").value = b.dataset.sug; $("#buildInput").focus(); });
  $("#buildSend").onclick = startBuild;
  $("#buildInput").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); startBuild(); } });
  async function startBuild() {
    let v = $("#buildInput").value.trim();
    const files = attached.filter((a) => a.path);
    if (!v && !files.length) return;
    let prompt = v;
    if (files.length) prompt += "\n\n[ملفات مرفقة يمكنك قراءتها بأداة Read]:\n" + files.map((a) => "- " + a.path).join("\n");
    chatHistory = []; // محادثة جديدة
    currentSessionId = uuid(); // معرّف جديد ثابت لهذه المحادثة
    await post("/api/task", { prompt: prompt, mode: $("#buildMode").value, history: [], session_id: currentSessionId });
    chatHistory.push({ role: "user", content: prompt });
    $("#chatTitle").textContent = (v || "ملفات مرفقة").slice(0, 30);
    $("#chatMsgs").innerHTML = bubble("user", escapeHtml(v) +
      (files.length ? '<div class="who">📎 ' + files.length + " ملف مرفق</div>" : ""));
    attached = []; renderAttached();
    $("#chatAttachList").innerHTML = ""; chatAttached = [];
    go("v-chat");
    scrollChat();
  }

  // ── متابعة داخل المحادثة ──
  $("#chatSend").onclick = sendFollow;
  $("#chatInput").addEventListener("keydown", (e) => { if (e.key === "Enter") sendFollow(); });
  async function sendFollow() {
    const v = $("#chatInput").value.trim();
    const files = chatAttached.filter((a) => a.path);
    if (!v && !files.length) return;
    let prompt = v;
    if (files.length) prompt += "\n\n[ملفات مرفقة يمكنك قراءتها بأداة Read]:\n" + files.map((a) => "- " + a.path).join("\n");
    $("#chatMsgs").insertAdjacentHTML("beforeend", bubble("user", escapeHtml(v) +
      (files.length ? '<div class="who">📎 ' + files.length + " ملف</div>" : "")));
    $("#chatInput").value = "";
    if (!currentSessionId) currentSessionId = uuid();
    // أرسل سياق المحادثة السابق ليفهم المتابعة (بنفس معرّف المحادثة)
    await post("/api/task", { prompt: prompt, mode: "main", history: chatHistory.slice(), session_id: currentSessionId });
    chatHistory.push({ role: "user", content: prompt });
    chatAttached = []; $("#chatAttachList").innerHTML = "";
    scrollChat();
  }
  function scrollChat() { const m = $("#chatMsgs"); m.scrollTop = m.scrollHeight; window.scrollTo(0, document.body.scrollHeight); }

  // ── أزرار كتل الكود: نسخ + تكبير (تفويض الأحداث) ──
  $("#chatMsgs").addEventListener("click", (e) => {
    const copyBtn = e.target.closest("[data-copy]");
    const expBtn = e.target.closest("[data-expand]");
    if (copyBtn) {
      const pre = copyBtn.closest(".codewrap").querySelector("pre.code");
      const text = pre ? pre.textContent : "";
      navigator.clipboard.writeText(text).then(() => {
        copyBtn.textContent = "✓"; setTimeout(() => copyBtn.textContent = "⧉", 1200);
      }).catch(() => {});
    } else if (expBtn) {
      expBtn.closest(".codewrap").classList.toggle("expanded");
      expBtn.textContent = expBtn.closest(".codewrap").classList.contains("expanded") ? "⤡" : "⤢";
    }
  });

  // ── إكمال تلقائي لأوامر السلاش (يظهر عند كتابة "/") ──
  let _cmds = null;
  function loadCommands() {
    if (_cmds) return Promise.resolve(_cmds);
    return api("/api/commands").then((d) => { _cmds = (d && d.commands) || []; return _cmds; }).catch(() => (_cmds = []));
  }
  function attachSlashAutocomplete(input) {
    if (!input) return;
    const box = document.createElement("div");
    box.className = "cmd-menu"; box.style.display = "none";
    input.parentElement.appendChild(box);
    let items = [], sel = 0, open = false;
    function close() { open = false; box.style.display = "none"; }
    function pick(i) {
      const c = items[i]; if (!c) return;
      input.value = "/" + c.name + " ";
      close(); input.focus();
    }
    function render() {
      if (!items.length) { close(); return; }
      box.innerHTML = items.map((c, i) =>
        '<div class="cmd-item' + (i === sel ? " on" : "") + '" data-i="' + i + '">' +
        '<span class="cmd-n">/' + c.name + '</span><span class="cmd-d">' + escapeHtml(c.description || "") + "</span></div>").join("");
      box.style.display = "block"; open = true;
      Array.from(box.querySelectorAll(".cmd-item")).forEach((el) => {
        el.onmousedown = (e) => { e.preventDefault(); pick(+el.dataset.i); };
      });
    }
    input.addEventListener("input", async () => {
      const v = input.value;
      if (v[0] !== "/" || /\s/.test(v)) { close(); return; }  // فقط أثناء كتابة اسم الأمر
      const q = v.slice(1).toLowerCase();
      const all = await loadCommands();
      items = all.filter((c) => c.name.toLowerCase().includes(q)).slice(0, 40);
      sel = 0; render();
    });
    input.addEventListener("keydown", (e) => {
      if (!open) return;
      if (e.key === "ArrowDown") { e.preventDefault(); sel = (sel + 1) % items.length; render(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); sel = (sel - 1 + items.length) % items.length; render(); }
      else if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); e.stopPropagation(); pick(sel); }
      else if (e.key === "Escape") { close(); }
    }, true);  // capture: نعترض Enter قبل معالج الإرسال
    input.addEventListener("blur", () => setTimeout(close, 150));
  }
  attachSlashAutocomplete($("#chatInput"));
  attachSlashAutocomplete($("#buildInput"));

  // ── البثّ الحيّ (SSE) → يظهر داخل شاشة المحادثة ──
  const EV_ICON = { thinking: "⟳", tool_start: "🔧", file_view: "📄", file_edit: "✏️", file_create: "📄", bash_run: "💻", error: "❌", done: "✅" };
  function connectSSE() {
    const es = new EventSource("/events");
    es.onmessage = (ev) => {
      let d; try { d = JSON.parse(ev.data); } catch (e) { return; }
      // عند اكتمال مهمة، حدّث قائمة الجلسات إن كانت ظاهرة
      if (d.type === "done") { refreshStatus(); if ($("#v-sessions").classList.contains("active")) loadSessions(); }
      const chat = $("#v-chat");
      if (!chat.classList.contains("active")) { return; }
      if (d.type === "response") {
        const txt = d.detail || d.message;
        $("#chatMsgs").insertAdjacentHTML("beforeend", bubble("agent", md(txt)));
        chatHistory.push({ role: "assistant", content: txt });
      } else if (d.type === "done") {
        $("#chatMsgs").insertAdjacentHTML("beforeend", '<div class="bubble event">✅ اكتملت</div>');
      } else if (d.type === "action_block") {
        // ملخص جولة الأدوات بصيغة Claude Code:  ‹ 2- +11  edited a file, read a file
        const hasDiff = (d.diff_removed || 0) > 0 || (d.diff_added || 0) > 0;
        const diff = hasDiff
          ? '<span class="ab-removed">' + (d.diff_removed || 0) + '-</span> '
            + '<span class="ab-added">+' + (d.diff_added || 0) + '</span>&nbsp;&nbsp;'
          : "";
        $("#chatMsgs").insertAdjacentHTML("beforeend",
          '<div class="action-block"><span class="ab-arrow">‹</span> ' + diff +
          '<span class="ab-desc">' + escapeHtml(d.detail || d.message) + '</span></div>');
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
  // أيقونات حديثة (SVG أحادي اللون) للخدمات المعروفة، وإلا حرف/إيموجي في بلاطة
  const INTG_SVG = {
    github: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>',
    vercel: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 3L22 20H2L12 3z"/></svg>',
    huggingface: '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="9" cy="10.5" r="1.1"/><circle cx="15" cy="10.5" r="1.1"/><path d="M8 14c1 1.4 2.4 2.1 4 2.1s3-.7 4-2.1" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  };
  function intgIcon(it) {
    const svg = INTG_SVG[it.id];
    if (svg) return '<span class="ic-svg">' + svg + "</span>";
    return '<span class="ic-emoji">' + escapeHtml(it.icon || "🔗") + "</span>";
  }
  // الاتصال صادق: «متصل» فقط عند وجود اعتماد حقيقي (token)
  function isConnected(it) { return !!(it.connected || (it.token && String(it.token).trim())); }
  function renderIntegrations() {
    const box = $("#intgList");
    box.innerHTML = "";
    intg.forEach((it, idx) => {
      const conn = isConnected(it);
      const card = document.createElement("div");
      card.className = "intg-card" + (conn ? "" : " off");
      const url = it.url || "";
      let actions = '<button class="ic" data-edit="' + idx + '" title="تعديل">✎</button>';
      if (conn) {
        // متصل فعلاً: شارة خضراء صادقة + زر قطع الاتصال
        actions =
          '<span class="conn-badge">✓ متصل</span>' +
          '<button class="ic" data-open="' + idx + '" title="فتح الموقع">↗</button>' +
          '<button class="ic" data-disc="' + idx + '" title="قطع الاتصال">⏻</button>' +
          actions;
      } else if (url) {
        // غير متصل: زر اتصال يبدأ التدفّق الحقيقي
        actions = '<button class="conn-btn" data-conn="' + idx + '">اتصال</button>' + actions;
      }
      card.innerHTML =
        '<div class="intg-ic i-' + escapeHtml(it.id || "x") + '">' + intgIcon(it) + "</div>" +
        '<div class="intg-main"><div class="intg-name">' + escapeHtml(it.name) +
        (conn ? ' <span class="tok" title="اعتماد محفوظ">🔑</span>' : "") + "</div>" +
        '<div class="intg-url ellip">' + escapeHtml(url || "—") +
        '</div><div class="intg-state ' + (conn ? "on" : "off") + '">' +
        (conn ? "متصل" : "غير متصل") + "</div></div>" +
        '<div class="intg-actions">' + actions + "</div>";
      box.appendChild(card);
    });
    $$("#intgList [data-edit]").forEach((b) => b.onclick = () => editIntg(+b.dataset.edit));
    $$("#intgList [data-conn]").forEach((b) => b.onclick = () => connectIntg(+b.dataset.conn));
    $$("#intgList [data-open]").forEach((b) => b.onclick = () => { const it = intg[+b.dataset.open]; if (it && it.url) window.open(it.url, "_blank", "noopener"); });
    $$("#intgList [data-disc]").forEach((b) => b.onclick = () => disconnectIntg(+b.dataset.disc));
  }
  // تدفّق الاتصال الحقيقي: افتح صفحة إنشاء التوكن/التفويض ثم أكمل بلصق الاعتماد
  function connectIntg(i) {
    const it = intg[i];
    if (!it) return;
    const authUrl = it.auth_url || it.url;   // صفحة «السماح»/إنشاء التوكن مباشرةً
    if (authUrl) window.open(authUrl, "_blank", "noopener");
    openIntgModal(i, true);                   // الصق الاعتماد لإتمام الربط فعلاً
  }
  // قطع الاتصال: يمسح الاعتماد فيعود صادقاً «غير متصل»
  function disconnectIntg(i) {
    const it = intg[i];
    if (!it) return;
    if (!confirm("قطع الاتصال بـ " + it.name + "؟ (سيُحذف الاعتماد المحفوظ)")) return;
    it.token = ""; it.connected = false;
    saveIntg();
  }
  async function saveIntg() { await post("/api/integrations", { integrations: intg }); loadIntegrations(); }

  // نافذة تعديل/إضافة (بدل prompt الذي كان يفقد الرابط)
  let editIdx = -1;
  function openIntgModal(idx, connecting) {
    editIdx = idx;
    const it = idx >= 0 ? intg[idx] : { name: "", url: "https://", token: "" };
    $("#intgModalTitle").textContent = connecting
      ? ("إتمام الاتصال بـ " + it.name)
      : (idx >= 0 ? "تعديل: " + it.name : "إضافة ارتباط");
    $("#mName").value = it.name || "";
    $("#mName").parentElement.style.display = (idx >= 0 && it.builtin) ? "none" : "block";
    $("#mUrl").value = it.url || "";
    $("#mToken").value = it.token || "";
    // تلميح أثناء الاتصال: افتحنا الموقع — الصق المفتاح/التوكن لإتمام الربط فعلاً
    const hint = $("#mHint");
    if (hint) {
      hint.textContent = connecting
        ? "فُتحت صفحة الخدمة في تبويب جديد. أنشئ توكناً/مفتاحاً هناك (هذا هو «السماح» الفعلي) وانسخه ثم الصقه هنا لإتمام الاتصال."
        : "";
      hint.style.display = connecting ? "block" : "none";
    }
    if (connecting) setTimeout(() => $("#mToken").focus(), 100);
    $("#intgModal").classList.add("open");
  }
  function editIntg(i) { openIntgModal(i); }
  $("#addIntg").onclick = () => openIntgModal(-1);
  $$("[data-mclose]").forEach((b) => b.onclick = () => $("#intgModal").classList.remove("open"));
  $("#intgModal").addEventListener("click", (e) => { if (e.target.id === "intgModal") $("#intgModal").classList.remove("open"); });
  $("#mSave").onclick = () => {
    const url = $("#mUrl").value.trim();
    const token = $("#mToken").value.trim();
    const name = $("#mName").value.trim();
    if (editIdx >= 0) {
      intg[editIdx].url = url;
      intg[editIdx].token = token;
      if (!intg[editIdx].builtin && name) intg[editIdx].name = name;
    } else {
      if (!name) { alert("أدخل اسم الخدمة"); return; }
      intg.push({ id: "custom_" + Date.now(), name: name, icon: "🔗", url: url, token: token, enabled: true, builtin: false });
    }
    $("#intgModal").classList.remove("open");
    saveIntg();
  };

  // ── مساعدات ──
  function iconFor(t) { return { py: "🐍", json: "📋", db: "🗄️", zip: "📦", md: "📝", txt: "📄", png: "🖼️", jpg: "🖼️", sh: "⚙️", js: "📜" }[t] || "📄"; }
  function humanSize(n) { if (n < 1024) return n + " B"; if (n < 1048576) return (n / 1024).toFixed(1) + " KB"; if (n < 1073741824) return (n / 1048576).toFixed(1) + " MB"; return (n / 1073741824).toFixed(2) + " GB"; }
  function escapeHtml(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  function md(s) {
    let t = escapeHtml(String(s == null ? "" : s));
    t = t.replace(/```([\s\S]*?)```/g, (m, c) => {
      let body = c.replace(/^\n/, "");
      // سطر اللغة الأول (مثل ```bash)
      let lang = "code";
      const nl = body.indexOf("\n");
      const firstLine = nl >= 0 ? body.slice(0, nl).trim() : "";
      if (firstLine && /^[a-zA-Z0-9_+-]{1,20}$/.test(firstLine)) {
        lang = firstLine; body = body.slice(nl + 1);
      }
      const label = { bash: "Bash", sh: "Shell", py: "Python", python: "Python", js: "JavaScript", json: "JSON", ts: "TypeScript" }[lang.toLowerCase()] || lang;
      return '<div class="codewrap"><div class="codebar">' +
        '<span class="codebtns"><button class="cbtn" data-expand title="تكبير">⤢</button>' +
        '<button class="cbtn" data-copy title="نسخ">⧉</button></span>' +
        '<span class="codelang">' + escapeHtml(label) + '</span></div>' +
        '<pre class="code">' + body + "</pre></div>";
    });
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
