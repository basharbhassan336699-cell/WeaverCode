// extension.js — امتداد WeaverCode لـ VS Code
// =========================================================================
// يشغّل وكيل WeaverCode (weaver.py) من داخل المحرّر عبر الطرفية المدمجة.
// لا يخزّن أي مفاتيح ولا يمسّ إعدادات المزوّد — يعتمد على بيئة weaver.py نفسها
// (WEAVER_API_KEY / WEAVER_BASE_URL / WEAVER_MODEL من .env أو البيئة).
//
// EN: WeaverCode VS Code extension. Drives the weaver.py CLI through the
// integrated terminal. It never stores API keys or touches provider config —
// weaver.py resolves its own credentials from .env / environment.
// =========================================================================

const vscode = require('vscode');
const fs = require('fs');
const path = require('path');

/** طرفية مشتركة واحدة لكل أوامر WeaverCode. */
let sharedTerminal = null;

/** يقتبس وسيطاً للـ shell بأمان (يمنع كسر الأمر / حقن أوامر). */
function shellQuote(arg) {
  return `'${String(arg).replace(/'/g, `'\\''`)}'`;
}

/** يحدّد جذر مساحة العمل الحالية. */
function workspaceRoot() {
  const folders = vscode.workspace.workspaceFolders;
  if (folders && folders.length > 0) {
    return folders[0].uri.fsPath;
  }
  return undefined;
}

/** يكتشف مسار weaver.py من الإعدادات أو جذر مساحة العمل. */
function resolveWeaverPath() {
  const cfg = vscode.workspace.getConfiguration('weavercode');
  const configured = cfg.get('weaverPath');
  if (configured && fs.existsSync(configured)) {
    return configured;
  }
  const root = workspaceRoot();
  if (root) {
    const candidate = path.join(root, 'weaver.py');
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return undefined;
}

/** يبني بادئة الأمر: python weaver.py [--mode M] [--yes]. */
function baseCommand(weaverPath) {
  const cfg = vscode.workspace.getConfiguration('weavercode');
  const python = cfg.get('pythonPath') || 'python3';
  const mode = cfg.get('mode') || 'main';
  const autoApprove = cfg.get('autoApprove') === true;
  let cmd = `${shellQuote(python)} ${shellQuote(weaverPath)} --mode ${shellQuote(mode)}`;
  if (autoApprove) {
    cmd += ' --yes';
  }
  return cmd;
}

/** يعيد الطرفية المشتركة (أو ينشئها). */
function getTerminal() {
  if (!sharedTerminal || sharedTerminal.exitStatus !== undefined) {
    const cwd = workspaceRoot();
    sharedTerminal = vscode.window.createTerminal({
      name: 'WeaverCode 🕸️',
      cwd: cwd,
    });
  }
  return sharedTerminal;
}

/** يشغّل weaver.py مع مهمة نصّية في الطرفية المدمجة. */
function runInTerminal(taskCommand) {
  const weaverPath = resolveWeaverPath();
  if (!weaverPath) {
    vscode.window.showErrorMessage(
      'WeaverCode: لم يُعثر على weaver.py. اضبط weavercode.weaverPath في الإعدادات.'
    );
    return;
  }
  const terminal = getTerminal();
  terminal.show();
  terminal.sendText(`${baseCommand(weaverPath)} ${taskCommand}`);
}

/** أمر: فتح المحادثة التفاعلية. */
function openChat() {
  const weaverPath = resolveWeaverPath();
  if (!weaverPath) {
    vscode.window.showErrorMessage(
      'WeaverCode: لم يُعثر على weaver.py في مساحة العمل.'
    );
    return;
  }
  const terminal = getTerminal();
  terminal.show();
  terminal.sendText(`${baseCommand(weaverPath)} --interactive`);
}

/** أمر: تنفيذ مهمة يكتبها المستخدم. */
async function runTask() {
  const task = await vscode.window.showInputBox({
    prompt: 'ما المهمة التي تريد من WeaverCode تنفيذها؟',
    placeHolder: 'مثال: راجع core/engine/provider.py وأصلح أي خطأ',
  });
  if (task && task.trim()) {
    runInTerminal(shellQuote(task.trim()));
  }
}

/** أمر: تنفيذ على النص المحدّد في المحرّر. */
function runSelection() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage('WeaverCode: لا يوجد محرّر نشط.');
    return;
  }
  const selection = editor.document.getText(editor.selection);
  if (!selection || !selection.trim()) {
    vscode.window.showWarningMessage('WeaverCode: لا يوجد نص محدّد.');
    return;
  }
  const filePath = editor.document.uri.fsPath;
  const task =
    `بخصوص الملف ${filePath} والمقطع التالي، ` +
    `حلّله واقترح تحسينات:\n\n${selection}`;
  runInTerminal(shellQuote(task));
}

/** أمر: اشرح الملف الحالي. */
function explainFile() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage('WeaverCode: لا يوجد ملف مفتوح.');
    return;
  }
  const filePath = editor.document.uri.fsPath;
  runInTerminal(shellQuote(`اشرح الملف @${filePath} بالتفصيل وبيّن وظيفته.`));
}

/** أمر: فحص الحالة. */
function showStatus() {
  const weaverPath = resolveWeaverPath();
  if (!weaverPath) {
    vscode.window.showErrorMessage('WeaverCode: لم يُعثر على weaver.py.');
    return;
  }
  const cfg = vscode.workspace.getConfiguration('weavercode');
  const python = cfg.get('pythonPath') || 'python3';
  const terminal = getTerminal();
  terminal.show();
  terminal.sendText(`${shellQuote(python)} ${shellQuote(weaverPath)} --version`);
}

/** نقطة التفعيل. */
function activate(context) {
  const commands = [
    ['weavercode.openChat', openChat],
    ['weavercode.runTask', runTask],
    ['weavercode.runSelection', runSelection],
    ['weavercode.explainFile', explainFile],
    ['weavercode.status', showStatus],
  ];
  for (const [id, handler] of commands) {
    context.subscriptions.push(
      vscode.commands.registerCommand(id, handler)
    );
  }
  // تنظيف الطرفية عند إغلاقها
  context.subscriptions.push(
    vscode.window.onDidCloseTerminal((t) => {
      if (t === sharedTerminal) {
        sharedTerminal = null;
      }
    })
  );
}

function deactivate() {
  if (sharedTerminal) {
    sharedTerminal.dispose();
    sharedTerminal = null;
  }
}

module.exports = { activate, deactivate };
