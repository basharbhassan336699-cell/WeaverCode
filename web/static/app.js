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
    if (id === "v-dashboard") loadDashboard();
    if (id === "v-chat") { loadEffort(); updateCtxSub(); }
    updateCtxSub();
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
      const cm = $("#cbarModel"); if (cm && s.model) cm.textContent = shortModel(s.model);
    } catch (e) {}
  }
  function shortModel(m) { return String(m || "").split("/").pop() || m || "النموذج"; }
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
  // معرّف المحادثة الحالية — يُسترجَع من localStorage ليصمد عبر تحديث الصفحة
  let currentSessionId = localStorage.getItem("weaver_session_id") || "";
  function rememberSession(id) {
    if (id) localStorage.setItem("weaver_session_id", id);
  }
  function uuid() {
    return "s_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
  }
  async function openSession(meta) {
    currentSessionId = meta.id || "";
    rememberSession(currentSessionId);
    $("#chatTitle").textContent = (meta.prompt || "محادثة").slice(0, 30);
    setRunning(false); updateCtxSub(); loadEffort();
    $("#chatMsgs").innerHTML = '<div class="bubble event">⟳ تحميل المحادثة…</div>';
    go("v-chat");
    // حمّل كل رسائل المحادثة (لا رسالة واحدة)
    let msgs = [];
    try {
      const r = await api("/api/session?id=" + encodeURIComponent(meta.id));
      msgs = r.messages || [];
    } catch (e) {}
    // نحافظ على كتل العمليات (blocks) في السجل لإعادة إرسالها وحفظها في الأدوار التالية
    chatHistory = msgs.map((m) => {
      const e = { role: m.role, content: m.content || "" };
      if (m.blocks) e.blocks = m.blocks;
      return e;
    });
    pendingBlocks = [];
    $("#chatMsgs").innerHTML = msgs.map((m) => {
      if (m.role === "user") return bubble("user", escapeHtml(m.content || ""));
      // المساعد: سجل العمليات (إن حُفظ) قبل النصّ، ثم بطاقة ملخّص الإنجاز — كما كان لحظياً
      let html = "";
      (m.blocks || []).forEach((b) => { html += actionBlockHtml(b); });
      html += bubble("agent", md(m.content || ""));
      if (m.blocks && m.blocks.length) html += completionSummaryHtml(m.blocks);
      return html;
    }).join("") || bubble("agent", "(محادثة فارغة)");
    maybeAddPrChip();   // رقاقة PRs عند فتح المحادثة أيضاً
    $("#chatAttachList").innerHTML = ""; chatAttached = [];
    scrollChat();
  }

  // ── محادثة جديدة (compose) ──
  $("#newBtn").onclick = () => { localStorage.removeItem("weaver_session_id"); go("v-compose"); };
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
    if (ghConnected) {
      const label = ghRepo ? ("🔗 " + escapeHtml(ghRepo) + " (متصل)") : "🔗 اختر مستودعاً…";
      chip.innerHTML = '<span class="ellip">' + label + "</span><span class=\"chip-caret\">▾</span>";
      chip.classList.add("clickable");
      chip.title = "اضغط لاختيار مستودع من GitHub";
      chip.onclick = openRepoPicker;
    } else {
      chip.innerHTML = '<span class="ellip">📁 ' + escapeHtml(localFolder()) + " · محلي</span>";
      chip.classList.remove("clickable");
      chip.title = "المستودع المحلي على جهازك";
      chip.onclick = null;
    }
    $("#buildInput").value = "";
    attached = []; renderAttached();
  }
  function localFolder() { return (ghRepo && ghRepo.split("/").pop()) || "WeaverCode"; }

  // ── مستعرض مستودعات GitHub الحقيقية (بلا وهم) ──
  let repoCache = [];
  async function openRepoPicker() {
    $("#repoModal").classList.add("open");
    $("#repoSearch").value = "";
    $("#repoNewForm").style.display = "none";
    $("#rnMsg").textContent = "";
    const box = $("#repoList");
    box.innerHTML = '<div class="muted small">…جارٍ جلب مستودعاتك</div>';
    try {
      const r = await api("/api/github/repos");
      if (!r.connected) { box.innerHTML = '<div class="muted small">لست متصلاً بـ GitHub بعد.</div>'; return; }
      if (r.error) { box.innerHTML = '<div class="muted small">⚠️ ' + escapeHtml(r.error) + "</div>"; return; }
      repoCache = r.repos || [];
      if (!repoCache.length) { box.innerHTML = '<div class="muted small">لا توجد مستودعات في حسابك.</div>'; return; }
      renderRepoList(repoCache);
    } catch (e) {
      box.innerHTML = '<div class="muted small">⚠️ تعذّر جلب المستودعات.</div>';
    }
  }
  function renderRepoList(list) {
    const box = $("#repoList");
    if (!list.length) { box.innerHTML = '<div class="muted small">لا نتائج.</div>'; return; }
    box.innerHTML = list.map((r, i) =>
      '<button class="repo-item" data-ri="' + i + '">'
      + '<div class="repo-top"><span class="repo-name">' + escapeHtml(r.full_name) + "</span>"
      + (r.private ? '<span class="repo-tag">🔒 خاص</span>' : '<span class="repo-tag pub">عام</span>') + "</div>"
      + (r.description ? '<div class="repo-desc">' + escapeHtml(r.description) + "</div>" : "")
      + '<div class="repo-meta">' + (r.language ? "● " + escapeHtml(r.language) + " · " : "")
      + "الفرع: " + escapeHtml(r.default_branch || "main") + "</div>"
      + "</button>").join("");
    $$("#repoList [data-ri]").forEach((b) => b.onclick = () => pickRepo(list[+b.dataset.ri]));
  }
  async function pickRepo(r) {
    ghRepo = r.full_name;
    activeRepo = r;
    $("#repoModal").classList.remove("open");
    const chip = $("#repoChip");
    // استنساخ المستودع فعلياً ليعمل الوكيل عليه (لا مجرّد سطر سياق)
    chip.innerHTML = '<span class="ellip">⏳ يُستنسَخ ' + escapeHtml(ghRepo) + "…</span>";
    try {
      const res = await post("/api/github/select-repo", {
        full_name: r.full_name, clone_url: r.clone_url, default_branch: r.default_branch });
      if (res.ok) {
        activeRepo.local_ready = true;
        chip.innerHTML = '<span class="ellip">🔗 ' + escapeHtml(ghRepo) +
          " (" + (res.files || 0) + " ملف)</span><span class=\"chip-caret\">▾</span>";
      } else {
        chip.innerHTML = '<span class="ellip">⚠️ ' + escapeHtml(ghRepo) +
          " — تعذّر الاستنساخ</span><span class=\"chip-caret\">▾</span>";
        alert("تعذّر استنساخ المستودع: " + (res.error || "خطأ") +
          "\nتأكد أن اتصال GitHub يحمل صلاحية repo.");
      }
    } catch (e) {
      chip.innerHTML = '<span class="ellip">🔗 ' + escapeHtml(ghRepo) + "</span><span class=\"chip-caret\">▾</span>";
    }
  }
  // محادثة بدون أي مستودع → يلغي مساحة العمل، يعود الوكيل للعمل محلياً
  async function pickNoRepo() {
    ghRepo = "";
    activeRepo = null;
    $("#repoModal").classList.remove("open");
    try { await post("/api/workspace/clear", {}); } catch (e) {}
    const chip = $("#repoChip");
    chip.innerHTML = '<span class="ellip">💬 بدون مستودع</span><span class="chip-caret">▾</span>';
  }
  $("#repoNone") && ($("#repoNone").onclick = pickNoRepo);
  // نموذج إنشاء مستودع جديد
  $("#repoNew") && ($("#repoNew").onclick = () => {
    const f = $("#repoNewForm");
    f.style.display = f.style.display === "none" ? "block" : "none";
    $("#rnMsg").textContent = "";
    if (f.style.display === "block") $("#rnName").focus();
  });
  $("#rnCancel") && ($("#rnCancel").onclick = () => { $("#repoNewForm").style.display = "none"; });
  $("#rnCreate") && ($("#rnCreate").onclick = async () => {
    const name = $("#rnName").value.trim();
    if (!name) { $("#rnMsg").textContent = "⚠️ اكتب اسم المستودع."; return; }
    $("#rnMsg").textContent = "…جارٍ الإنشاء على GitHub";
    try {
      const r = await post("/api/github/create-repo", {
        name: name, description: $("#rnDesc").value.trim(), private: $("#rnPrivate").checked });
      if (!r.ok) { $("#rnMsg").textContent = "⚠️ " + (r.error || "تعذّر الإنشاء"); return; }
      repoCache.unshift(r.repo);
      pickRepo(r.repo); // يُغلق النافذة ويختار الجديد
      $("#repoNewForm").style.display = "none";
      $("#rnName").value = ""; $("#rnDesc").value = "";
    } catch (e) { $("#rnMsg").textContent = "⚠️ تعذّر الاتصال بـ GitHub."; }
  });
  $("#repoSearch") && ($("#repoSearch").oninput = (e) => {
    const q = e.target.value.trim().toLowerCase();
    renderRepoList(!q ? repoCache : repoCache.filter((r) =>
      (r.full_name || "").toLowerCase().includes(q) || (r.description || "").toLowerCase().includes(q)));
  });
  $$("[data-rpclose]").forEach((b) => b.onclick = () => $("#repoModal").classList.remove("open"));
  $("#repoModal").addEventListener("click", (e) => { if (e.target.id === "repoModal") $("#repoModal").classList.remove("open"); });

  // ── إرفاق الملفات (لشاشتَي الإنشاء والمحادثة) ──
  let chatAttached = [];
  function fileToB64(f) { return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(f); }); }
  function isImageName(n) { return /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(n || ""); }
  function renderAtt(listId, arr) {
    const box = $("#" + listId);
    box.innerHTML = arr.map((a, i) => {
      if (a.loading) return '<span class="attach-chip">⏳ ' + escapeHtml(a.name) + "…</span>";
      const rm = '<b class="att-rm" data-rm="' + i + '">✕</b>';
      if (a.isImage && a.dataUrl)
        return '<span class="attach-thumb"><img src="' + a.dataUrl + '" alt="' + escapeHtml(a.name) + '"/>' + rm + '</span>';
      return '<span class="attach-chip">📎 ' + escapeHtml(a.name) + ' ' + rm + '</span>';
    }).join("");
    $$("#" + listId + " [data-rm]").forEach((b) => b.onclick = () => { arr.splice(+b.dataset.rm, 1); renderAtt(listId, arr); });
  }
  async function handleFiles(files, arr, listId) {
    for (const f of files) {
      if (f.size > 25 * 1024 * 1024) { alert("الملف " + f.name + " أكبر من 25MB"); continue; }
      const slot = { name: f.name, loading: true, isImage: isImageName(f.name) || (f.type || "").startsWith("image/") };
      arr.push(slot); renderAtt(listId, arr);
      try {
        const b64 = await fileToB64(f);
        if (slot.isImage) slot.dataUrl = b64;   // معاينة مصغّرة محلياً (بلا خادم)
        const r = await post("/api/upload", { name: f.name, data_base64: b64 });
        if (r && r.ok) { slot.loading = false; slot.path = r.path; slot.name = r.name; }
        else { arr.splice(arr.indexOf(slot), 1); alert("تعذّر رفع " + f.name + (r && r.error ? ": " + r.error : "")); }
      } catch (err) { arr.splice(arr.indexOf(slot), 1); alert("خطأ في رفع " + f.name); }
      renderAtt(listId, arr);
    }
  }
  // بطاقات المرفقات داخل رسالة المستخدم (صور مصغّرة + بطاقات ملفات) كما في Claude Code
  function attachCardsHtml(files) {
    if (!files || !files.length) return "";
    const items = files.map((a) => a.isImage && a.dataUrl
      ? '<span class="msg-att-img"><img src="' + a.dataUrl + '" alt="' + escapeHtml(a.name) + '"/></span>'
      : '<span class="msg-att-file"><span class="mf-ic">📄</span><span class="mf-nm">' + escapeHtml(a.name) + '</span></span>'
    ).join("");
    return '<div class="msg-att-row">' + items + "</div>";
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
    if (activeRepo && activeRepo.full_name) {
      prompt = "[أنت الآن داخل مستودع " + activeRepo.full_name +
        " المستنسَخ محلياً في مجلد العمل الحالي (فرع " +
        (activeRepo.default_branch || "main") + "). اعمل على ملفاته الفعلية " +
        "بمسارات نسبية (استخدم Glob/Read لاستكشافها أولاً)، ولا تخترع مسارات.]\n\n" + prompt;
    }
    chatHistory = []; // محادثة جديدة
    currentSessionId = uuid(); // معرّف جديد ثابت لهذه المحادثة
    rememberSession(currentSessionId);
    setRunning(true);
    pendingBlocks = []; turnBlocks = [];
    await post("/api/task", { prompt: prompt, mode: $("#buildMode").value, history: [], session_id: currentSessionId, repo: (activeRepo && activeRepo.full_name) || "" });
    chatHistory.push({ role: "user", content: prompt });
    $("#chatTitle").textContent = (v || "ملفات مرفقة").slice(0, 30);
    updateCtxSub();
    $("#chatMsgs").innerHTML = bubble("user", attachCardsHtml(files) +
      (v ? '<div class="msg-txt">' + escapeHtml(v) + "</div>" : ""));
    attached = []; renderAttached();
    $("#chatAttachList").innerHTML = ""; chatAttached = [];
    go("v-chat");
    scrollChat();
  }

  // ── متابعة داخل المحادثة (زر إرسال ↔ توقيف) ──
  let taskRunning = false;
  function setRunning(on) {
    taskRunning = on;
    const b = $("#chatSend");
    if (b) { b.classList.toggle("running", on); b.disabled = false; b.title = on ? "توقيف" : "إرسال"; }
    const spin = $("#effortSpin"); if (spin) spin.style.display = on ? "inline-block" : "none";
    const inp = $("#chatInput");
    if (inp) inp.placeholder = on ? "أضف ملاحظة للطابور… (Enter)" : "أضف ملاحظة أو تابع…";
    if (!on) updateSendEnabled();
  }
  function updateSendEnabled() {
    const b = $("#chatSend"); if (!b) return;
    if (taskRunning) { b.disabled = false; return; }
    const has = ($("#chatInput").value || "").trim().length > 0 || chatAttached.some((a) => a.path);
    b.disabled = !has;
  }
  function autoGrow(t) { if (!t) return; t.style.height = "auto"; t.style.height = Math.min(140, t.scrollHeight) + "px"; }
  async function stopTask() {
    try { await post("/api/stop", {}); } catch (e) {}
    setRunning(false); setLive(null);
    $("#chatMsgs").insertAdjacentHTML("beforeend", '<div class="bubble event">⏹️ أُوقفت المهمة</div>');
    scrollChat();
  }
  $("#chatSend").onclick = () => { if (taskRunning) stopTask(); else sendFollow(); };
  $("#chatInput").addEventListener("input", () => { autoGrow($("#chatInput")); updateSendEnabled(); });
  // Enter يُرسل دائماً — أثناء العمل تُدرَج الرسالة في الطابور (Queue feedback)،
  // وزر التوقيف ■ يوقف المهمة الحالية (كواجهة Claude Code).
  $("#chatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendFollow(); }
  });
  async function sendFollow() {
    const v = $("#chatInput").value.trim();
    const files = chatAttached.filter((a) => a.path);
    if (!v && !files.length) return;
    const queued = taskRunning;   // يعمل الآن → هذه ملاحظة تُدرَج للطابور
    let prompt = v;
    if (files.length) prompt += "\n\n[ملفات مرفقة يمكنك قراءتها بأداة Read]:\n" + files.map((a) => "- " + a.path).join("\n");
    chatAppend(bubble("user",
      (queued ? '<div class="who">⏳ مُدرَج في الطابور</div>' : "") +
      attachCardsHtml(files) +
      (v ? '<div class="msg-txt">' + escapeHtml(v) + "</div>" : "")));
    $("#chatInput").value = ""; autoGrow($("#chatInput"));
    if (!currentSessionId) currentSessionId = uuid();
    rememberSession(currentSessionId);
    if (!queued) { setRunning(true); pendingBlocks = []; turnBlocks = []; }
    // أرسل سياق المحادثة السابق ليفهم المتابعة (بنفس معرّف المحادثة)
    await post("/api/task", { prompt: prompt, mode: "main", history: chatHistory.slice(), session_id: currentSessionId });
    chatHistory.push({ role: "user", content: prompt });
    chatAttached = []; $("#chatAttachList").innerHTML = ""; updateSendEnabled();
    scrollChat();
  }

  // ── العنوان الفرعي (المستودع/المحادثة) تحت اسم WeaverCode ──
  function updateCtxSub() {
    const el = $("#ctxSub"); if (!el) return;
    let txt = "";
    const repo = ghRepo || (activeRepo && activeRepo.full_name) || "";
    if (repo) {
      txt = "📦 " + repo;
    } else if ($("#v-chat") && $("#v-chat").classList.contains("active")) {
      const t = (($("#chatTitle") && $("#chatTitle").textContent) || "").trim();
      if (t && t !== "محادثة") txt = "💬 " + t;
    }
    el.textContent = txt;
  }

  // ── شريط الجهد (Effort): أسرع ↔ أذكى — مبرمج ليضبط التوكنات/الحرارة فعلياً ──
  let effortLevels = [];
  const EFFORT_EN = ["Faster", "Fast", "Balanced", "High", "Higher", "Max"];
  async function loadEffort() {
    try {
      const r = await api("/api/effort");
      effortLevels = r.levels || [];
      const lvl = (r.level == null ? 3 : r.level);
      const sl = $("#effortSlider"); if (sl) sl.value = lvl;
      updateEffortLabels(lvl);
      const model = r.model || "النموذج";
      const cm = $("#cbarModel"); if (cm) cm.textContent = shortModel(model);
      const pm = $("#effortPopModel"); if (pm) pm.textContent = "النموذج: " + model;
    } catch (e) {}
  }
  function effortEn(lvl) { return (effortLevels[lvl] && effortLevels[lvl].en) || EFFORT_EN[lvl] || "High"; }
  function updateEffortLabels(lvl) {
    $("#effortBadge").textContent = effortEn(lvl);
    $("#effortPopName").textContent = effortEn(lvl);
  }
  $("#effortBtn").onclick = (e) => { e.stopPropagation(); $("#effortPop").classList.toggle("open"); };
  $("#effortSlider").addEventListener("input", (e) => updateEffortLabels(+e.target.value));
  $("#effortSlider").addEventListener("change", async (e) => {
    const lvl = +e.target.value;
    updateEffortLabels(lvl);
    try { await post("/api/effort", { level: lvl }); } catch (err) {}
    refreshStatus();
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#effortPop") && !e.target.closest("#effortBtn"))
      $("#effortPop").classList.remove("open");
  });
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
    } else {
      const ab = e.target.closest("[data-ab]");
      if (ab) showActionDetail(actionBlocks[+ab.dataset.ab]);
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

  // ── اللوحة (Dashboard): وضع التخطيط + سجل التعديلات ──
  async function loadDashboard() {
    loadGitActivity(true);   // تحديث فعلي من git عند فتح اللوحة
    try {
      const p = await api("/api/plan");
      const st = $("#planState");
      st.textContent = p.plan_mode ? "مفعّل ✅" : "معطّل ⏹️";
      st.className = "intg-state " + (p.plan_mode ? "on" : "off");
      const box = $("#pendingPlanBox");
      if (p.pending_plan) {
        box.style.display = "block";
        $("#pendingPlanText").textContent = p.pending_plan;
      } else box.style.display = "none";
    } catch (e) {}
    try {
      const r = await api("/api/operations");
      renderOpsBatches(r.batches || []);
    } catch (e) {}
  }

  // ── سجل العمليات الهرمي (3 مستويات كواجهة Claude Code) ──
  // المستوى 1: ملخّص دفعة قابل للطي · المستوى 2: قائمة العمليات · المستوى 3: تفاصيل
  const OP_TIME = (ts) => { try { return new Date(ts * 1000).toLocaleTimeString("ar"); } catch (e) { return ""; } };
  function renderOpsBatches(batches) {
    const box = $("#opsBatches");
    if (!batches.length) { box.innerHTML = '<span class="muted small">لا عمليات مسجّلة بعد.</span>'; return; }
    box.innerHTML = batches.map((b, bi) =>
      '<div class="op-batch">' +
      '<button class="op-summary" data-bi="' + bi + '">' +
        '<span class="op-caret">▸</span>' +
        '<span class="op-sum-text">' + escapeHtml(b.summary) + "</span>" +
        '<span class="op-sum-meta muted small">' + b.count + " · " + OP_TIME(b.ts) + "</span>" +
      "</button>" +
      '<div class="op-list" data-list="' + bi + '" style="display:none"></div>' +
      "</div>").join("");
    // المستوى 2: يُبنى عند فتح الملخّص (طي/فتح)
    box.querySelectorAll(".op-summary").forEach((btn) => btn.onclick = () => {
      const bi = +btn.dataset.bi, list = box.querySelector('[data-list="' + bi + '"]');
      const caret = btn.querySelector(".op-caret");
      const open = list.style.display !== "none";
      if (open) { list.style.display = "none"; caret.textContent = "▸"; return; }
      caret.textContent = "▾";
      list.style.display = "block";
      list.innerHTML = batches[bi].operations.map((o) =>
        '<button class="op-item" data-opid="' + escapeHtml(o.id) + '">' +
        '<span class="op-ic">' + o.icon + "</span>" +
        '<span class="op-verb">' + escapeHtml(o.verb) + "</span>" +
        '<span class="op-name">' + escapeHtml(o.label || o.file || "—") + "</span>" +
        ((o.added || o.removed)
          ? '<span class="ab-added">+' + o.added + '</span><span class="ab-removed">-' + o.removed + "</span>"
          : "") +
        "</button>").join("");
      // المستوى 3: نقر عملية → تفاصيلها
      list.querySelectorAll(".op-item").forEach((el) =>
        el.onclick = () => openOpDetail(el.dataset.opid));
    });
  }

  async function openOpDetail(opId) {
    const modal = $("#opDetailModal"), body = $("#opDetailBody");
    modal.classList.add("open");
    body.innerHTML = '<div class="muted small">…جارٍ التحميل</div>';
    try {
      const r = await api("/api/operations/detail?id=" + encodeURIComponent(opId));
      if (!r.ok) { body.innerHTML = '<div class="muted small">' + escapeHtml(r.error || "تعذّر") + "</div>"; return; }
      const o = r.operation;
      $("#opDetailTitle").textContent =
        (({ edit: "تعديل", create: "إنشاء", read: "قراءة", run: "تنفيذ" })[o.type] || o.type) +
        " · " + (o.file || (o.command || "").slice(0, 30));
      body.innerHTML = renderOpDetail(o);
    } catch (e) {
      body.innerHTML = '<div class="muted small">تعذّر جلب التفاصيل.</div>';
    }
  }

  // ── تلوين الكود (Syntax Highlighting) بلا مكتبات خارجية — يعمل دون إنترنت ──
  // (لا نعتمد CDN حتى لا ينكسر على Termux أوفلاين؛ محرّك خفيف مدمج يكفي للعرض.)
  const _HL_KW = {
    _common: new Set(("if else for while return function class import from export const let var new this " +
      "null true false try catch finally throw switch case break continue default do typeof instanceof " +
      "void delete yield await async static extends super public private protected interface enum type").split(" ")),
    python: new Set(("def class return if elif else for while import from as pass break continue try except " +
      "finally raise with lambda yield global nonlocal assert del in is not and or None True False async await match case print self").split(" ")),
    bash: new Set(("if then else elif fi for while do done case esac function return in select until echo " +
      "export local readonly declare set unset source alias cd grep sed awk cat").split(" ")),
  };
  function _kwset(lang) {
    if (lang === "python" || lang === "pyi") return _HL_KW.python;
    if (lang === "bash") return _HL_KW.bash;
    return _HL_KW._common;
  }
  function detectLang(path, content) {
    const ext = (path || "").split(".").pop().toLowerCase();
    const map = { py: "python", pyw: "python", pyi: "python", js: "javascript", mjs: "javascript",
      cjs: "javascript", ts: "typescript", tsx: "typescript", jsx: "javascript", json: "json",
      jsonl: "json", yaml: "yaml", yml: "yaml", toml: "toml", sh: "bash", bash: "bash", zsh: "bash",
      md: "markdown", html: "html", htm: "html", css: "css", scss: "css", rs: "rust", go: "go",
      java: "java", cpp: "cpp", c: "c", cs: "csharp", rb: "ruby", php: "php", sql: "sql", xml: "xml",
      ini: "ini", cfg: "ini", conf: "ini", env: "bash", txt: "text" };
    if (map[ext]) return map[ext];
    const base = (path || "").split("/").pop().toLowerCase();
    if (base === "dockerfile") return "bash";
    if (base === "makefile") return "bash";
    if (base.indexOf(".env") >= 0) return "bash";
    const first = ((content || "").split("\n")[0] || "").trim();
    if (first.startsWith("#!") && first.indexOf("python") >= 0) return "python";
    if (first.startsWith("#!")) return "bash";
    if (first.startsWith("{") || first.startsWith("[")) return "json";
    if (first.startsWith("---")) return "yaml";
    return "text";
  }
  function _hlLine(line, lang, kw) {
    const hash = /^(python|bash|yaml|ini|ruby|toml)$/.test(lang);
    const re = hash
      ? /(#[^\n]*)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)|(\b\d[\w.]*)|([A-Za-z_]\w*)/g
      : /(\/\/[^\n]*)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)|(\b\d[\w.]*)|([A-Za-z_$]\w*)/g;
    let out = "", last = 0, m;
    while ((m = re.exec(line))) {
      out += escapeHtml(line.slice(last, m.index));
      last = re.lastIndex;
      if (m[1]) out += '<span class="token comment">' + escapeHtml(m[1]) + "</span>";
      else if (m[2]) out += '<span class="token string">' + escapeHtml(m[2]) + "</span>";
      else if (m[3]) out += '<span class="token number">' + escapeHtml(m[3]) + "</span>";
      else {
        const w = m[4];
        if (kw.has(w)) out += '<span class="token keyword">' + escapeHtml(w) + "</span>";
        else if (["true", "false", "null", "None", "True", "False", "undefined"].indexOf(w) >= 0)
          out += '<span class="token boolean">' + escapeHtml(w) + "</span>";
        else out += escapeHtml(w);
      }
    }
    out += escapeHtml(line.slice(last));
    return out;
  }
  function highlightCode(content, lang) {
    if (!content) return "";
    const kw = _kwset(lang);
    const doHl = lang && lang !== "text";
    return content.split("\n").map((line, i) =>
      '<span class="ln">' + (i + 1) + "</span>" + (doHl ? _hlLine(line, lang, kw) : escapeHtml(line))
    ).join("\n");
  }

  function renderOpDetail(o) {
    if (o.type === "shot") {
      return (o.target ? '<div class="op-path">' + escapeHtml(o.target) + "</div>" : "") +
        (o.image_path
          ? '<img class="op-shot" src="/api/shot?path=' + encodeURIComponent(o.image_path) + '" alt="لقطة شاشة"/>'
          : '<div class="muted small">لا صورة.</div>');
    }
    if (o.type === "edit") {
      const lang = detectLang(o.path, o.before || o.after || "");
      return '<div class="op-path">' + escapeHtml(o.path) + "</div>" +
        '<div class="op-lang-badge">' + escapeHtml(lang) + "</div>" +
        renderDiff(o.before || "", o.after || "", lang);
    }
    if (o.type === "create" || o.type === "read") {
      const lang = detectLang(o.path, o.content || "");
      return '<div class="op-path">' + escapeHtml(o.path) + "</div>" +
        '<div class="op-lang-badge">' + escapeHtml(lang) + "</div>" +
        '<pre class="op-code hl"><code>' + highlightCode(o.content || "", lang) + "</code></pre>";
    }
    if (o.type === "run") {
      return '<div class="op-sec-label">الأمر (Command)</div>' +
        '<pre class="op-code op-cmd">' + escapeHtml(o.command || "") + "</pre>" +
        '<div class="op-sec-label">المخرجات (Output)</div>' +
        '<pre class="op-code op-out">' + escapeHtml(o.output || "") + "</pre>";
    }
    return '<pre class="op-code">' + escapeHtml(JSON.stringify(o, null, 2)) + "</pre>";
  }

  // diff view: تمييز الأسطر المضافة/المحذوفة بألوان + أرقام + تلوين الكود
  function renderDiff(before, after, lang) {
    const a = before.split("\n"), b = after.split("\n");
    const rows = [];
    const setB = new Set(b);
    const setA = new Set(a);
    const kw = lang ? _kwset(lang) : null;
    const hl = (ln) => (lang && lang !== "text") ? _hlLine(ln, lang, kw) : escapeHtml(ln);
    // نعرض المحذوف ثم المضاف بأسلوب موحّد مقروء
    a.forEach((ln, idx) => {
      if (!setB.has(ln)) rows.push('<div class="dl del"><span class="ln">-' + (idx + 1) + '</span>' + hl(ln) + "</div>");
      else rows.push('<div class="dl ctx"><span class="ln">' + (idx + 1) + "</span>" + hl(ln) + "</div>");
    });
    b.forEach((ln, idx) => {
      if (!setA.has(ln)) rows.push('<div class="dl add"><span class="ln">+' + (idx + 1) + '</span>' + hl(ln) + "</div>");
    });
    return '<div class="op-diff">' + rows.join("") + "</div>";
  }
  function numberLines(s) {
    return s.split("\n").map((l, i) =>
      '<span class="ln">' + (i + 1) + "</span>" + escapeHtml(l)).join("\n");
  }
  $$("[data-opclose]").forEach((b) => b.onclick = () => $("#opDetailModal").classList.remove("open"));
  $("#opDetailModal").addEventListener("click", (e) => { if (e.target.id === "opDetailModal") $("#opDetailModal").classList.remove("open"); });
  $("#opDetailBack") && ($("#opDetailBack").onclick = () => $("#opDetailModal").classList.remove("open"));

  // ── شريط نشاط Git/GitHub (commits + PRs) — بطاقات + Show N more + polling ──
  let gitActShown = 20;   // عدد العناصر المعروضة (يتوسّع بـ Show N more)
  const CI_BADGE = {
    success: { t: "CI ✓", c: "ci-ok" }, failure: { t: "CI ✗", c: "ci-fail" },
    pending: { t: "CI …", c: "ci-run" }, unknown: { t: "CI", c: "ci-unknown" },
  };
  function gitCard(a) {
    const add = a.added != null ? '<span class="ab-added">+' + a.added + "</span>" : "";
    const rem = a.removed != null ? '<span class="ab-removed">-' + a.removed + "</span>" : "";
    let badge = "";
    if (a.kind === "pr") {
      if (a.state === "merged") badge = '<span class="git-badge merged">Merged</span>';
      else if (a.state === "closed") badge = '<span class="git-badge closed">Closed</span>';
      else badge = '<span class="git-badge open">Open</span>';
      const ci = CI_BADGE[a.ci] || CI_BADGE.unknown;
      badge += '<span class="git-badge ' + ci.c + '"><span class="ci-dot"></span>' + ci.t + "</span>";
    }
    const num = a.kind === "pr" ? "#" + (a.number || "") : (a.hash || "").slice(0, 7);
    const cls = "git-card" + (a.pending ? " pending" : "") + (a.kind === "pr" ? " is-pr" : "");
    const title = a.kind === "pr" ? (a.title || "") : (a.message || "");
    return '<div class="' + cls + '"' + (a.url ? ' data-url="' + escapeHtml(a.url) + '"' : "") + ">" +
      '<div class="git-card-top"><span class="git-num">' + escapeHtml(num) + "</span>" +
      (a.pending ? '<span class="git-badge pending-b">معلّق</span>' : "") + badge + "</div>" +
      '<div class="git-card-msg">' + escapeHtml(title.slice(0, 70)) + "</div>" +
      '<div class="git-card-meta">' +
        (a.repo ? '<span class="git-repo">' + escapeHtml(a.repo) + "</span>" : "") +
        (a.branch ? '<span class="git-branch">⑂ ' + escapeHtml(a.branch) + "</span>" : "") +
        add + rem + "</div></div>";
  }
  async function loadGitActivity(refresh) {
    const bar = $("#gitActBar");
    if (!bar) return;
    try {
      const r = await api("/api/git-activity?limit=" + gitActShown +
        "&offset=0" + (refresh ? "&refresh=1" : ""));
      const acts = r.activity || [];
      $("#gitActMeta").textContent = (r.repo || "محلي") + " · " + (r.total || 0) +
        (r.token ? "" : " · (بلا توكن: commits فقط)");
      bar.innerHTML = acts.length
        ? acts.map(gitCard).join("")
        : '<span class="muted small">لا نشاط Git بعد.</span>';
      bar.querySelectorAll("[data-url]").forEach((el) =>
        el.onclick = () => window.open(el.dataset.url, "_blank"));
      const more = $("#gitActMore");
      if (r.has_more) { more.style.display = "inline-block"; more.textContent = "عرض المزيد ↓"; }
      else more.style.display = "none";
    } catch (e) {
      bar.innerHTML = '<span class="muted small">تعذّر جلب النشاط.</span>';
    }
  }
  $("#gitActMore") && ($("#gitActMore").onclick = () => { gitActShown += 20; loadGitActivity(); });
  $("#gitActToggle") && ($("#gitActToggle").onclick = () => {
    const body = $("#gitActBody"), caret = $("#gitActCaret");
    const open = body.style.display !== "none";
    body.style.display = open ? "none" : "block";
    caret.textContent = open ? "▸" : "▾";
  });
  // polling دوري خفيف عندما تكون اللوحة مفتوحة (لا يُثقل عند إغلاقها)
  setInterval(() => {
    if ($("#v-dashboard") && $("#v-dashboard").classList.contains("active")) loadGitActivity(true);
  }, 15000);
  $("#planToggle") && ($("#planToggle").onclick = async () => {
    const cur = $("#planState").classList.contains("on");
    const r = await post("/api/plan/toggle", { on: !cur });
    $("#planMsg").textContent = r.message || "";
    loadDashboard();
  });
  $("#planApprove") && ($("#planApprove").onclick = async () => {
    const r = await post("/api/plan/approve", {});
    $("#planMsg").textContent = r.message || r.error || "";
    if (r.ok) { loadDashboard(); go("v-chat"); }
  });

  // ── البثّ الحيّ (SSE) → يظهر داخل شاشة المحادثة ──
  // ملاحظة (streaming): المزوّد عبر daemon لا يبثّ توكِناً بتوكِن، لكن أحداث
  // التفكير/الأدوات تصل لحظياً عبر SSE — فنعرض مؤشراً حيّاً «✻ يفكّر…» كما في
  // Claude Code، ويختفي عند اكتمال الرد (بديل صادق عن انتظار صامت).
  const EV_ICON = { thinking: "⟳", tool_start: "🔧", file_view: "📄", file_edit: "✏️", file_create: "📄", bash_run: "💻", error: "❌", done: "✅" };
  const LIVE_WORD = { thinking: "يفكّر", tool_start: "يستخدم أداة", file_view: "يقرأ",
                      file_edit: "يعدّل", file_create: "ينشئ", bash_run: "ينفّذ" };
  // أثناء العمل: شبكة WeaverCode «المتحركة» (GIF بكامل حركتها) + كلمة الحالة.
  // عند التوقف: الشبكة «الثابتة» (PNG) وحدها — كما طلب المستخدم.
  const LIVE_GIF = "/static/weaver-live.gif", IDLE_PNG = "/static/weaver-idle.png";

  // ── تفاصيل Action Block: popup بأيقونات SVG عصرية (كواجهة Claude Code) ──
  let actionBlocks = [];
  let pendingBlocks = [];   // كتل العمليات للدور الحالي (تُرفَق برد المساعد للحفظ)
  let turnBlocks = [];      // كتل الدور الحالي (لبطاقة ملخّص الإنجاز عند الاكتمال)
  // ── رقاقة «N · Pull requests» بعد الاكتمال + لوحة عرضها (كواجهة Claude Code) ──
  function closePrPanel() {
    ["prPanel", "prBackdrop"].forEach((id) => { const e = document.getElementById(id); if (e) e.remove(); });
  }
  function openPrPanel(prs) {
    closePrPanel();
    const bd = document.createElement("div"); bd.id = "prBackdrop"; bd.className = "adx-backdrop";
    bd.onclick = closePrPanel; document.body.appendChild(bd);
    const el = document.createElement("div"); el.id = "prPanel"; el.className = "pr-panel";
    el.innerHTML = '<div class="pr-head"><span class="pr-h-title">Pull requests</span>' +
      '<button class="pr-close" aria-label="إغلاق">✕</button></div>' +
      '<div class="pr-list">' + prs.map(gitCard).join("") + "</div>";
    document.body.appendChild(el);
    el.querySelector(".pr-close").onclick = closePrPanel;
    el.querySelectorAll("[data-url]").forEach((c) => c.onclick = () => window.open(c.dataset.url, "_blank"));
  }
  async function maybeAddPrChip() {
    try {
      const r = await api("/api/git-activity?limit=100");
      // نعرض فقط الطلبات المفتوحة/المعلّقة (القابلة للتنفيذ) — لا نُظهر المدموجة/
      // المغلقة القديمة كأنها إنجاز حديث (سبق أن ظهرت «وهمية»). العمل الحديث يذهب
      // إلى main كـ commits لا PRs، فلا تظهر رقاقة إن لم توجد طلبات مفتوحة.
      const open = (r.activity || []).filter(
        (a) => a.kind === "pr" && (a.state === "open" || a.pending));
      const old = document.querySelector(".pr-chip-row"); if (old) old.remove();
      if (!open.length) return;
      const el = document.createElement("div"); el.className = "pr-chip-row";
      el.innerHTML = '<button class="pr-chip"><span class="pr-branch">⑂</span> ' +
        open.length + " · Pull requests</button>";
      const live = $("#inlineLive");
      if (live) live.insertAdjacentElement("beforebegin", el);
      else $("#chatMsgs").appendChild(el);
      el.querySelector(".pr-chip").onclick = () => openPrPanel(open);
      scrollChat();
    } catch (e) {}
  }
  // بطاقة ملخّص الإنجاز — تظهر بعد اكتمال العمل بدل كلمة «اكتملت» (كواجهة Claude Code)
  function completionSummaryHtml(blocks) {
    let added = 0, removed = 0, cmds = 0, reads = 0, commits = 0, failed = 0;
    const files = [], shots = [];
    (blocks || []).forEach((b) => (b.ops || []).forEach((o) => {
      added += o.lines_added || 0; removed += o.lines_removed || 0;
      if (o.failed) failed++;
      if (o.image_path && shots.indexOf(o.image_path) < 0) shots.push(o.image_path);
      const tn = o.tool_name;
      if (tn === "Write" || tn === "Edit" || tn === "MultiEdit") {
        const f = o.path || o.arg; if (f && files.indexOf(f) < 0) files.push(f);
      } else if (tn === "Bash" || tn === "PythonRun") cmds++;
      else if (tn === "Read" || tn === "Glob" || tn === "Grep" || tn === "DirectoryList") reads++;
      else if (tn === "GitCommit" || tn === "GitPush") commits++;
    }));
    if (!blocks || !blocks.length) return '<div class="bubble event">✅ تم</div>';
    const parts = [];
    if (files.length) parts.push(files.length + " ملف");
    if (added || removed) parts.push('<span class="cs-add">+' + added + '</span> <span class="cs-rm">-' + removed + '</span>');
    if (cmds) parts.push(cmds + (cmds > 2 ? " أوامر" : " أمر"));
    if (reads) parts.push(reads + " قراءة");
    if (commits) parts.push(commits + " commit");
    const fileChips = files.slice(0, 6).map((f) =>
      '<span class="cs-file">📄 ' + escapeHtml(f.split("/").pop()) + "</span>").join("");
    const shotImgs = shots.map((s) =>
      '<img class="cs-shot" src="/api/shot?path=' + encodeURIComponent(s) + '" alt="لقطة شاشة"/>').join("");
    return '<div class="complete-card' + (failed ? " has-fail" : "") + '">' +
      '<div class="cs-head"><span class="cs-mark">' + (failed ? "⚠️" : "✅") + '</span>' +
      '<span class="cs-title">' + (failed ? "اكتمل مع تنبيهات" : "اكتمل العمل") + '</span>' +
      (parts.length ? '<span class="cs-stats">' + parts.join(" · ") + "</span>" : "") + "</div>" +
      (fileChips ? '<div class="cs-files">' + fileChips + (files.length > 6 ? '<span class="cs-more">+' + (files.length - 6) + "</span>" : "") + "</div>" : "") +
      (shotImgs ? '<div class="cs-shots">' + shotImgs + "</div>" : "") +
      "</div>";
  }
  // يبني HTML لسطر Action Block ويُسجّل تفاصيله (للنقر → المستوى الثالث).
  // يقبل شكلَي البيانات: SSE (detail/diff_added) والمحفوظ (desc/added).
  function actionBlockHtml(b) {
    const desc = b.desc || b.detail || b.message || "";
    const added = (b.added != null ? b.added : b.diff_added) || 0;
    const removed = (b.removed != null ? b.removed : b.diff_removed) || 0;
    const ops = b.ops || [];
    const hasDiff = removed > 0 || added > 0;
    const diff = hasDiff
      ? '<span class="ab-removed">' + removed + '-</span> <span class="ab-added">+' + added + '</span>&nbsp;&nbsp;'
      : "";
    const failed = ops.some((o) => o.failed);
    const idx = actionBlocks.push({ desc: desc, ops: ops, added: added, removed: removed }) - 1;
    const cls = "action-block" + (failed ? " failed" : "") + (ops.length ? " clickable" : "");
    const attr = ops.length ? ' data-ab="' + idx + '"' : "";
    return '<div class="' + cls + '"' + attr + '>' +
      (failed ? '<span class="ab-warn">⚠️</span> ' : '<span class="ab-arrow">‹</span> ') + diff +
      '<span class="ab-desc">' + escapeHtml(desc) + '</span>' +
      (ops.length ? '<span class="ab-more">⌄</span>' : '') + "</div>";
  }
  const AB_ACTION = { Write: "Created", Edit: "Edited", MultiEdit: "Edited", Read: "Read",
    Bash: "Ran", PythonRun: "Ran", DirectoryList: "Listed", Glob: "Searched", Grep: "Searched",
    GitCommit: "Committed", GitPush: "Pushed", GitClone: "Cloned", GitStatus: "Checked",
    TodoWrite: "Planned", WebFetch: "Fetched", WebSearch: "Searched", PipInstall: "Installed",
    NotebookEdit: "Edited", Screenshot: "Captured" };
  // أيقونات SVG خطّية عصرية (outline · currentColor) — لا إيموجي
  const AB_ICON = {
    edit: '<path d="M4 20h4L18.5 9.5a2.1 2.1 0 0 0-3-3L5 17z"/><path d="M13.5 6.5l3 3"/>',
    run: '<rect x="3" y="4.5" width="18" height="15" rx="2.5"/><path d="M7 9l3.2 3.2L7 15.4"/><path d="M12.5 15.4h4.6"/>',
    read: '<path d="M2 12s3.6-6.8 10-6.8S22 12 22 12s-3.6 6.8-10 6.8S2 12 2 12z"/><circle cx="12" cy="12" r="2.6"/>',
    doc: '<path d="M6.5 2.5h7l4.5 4.5V21a.9.9 0 0 1-.9.9H6.5a.9.9 0 0 1-.9-.9V3.4a.9.9 0 0 1 .9-.9z"/><path d="M13 2.7V7h4.3"/><path d="M8.5 13h7M8.5 16.5h4.5"/>',
    folder: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2h8.5A1.5 1.5 0 0 1 21 8.5v9A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5z"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
    shot: '<rect x="3" y="6" width="18" height="13" rx="2.5"/><circle cx="12" cy="12.5" r="3.2"/><path d="M8.5 6l1.3-2h4.4l1.3 2"/>',
    git: '<circle cx="6" cy="6" r="2.4"/><circle cx="6" cy="18" r="2.4"/><circle cx="18" cy="9" r="2.4"/><path d="M6 8.4v7.2M8.3 7.2A6 6 0 0 0 15.5 9.4M18 11.4V13a3 3 0 0 1-3 3H8.4"/>',
    plan: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01"/>',
    tool: '<path d="M14.5 6.5a3.5 3.5 0 0 1-4.6 4.6L5 16l3 3 4.9-4.9a3.5 3.5 0 0 1 4.6-4.6l-2 2-2-2z"/>' };
  const AB_ICON_FOR = { Write: "doc", Edit: "edit", MultiEdit: "edit", Read: "read",
    Bash: "run", PythonRun: "run", DirectoryList: "folder", Glob: "search", Grep: "search",
    GitCommit: "git", GitPush: "git", GitClone: "git", GitStatus: "git", TodoWrite: "plan",
    WebFetch: "read", WebSearch: "search", PipInstall: "doc", Screenshot: "shot" };
  function abSvg(tool) {
    const k = AB_ICON_FOR[tool] || "tool";
    return '<svg viewBox="0 0 24 24" class="adx-svg" fill="none" stroke="currentColor" ' +
      'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' + (AB_ICON[k] || AB_ICON.tool) + '</svg>';
  }
  function closeActionDetail() {
    const o = $("#actionDetailPop"); if (o) o.remove();
    const b = $("#actionDetailBackdrop"); if (b) b.remove();
  }
  let _abCurrent = null;   // الدفعة المعروضة حالياً (للرجوع من تفاصيل عملية)
  function _ensureAbPop() {
    let pop = $("#actionDetailPop");
    if (!pop) {
      // خلفية شفّافة تلتقط النقر خارج النافذة (أمتن من مراقبة النقر على المستند)
      const bd = document.createElement("div");
      bd.id = "actionDetailBackdrop"; bd.className = "adx-backdrop";
      bd.onclick = closeActionDetail;
      document.body.appendChild(bd);
      pop = document.createElement("div");
      pop.id = "actionDetailPop"; pop.className = "adx-pop";
      document.body.appendChild(pop);
    }
    return pop;
  }
  // هل للعملية تفاصيل «ماذا فعل» (أمر/مخرجات/محتوى/فرق)؟
  function opHasDetail(op) {
    return !!(op && (op.command || op.output || op.content || op.before || op.after || op.image_path));
  }
  // تحويل عملية SSE إلى كائن يفهمه renderOpDetail (المستوى الثالث المشترك)
  function opToDetailObj(op) {
    const tn = op.tool_name;
    if (tn === "Screenshot")
      return { type: "shot", image_path: op.image_path || "", target: op.target || op.arg || "" };
    if (tn === "Bash" || tn === "PythonRun")
      return { type: "run", command: op.command || op.arg || "", output: op.output || "" };
    if (tn === "Write")
      return { type: "create", path: op.path || op.arg || "", content: op.content || "" };
    if (tn === "Edit" || tn === "MultiEdit")
      return { type: "edit", path: op.path || op.arg || "", before: op.before || "", after: op.after || "" };
    if (tn === "Read" || tn === "Glob" || tn === "Grep" || tn === "DirectoryList")
      return { type: "read", path: op.path || op.arg || "", content: op.content || "" };
    return { type: "other", command: op.arg || "", output: op.output || "" };
  }
  // المستوى الثاني: قائمة العمليات (كل صفّ قابل للضغط لعرض «ماذا فعل»)
  function showActionDetail(block) {
    if (!block) return;
    _abCurrent = block;
    const pop = _ensureAbPop();
    const ops = block.ops || [];
    const rows = ops.map((op, i) => {
      const label = AB_ACTION[op.tool_name] || op.tool_name;
      const arg = op.arg || "";
      const nm = arg.indexOf("/") >= 0 ? arg.split("/").pop() : arg;
      const name = nm ? escapeHtml(nm.slice(0, 40)) : escapeHtml(op.tool_name);
      const hd = (op.lines_removed || 0) > 0 || (op.lines_added || 0) > 0;
      const diff = hd
        ? '<span class="adx-rm">' + (op.lines_removed || 0) + '-</span> <span class="adx-add">+' + (op.lines_added || 0) + '</span>'
        : '<span class="adx-none">──</span>';
      const can = opHasDetail(op);
      const rowCls = "adx-row" + (op.failed ? " failed" : "") + (can ? " has-detail" : "");
      const attr = can ? ' data-op="' + i + '"' : "";
      return '<div class="' + rowCls + '"' + attr + '>' +
        '<span class="adx-ic">' + (op.failed ? "⚠️" : abSvg(op.tool_name)) + '</span>' +
        '<span class="adx-act">' + escapeHtml(label) + (op.failed ? " · فشل" : "") + '</span>' +
        '<span class="adx-name" title="' + escapeHtml(arg) + '">' + name + '</span>' +
        '<span class="adx-diff">' + diff + (can ? ' <span class="adx-caret">›</span>' : '') + '</span></div>';
    }).join("");
    const ta = ops.reduce((s, o) => s + (o.lines_added || 0), 0);
    const tr = ops.reduce((s, o) => s + (o.lines_removed || 0), 0);
    const stats = ops.length ? '<div class="adx-stats">' + ops.length + ' عملية · +' + ta + ' -' + tr + ' سطر</div>' : '';
    pop.innerHTML =
      '<div class="adx-head"><span class="adx-title">' + escapeHtml(block.desc || "تفاصيل العمليات") + '</span>' +
      '<button class="adx-close" aria-label="إغلاق">✕</button></div>' +
      '<div class="adx-rows">' + (rows || '<div class="adx-empty">لا تفاصيل متاحة</div>') + '</div>' + stats;
    pop.querySelector(".adx-close").onclick = closeActionDetail;
    pop.querySelectorAll("[data-op]").forEach((r) => {
      r.onclick = () => { const op = ops[+r.dataset.op]; if (opHasDetail(op)) showOpDetail(op); };
    });
  }
  // المستوى الثالث: «ماذا فعل» لعملية واحدة (أمر+مخرجات / محتوى / فرق) — كواجهة Claude Code
  function showOpDetail(op) {
    const pop = _ensureAbPop();
    const label = AB_ACTION[op.tool_name] || op.tool_name;
    pop.innerHTML =
      '<div class="adx-head"><button class="adx-back" aria-label="رجوع">‹</button>' +
      '<span class="adx-title">' + escapeHtml(label) + ' · <span class="adx-done">مكتمل</span></span>' +
      '<button class="adx-close" aria-label="إغلاق">✕</button></div>' +
      '<div class="adx-detail">' + renderOpDetail(opToDetailObj(op)) + '</div>';
    pop.querySelector(".adx-back").onclick = () => showActionDetail(_abCurrent);
    pop.querySelector(".adx-close").onclick = closeActionDetail;
    pop.scrollTop = 0;
  }

  // مؤشر الحالة الحيّ يظهر داخل مجرى المحادثة أسفل آخر رسالة (كما في Claude Code)
  // — لا مثبّتاً في الأسفل قرب لوحة الكتابة.
  // كلمات حالة متبدّلة (بأسلوب Claude Code) — مع إبقاء أيقونة WeaverCode المتحركة
  const LIVE_ROTATE = ["يفكّر", "يحلّل", "ينسج الخيوط", "يخطّط", "يتأمّل",
    "يرتّب الأفكار", "يبتكر", "يدقّق", "يعالج", "يستكشف", "يوصّل الأطراف"];
  let _liveTimer = null, _liveIdx = 0;
  function _liveWordText(t) {
    const w = document.querySelector("#inlineLive .live-word");
    if (w) w.textContent = t;
    const dl = $("#dashLive");
    if (dl && t) dl.innerHTML = '<img class="live-icon" src="' + LIVE_GIF + '"/> ' + escapeHtml(t) + "…";
  }
  function _stopRotate() { if (_liveTimer) { clearInterval(_liveTimer); _liveTimer = null; } }
  function setLive(word) {
    const msgs = $("#chatMsgs");
    let row = $("#inlineLive");
    if (word) {
      if (!row && msgs) {
        row = document.createElement("div");
        row.id = "inlineLive"; row.className = "inline-live";
        row.innerHTML = '<img class="live-icon" src="' + LIVE_GIF + '"/>' +
          '<span class="live-word"></span><span class="live-dots"></span>';
        msgs.appendChild(row);
      }
      if (row) msgs.appendChild(row);   // أبقِه دائماً في الأسفل
      _liveWordText(word);
      // ابدأ تدوير الكلمات (كل ~2.6ث) إن لم يكن يعمل
      if (!_liveTimer) {
        _liveIdx = 0;
        _liveTimer = setInterval(() => {
          _liveIdx = (_liveIdx + 1) % LIVE_ROTATE.length;
          _liveWordText(LIVE_ROTATE[_liveIdx]);
        }, 2600);
      }
      scrollChat();
    } else {
      _stopRotate();
      if (row) row.remove();
      const dl = $("#dashLive");
      if (dl) dl.innerHTML = '<img class="live-icon" src="' + IDLE_PNG + '"/> <span class="muted small">لا مهمة قيد التنفيذ.</span>';
    }
  }
  // يُدرِج محتوى المحادثة قبل مؤشر الحالة الحيّ ليبقى المؤشر دائماً في الأسفل.
  function chatAppend(html) {
    const live = $("#inlineLive");
    if (live) live.insertAdjacentHTML("beforebegin", html);
    else $("#chatMsgs").insertAdjacentHTML("beforeend", html);
  }
  function connectSSE() {
    const es = new EventSource("/events");
    es.onmessage = (ev) => {
      let d; try { d = JSON.parse(ev.data); } catch (e) { return; }
      // مؤشر الحالة الحيّ: يظهر مع أحداث العمل ويختفي عند الاكتمال/الخطأ
      // وزر الإرسال يتحوّل «توقيف» أثناء العمل ويعود «إرسال» عند الانتهاء.
      if (LIVE_WORD[d.type]) { setLive(LIVE_WORD[d.type]); setRunning(true); }
      else if (d.type === "response" || d.type === "done" || d.type === "error") setLive(null);
      if (d.type === "done" || d.type === "error") setRunning(false);
      // عند اكتمال مهمة، حدّث قائمة الجلسات إن كانت ظاهرة
      if (d.type === "done") { refreshStatus(); if ($("#v-sessions").classList.contains("active")) loadSessions(); if ($("#v-dashboard").classList.contains("active")) loadDashboard(); }
      const chat = $("#v-chat");
      if (!chat.classList.contains("active")) { return; }
      if (d.type === "response") {
        const txt = d.detail || d.message;
        chatAppend(bubble("agent", md(txt)));
        // أرفق كتل العمليات المتراكمة بردّ المساعد ليُحفَظ ويُسترجَع بعد التحديث
        const entry = { role: "assistant", content: txt };
        if (pendingBlocks.length) { entry.blocks = pendingBlocks.slice(); pendingBlocks = []; }
        chatHistory.push(entry);
      } else if (d.type === "done") {
        // بدل «اكتملت»: بطاقة ملخّص إنجاز (ملفات + أسطر + أوامر) كواجهة Claude Code
        chatAppend(completionSummaryHtml(turnBlocks));
        pendingBlocks = []; turnBlocks = [];
        maybeAddPrChip();   // رقاقة «N · Pull requests» إن وُجدت PRs
      } else if (d.type === "action_block") {
        // ملخص جولة الأدوات (قابل للضغط → المستوى الثالث). يُتراكم للحفظ + الملخّص.
        const blk = { desc: d.detail || d.message, ops: d.ops || [],
          added: d.diff_added || 0, removed: d.diff_removed || 0 };
        pendingBlocks.push(blk); turnBlocks.push(blk);
        chatAppend(actionBlockHtml(d));
      } else if (d.type !== "status") {
        const ic = EV_ICON[d.type] || "•";
        chatAppend('<div class="bubble event">' + ic + " " + escapeHtml(d.message) + (d.detail ? " · " + escapeHtml(d.detail.slice(0, 50)) : "") + "</div>");
      }
      scrollChat();
    };
  }
  connectSSE();

  // ── وضع الإذن: يسأل قبل الأدوات الحسّاسة (كواجهة Claude Code) ──
  // نستطلع الطلب المعلّق أثناء العمل ونعرض حواراً «سماح/رفض». افتراضياً معطّل.
  const PERM_LABEL = { Bash: "تنفيذ أمر (Bash)", PythonRun: "تشغيل بايثون",
    Write: "إنشاء/كتابة ملف", Edit: "تعديل ملف", MultiEdit: "تعديل ملف",
    GitPush: "رفع إلى GitHub", GitCommit: "حفظ commit", GitClone: "استنساخ مستودع" };
  let _permSeen = null;
  function closePermDialog() {
    ["permDialog", "permBackdrop"].forEach((id) => { const e = document.getElementById(id); if (e) e.remove(); });
  }
  function showPermDialog(p) {
    closePermDialog();
    const bd = document.createElement("div"); bd.id = "permBackdrop"; bd.className = "perm-backdrop";
    document.body.appendChild(bd);
    const el = document.createElement("div"); el.id = "permDialog"; el.className = "perm-dialog";
    const label = PERM_LABEL[p.name] || p.name;
    el.innerHTML =
      '<div class="perm-title">🔐 طلب إذن</div>' +
      '<div class="perm-body">يريد الوكيل تنفيذ: <b>' + escapeHtml(label) + "</b>" +
      (p.arg ? '<pre class="perm-arg">' + escapeHtml(p.arg) + "</pre>" : "") + "</div>" +
      '<div class="perm-actions">' +
        '<button class="perm-btn deny" data-d="deny">رفض</button>' +
        '<button class="perm-btn once" data-d="allow_once">سماح مرّة</button>' +
        '<button class="perm-btn always" data-d="allow_always">سماح دائماً</button>' +
      "</div>";
    document.body.appendChild(el);
    el.querySelectorAll("[data-d]").forEach((b) => b.onclick = async () => {
      try { await post("/api/permission", { id: p.id, decision: b.dataset.d }); } catch (e) {}
      closePermDialog(); _permSeen = null;
    });
  }
  async function pollPermission() {
    if (!taskRunning) { if (_permSeen) { _permSeen = null; closePermDialog(); } return; }
    try {
      const r = await api("/api/permission/pending");
      const p = r && r.pending;
      if (p && p.id !== _permSeen) { _permSeen = p.id; showPermDialog(p); }
      else if (!p && _permSeen) { _permSeen = null; closePermDialog(); }
    } catch (e) {}
  }
  setInterval(pollPermission, 1200);

  // ── الملفات ──
  async function loadFiles() {
    const r = await api("/api/files");
    $("#outputsDir").textContent = (r.repo ? "📦 مستودع: " + r.repo + " · " : "") +
      (r.count || 0) + " ملف · " + (r.outputs_dir || "");
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

  // ── الإعدادات (مزامنة مع config/.env) ──
  async function loadSettings() {
    const r = await api("/api/settings"); const s = r.settings || {};
    $("#modelInput").value = s.WEAVER_MODEL || "";
    if ($("#baseUrlInput")) $("#baseUrlInput").value = s.WEAVER_BASE_URL || "";
    if ($("#maxTokensInput")) $("#maxTokensInput").value = s.WEAVER_MAX_TOKENS || "";
    if ($("#askPermToggle")) $("#askPermToggle").checked =
      String(s.WEAVER_ASK_PERMISSION || "0").toLowerCase() in { "1": 1, "true": 1, "yes": 1, "on": 1 };
    $("#keyInput").value = ""; $("#keyInput").placeholder = s.WEAVER_API_KEY || "WEAVER_API_KEY";
  }
  $("#askPermToggle") && ($("#askPermToggle").onchange = async (e) => {
    await post("/api/settings", { WEAVER_ASK_PERMISSION: e.target.checked ? "1" : "0" });
    $("#settingsMsg").textContent = e.target.checked
      ? "🔐 وضع الإذن مُفعّل — سيسألك قبل الأدوات الحسّاسة."
      : "▶️ وضع الإذن معطّل — تنفيذ تلقائي.";
  });
  $("#keyToggle").onclick = () => { const k = $("#keyInput"); k.type = k.type === "password" ? "text" : "password"; };
  $("#providerSel").onchange = async (e) => { if (!e.target.value) return; await post("/api/command", { command: "/provider " + e.target.value }); loadSettings(); refreshStatus(); };
  $("#saveSettings").onclick = async () => {
    const body = {};
    if ($("#modelInput").value.trim()) body.WEAVER_MODEL = $("#modelInput").value.trim();
    if ($("#baseUrlInput") && $("#baseUrlInput").value.trim()) body.WEAVER_BASE_URL = $("#baseUrlInput").value.trim();
    if ($("#maxTokensInput") && $("#maxTokensInput").value.trim()) body.WEAVER_MAX_TOKENS = $("#maxTokensInput").value.trim();
    if ($("#keyInput").value.trim()) body.WEAVER_API_KEY = $("#keyInput").value.trim();
    const r = await post("/api/settings", body);
    let msg = r.saved && r.saved.length
      ? "✅ حُفظت: " + r.saved.join("، ") : (r.error ? "❌ " + r.error : "✅ حُفظت.");
    if (r.detected_platform) msg += " · كُشفت المنصة: " + r.detected_platform + " (اضغط «اكتشاف النماذج»)";
    $("#settingsMsg").textContent = msg;
    refreshStatus(); loadSettings();
  };
  $("#testConn").onclick = async () => { $("#settingsMsg").textContent = "…جارٍ الاختبار"; const r = await post("/api/settings/test-connection", {}); $("#settingsMsg").textContent = (r.success ? "✅ " : "❌ ") + (r.output || ""); };

  // ── اكتشاف النماذج المتاحة فعلاً من المزوّد (بلا نماذج وهمية) ──
  function renderModelsList(models) {
    const list = $("#modelsList");
    const cur = ($("#modelInput").value || "").trim();
    list.innerHTML = models.map((m) =>
      '<button class="model-item' + (m === cur ? " sel" : "") + '" data-model="' +
      escapeHtml(m) + '">' + escapeHtml(m) + "</button>").join("");
    list.querySelectorAll("[data-model]").forEach((el) =>
      el.onclick = () => selectModel(el.dataset.model));
  }
  function selectModel(name) {
    $("#modelInput").value = name;
    $("#modelsList").querySelectorAll(".model-item").forEach((el) =>
      el.classList.toggle("sel", el.dataset.model === name));
  }
  async function discoverModels() {
    const btn = $("#discoverModels"), list = $("#modelsList");
    if (!btn || !list) return;
    btn.disabled = true; const label = btn.textContent;
    btn.textContent = "⏳ جارٍ الاكتشاف…"; list.innerHTML = "";
    try {
      const r = await post("/api/models/discover", {});
      if (r.error) { list.innerHTML = '<div class="muted small">❌ ' + escapeHtml(r.error) + "</div>"; return; }
      const models = r.models || [];
      if (!models.length) { list.innerHTML = '<div class="muted small">لم يُعثَر على نماذج.</div>'; return; }
      if (r.switched_to) {  // اكتُشفت المنصة من المفتاح وتبدّل الرابط تلقائياً
        const note = document.createElement("div");
        note.className = "muted small"; note.style.color = "var(--orange)";
        note.textContent = "⟳ كُشفت المنصة تلقائياً: " + r.switched_to + " · " + (r.base_url || "");
        list.appendChild(note);
        loadSettings();  // حدّث حقل الرابط
      }
      renderModelsList(models);
    } catch (e) {
      list.innerHTML = '<div class="muted small">❌ تعذّر الاكتشاف.</div>';
    } finally { btn.disabled = false; btn.textContent = label; }
  }
  if ($("#discoverModels")) $("#discoverModels").onclick = discoverModels;

  // ── GitHub ──
  let ghRepo = "";
  let activeRepo = null; // المستودع المختار من مستعرض GitHub
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
  let oauthStatus = {};   // GitHub (device flow / one-click)
  let pkceStatus = {};    // خدمات PKCE (canva...) وأيّها مُهيّأ
  async function loadIntegrations() {
    try { oauthStatus = await api("/api/oauth/status"); } catch (e) { oauthStatus = {}; }
    try { pkceStatus = await api("/api/oauth/pkce/services"); } catch (e) { pkceStatus = {}; }
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
  // تدفّق الاتصال: «Allow» بضغطة واحدة → إعداد أول مرة → device flow → توكن
  async function connectIntg(i) {
    const it = intg[i];
    if (!it) return;
    if (it.id === "github") {
      // بضغطة واحدة لمن أضاف تطبيقه الخاص (secret)، وإلا device flow العام للجميع
      if (oauthStatus.github_oneclick) return githubAuthorize();
      const gi = intg.findIndex((x) => x.id === "github");
      return startGithubDeviceFlow(gi);   // يعمل لأي مستخدم بلا إعداد
    }
    // خدمات PKCE (Canva وأمثالها): «Allow» بضغطة واحدة بلا سرّ
    if (pkceStatus[it.id]) {
      if (pkceStatus[it.id].configured) return pkceAuthorize(it.id);
      return openPkceSetup(it.id, it.name);   // أدخل client_id مرة واحدة
    }
    const authUrl = it.auth_url || it.url;
    if (authUrl) window.open(authUrl, "_blank", "noopener");
    openIntgModal(i, true);
  }
  // ── PKCE «Allow» عام (Canva...) ──
  async function pkceAuthorize(service) {
    let r;
    try { r = await api("/api/oauth/pkce/authorize?service=" + encodeURIComponent(service)); } catch (e) { r = {}; }
    if (r.authorize_url) {
      window.open(r.authorize_url, "_blank");   // صفحة «Allow» الحقيقية للخدمة
      pollConnectedAfterReturn(service);
    } else if (r.error) {
      openPkceSetup(service, service);
    }
  }
  // إعداد client_id لخدمة PKCE (مرة واحدة، عام بلا سرّ)
  let _pkceSetupService = "";
  async function openPkceSetup(service, name) {
    _pkceSetupService = service;
    $("#ghSetupModal").querySelector(".modal-head span").textContent = "إعداد اتصال " + (name || service);
    $("#ghCid").value = "";
    $("#ghSec").value = "";
    $("#ghSec").parentElement.style.display = "none";   // PKCE لا يحتاج سرّاً
    $("#ghSetupModal").classList.add("open");
  }
  async function githubAuthorize() {
    let r;
    try { r = await api("/api/oauth/github/authorize"); } catch (e) { r = {}; }
    if (r.authorize_url) {
      window.open(r.authorize_url, "_blank");   // صفحة «Authorize» — ضغطة واحدة
      pollConnectedAfterReturn("github");
    } else if (r.error) {
      openGithubSetup(r.error);
    }
  }
  // ── إعداد GitHub OAuth من الواجهة (بدل تعديل .env) ──
  async function openGithubSetup(errMsg) {
    _pkceSetupService = "";   // وضع GitHub (بسرّ)
    $("#ghSetupModal").querySelector(".modal-head span").textContent = "إعداد اتصال GitHub (متقدّم)";
    let cfg = {};
    try { cfg = (await api("/api/oauth/config")).github || {}; } catch (e) {}
    $("#ghCid").value = cfg.client_id || "";
    $("#ghSec").value = "";
    $("#ghSec").parentElement.style.display = "block";
    $("#ghSec").placeholder = cfg.has_secret ? "محفوظ — اتركه فارغاً للإبقاء عليه" : "يُحفظ محلياً — لا يُرفع";
    $("#ghSetupModal").classList.add("open");
  }
  { const _adv = $("#ghAdvancedSetup"); if (_adv) _adv.onclick = (e) => { e.preventDefault(); openGithubSetup(); }; }
  $$("[data-ghclose]").forEach((b) => b.onclick = () => $("#ghSetupModal").classList.remove("open"));
  $("#ghSetupModal").addEventListener("click", (e) => { if (e.target.id === "ghSetupModal") $("#ghSetupModal").classList.remove("open"); });
  $("#ghSave").onclick = async () => {
    const cid = $("#ghCid").value.trim(), sec = $("#ghSec").value.trim();
    if (!cid) { alert("أدخل Client ID"); return; }
    $("#ghSave").textContent = "…جارٍ الحفظ";
    const svc = _pkceSetupService || "github";
    let body = { service: svc, client_id: cid };
    if (!_pkceSetupService) body.client_secret = sec;   // GitHub فقط يحتاج سرّاً
    try { await post("/api/oauth/config", body); } catch (e) {}
    $("#ghSave").textContent = "حفظ واتصال";
    try { oauthStatus = await api("/api/oauth/status"); pkceStatus = await api("/api/oauth/pkce/services"); } catch (e) {}
    $("#ghSetupModal").classList.remove("open");
    if (_pkceSetupService) {
      if (pkceStatus[svc] && pkceStatus[svc].configured) pkceAuthorize(svc);
    } else if (oauthStatus.github_oneclick) { githubAuthorize(); }
    else if (oauthStatus.github) { const gi = intg.findIndex((x) => x.id === "github"); startGithubDeviceFlow(gi); }
    else alert("حُفظ Client ID.");
  };
  // بعد العودة من «Authorize» (callback حفظ التوكن) نُحدّث البطاقة
  function pollConnectedAfterReturn(id) {
    let tries = 0;
    const t = setInterval(async () => {
      tries++;
      try {
        const r = await api("/api/integrations");
        const it = (r.integrations || []).find((x) => x.id === id);
        if (it && it.connected) { clearInterval(t); intg = r.integrations; renderIntegrations(); }
      } catch (e) {}
      if (tries > 40) clearInterval(t);
    }, 2000);
  }

  // ── تفويض GitHub الحقيقي عبر Device Flow (بلا توكن يدوي) ──
  let _devPoll = null, _devUri = "https://github.com/login/device", _devCodeVal = "";
  function stopDevPoll() { if (_devPoll) { clearInterval(_devPoll); _devPoll = null; } }
  $$("[data-dvclose]").forEach((b) => b.onclick = () => { stopDevPoll(); $("#deviceModal").classList.remove("open"); });
  $("#deviceModal").addEventListener("click", (e) => { if (e.target.id === "deviceModal") { stopDevPoll(); $("#deviceModal").classList.remove("open"); } });
  $("#devOpen").onclick = () => window.open(_devUri, "_blank", "noopener");
  $("#devCopy").onclick = () => { navigator.clipboard.writeText(_devCodeVal).then(() => { $("#devCopy").textContent = "نُسِخ ✓"; setTimeout(() => $("#devCopy").textContent = "نسخ الرمز", 1200); }).catch(() => {}); };
  async function startGithubDeviceFlow(i) {
    $("#devTitle").textContent = "تفويض GitHub";
    $("#devCode").textContent = "…"; $("#devStatus").textContent = "جارٍ البدء…";
    $("#deviceModal").classList.add("open");
    let start;
    try { start = await api("/api/oauth/github/start"); } catch (e) { start = { error: "تعذّر البدء" }; }
    if (start.error) { $("#devStatus").textContent = "❌ " + start.error; return; }
    _devUri = start.verification_uri || "https://github.com/login/device";
    _devCodeVal = start.user_code || "";
    $("#devCode").textContent = _devCodeVal;
    $("#devStatus").textContent = "افتح صفحة GitHub، أدخل الرمز، واضغط Authorize…";
    window.open(_devUri, "_blank", "noopener");   // افتح صفحة التفويض تلقائياً
    const interval = Math.max(5, start.interval || 5);
    const deadline = Date.now() + (start.expires_in || 900) * 1000;
    stopDevPoll();
    _devPoll = setInterval(async () => {
      if (Date.now() > deadline) { stopDevPoll(); $("#devStatus").textContent = "⏱️ انتهت المهلة — أعد المحاولة."; return; }
      let r;
      try { r = await post("/api/oauth/github/poll", { device_code: start.device_code }); } catch (e) { return; }
      if (r.connected) {
        stopDevPoll();
        $("#devStatus").textContent = "✅ تم الاتصال بنجاح!";
        setTimeout(() => { $("#deviceModal").classList.remove("open"); loadIntegrations(); }, 900);
      } else if (r.error) {
        stopDevPoll(); $("#devStatus").textContent = "❌ " + r.error;
      }  // pending → تابع الاستطلاع
    }, interval * 1000);
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

  // استرجاع آخر محادثة تلقائياً عند تحميل/تحديث الصفحة (تصمد عبر التحديث)
  async function restoreLastSession() {
    const savedId = localStorage.getItem("weaver_session_id");
    if (!savedId) return;
    try {
      const r = await api("/api/session?id=" + encodeURIComponent(savedId));
      if (!r || !r.messages || !r.messages.length) {
        localStorage.removeItem("weaver_session_id"); return;
      }
      const firstUser = (r.messages.find((m) => m.role === "user") || {}).content || "محادثة";
      openSession({ id: savedId, prompt: firstUser });   // يعيد العرض والتنقّل
    } catch (e) {
      localStorage.removeItem("weaver_session_id");
    }
  }
  restoreLastSession();
})();
