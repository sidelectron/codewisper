"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const path = require("path");
const child_process_1 = require("child_process");
const vscode = require("vscode");
const WS_URL = "ws://localhost:8000/ws/extension";
const RETRY_MS = 5000;
const DEBOUNCE_MS = 500;
const MAX_FILE_BYTES = 100 * 1024;
const EXCLUDED_DIRS = [
    "node_modules",
    ".git",
    "__pycache__",
    "dist",
    "build",
    ".venv",
    "venv",
    ".next",
    "coverage",
];
const BINARY_EXT = new Set([
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".otf",
    ".pdf", ".zip", ".bin", ".exe", ".dll", ".so", ".dylib", ".wasm",
]);
const FIND_FILES_EXCLUDE = "**/node_modules/**,**/.git/**,**/__pycache__/**,**/dist/**,**/build/**,**/.venv/**,**/venv/**,**/.next/**,**/coverage/**";
let socket = null;
let statusBarItem;
let disposables = [];
const pendingDebounce = new Map();
let retryTimer = null;
function getWorkspaceRoot() {
    const folders = vscode.workspace.workspaceFolders;
    return folders?.[0]?.uri;
}
function getRelativePath(uri) {
    const root = getWorkspaceRoot();
    if (!root)
        return uri.fsPath;
    const rel = path.relative(root.fsPath, uri.fsPath);
    return rel.split(path.sep).join("/");
}
function isExcluded(filePath, contentLength) {
    const normalized = filePath.replace(/\\/g, "/").toLowerCase();
    for (const dir of EXCLUDED_DIRS) {
        if (normalized.includes(`/${dir}/`) || normalized.startsWith(`${dir}/`))
            return true;
    }
    const ext = path.extname(normalized).toLowerCase();
    if (BINARY_EXT.has(ext))
        return true;
    if (contentLength !== undefined && contentLength > MAX_FILE_BYTES)
        return true;
    return false;
}
function send(msg) {
    if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(msg));
    }
}
async function getFileList() {
    const root = getWorkspaceRoot();
    if (!root)
        return [];
    const exclude = FIND_FILES_EXCLUDE.split(",").map((s) => s.trim());
    const uris = await vscode.workspace.findFiles("**/*", `{${exclude.join(",")}}`, 10000);
    const rel = [];
    for (const u of uris) {
        const r = getRelativePath(u);
        if (!isExcluded(r))
            rel.push(r);
    }
    return rel;
}
async function sendHandshake() {
    const root = getWorkspaceRoot();
    const workspace = root ? root.fsPath : "";
    const files = await getFileList();
    send({ type: "handshake", workspace, files });
    const editor = vscode.window.activeTextEditor;
    if (editor?.document) {
        const doc = editor.document;
        const r = getRelativePath(doc.uri);
        const text = doc.getText();
        if (!isExcluded(r, text.length)) {
            send({ type: "active_file_changed", path: r, content: text });
        }
    }
}
async function handleCommand(requestId, command, params) {
    const root = getWorkspaceRoot();
    try {
        if (command === "open_file") {
            const p = params?.path;
            if (!p || !root) {
                send({ requestId, data: "Error: path or workspace required" });
                return;
            }
            const uri = vscode.Uri.joinPath(root, p);
            const doc = await vscode.workspace.openTextDocument(uri);
            await vscode.window.showTextDocument(doc);
            send({ requestId, data: "File opened" });
            return;
        }
        if (command === "get_file") {
            const p = params?.path;
            if (!p || !root) {
                send({ requestId, data: "File not found" });
                return;
            }
            const uri = vscode.Uri.joinPath(root, p);
            const doc = await vscode.workspace.openTextDocument(uri);
            const content = doc.getText();
            send({ requestId, data: content });
            return;
        }
        if (command === "list_files") {
            const files = await getFileList();
            send({ requestId, data: JSON.stringify(files) });
            return;
        }
        if (command === "get_git_diff") {
            if (!root?.fsPath) {
                send({ requestId, data: "" });
                return;
            }
            (0, child_process_1.exec)("git diff", { cwd: root.fsPath, maxBuffer: 1024 * 1024 }, (err, stdout, stderr) => {
                send({ requestId, data: err ? (stderr || String(err)) : (stdout || "") });
            });
            return;
        }
        send({ requestId, data: `Unknown command: ${command}` });
    }
    catch (e) {
        send({ requestId, data: `Error: ${e instanceof Error ? e.message : String(e)}` });
    }
}
function clearDebounce() {
    for (const t of pendingDebounce.values())
        clearTimeout(t);
    pendingDebounce.clear();
}
function registerListeners() {
    disposables.push(vscode.workspace.onDidChangeTextDocument((e) => {
        const doc = e.document;
        const r = getRelativePath(doc.uri);
        if (isExcluded(r))
            return;
        const existing = pendingDebounce.get(r);
        if (existing)
            clearTimeout(existing);
        pendingDebounce.set(r, setTimeout(() => {
            pendingDebounce.delete(r);
            const text = doc.getText();
            if (isExcluded(r, text.length))
                return;
            send({ type: "file_changed", path: r, content: text });
        }, DEBOUNCE_MS));
    }));
    disposables.push(vscode.workspace.onDidCreateFiles((e) => {
        for (const f of e.files) {
            const r = getRelativePath(f);
            if (isExcluded(r))
                continue;
            vscode.workspace.openTextDocument(f).then((doc) => {
                const text = doc.getText();
                if (!isExcluded(r, text.length))
                    send({ type: "file_created", path: r, content: text });
            }, () => send({ type: "file_created", path: r, content: "" }));
        }
    }));
    disposables.push(vscode.workspace.onDidDeleteFiles((e) => {
        for (const f of e.files) {
            const r = getRelativePath(f);
            if (!isExcluded(r))
                send({ type: "file_deleted", path: r });
        }
    }));
    disposables.push(vscode.workspace.onDidRenameFiles((e) => {
        for (const { oldUri, newUri } of e.files) {
            const oldPath = getRelativePath(oldUri);
            const newPath = getRelativePath(newUri);
            if (!isExcluded(oldPath) || !isExcluded(newPath)) {
                send({ type: "file_renamed", oldPath, newPath });
            }
        }
    }));
    disposables.push(vscode.workspace.onDidSaveTextDocument((doc) => {
        const r = getRelativePath(doc.uri);
        if (!isExcluded(r))
            send({ type: "file_saved", path: r });
    }));
    disposables.push(vscode.window.onDidChangeActiveTextEditor((editor) => {
        if (!editor?.document)
            return;
        const doc = editor.document;
        const r = getRelativePath(doc.uri);
        const text = doc.getText();
        if (!isExcluded(r, text.length)) {
            send({ type: "active_file_changed", path: r, content: text });
        }
    }));
}
function disconnect() {
    if (socket) {
        try {
            socket.close();
        }
        catch (_) { }
        socket = null;
    }
    statusBarItem.text = "$(plug) CodeWhisper: Disconnected";
    statusBarItem.tooltip = "CodeWhisper IDE Connection";
    clearDebounce();
    disposables.forEach((d) => d.dispose());
    disposables = [];
}
function connect() {
    disconnect();
    const url = vscode.workspace.getConfiguration("codewhisper").get("backendWsUrl") ?? WS_URL;
    try {
        const ws = new WebSocket(url);
        socket = ws;
        ws.onopen = () => {
            statusBarItem.text = "$(check) CodeWhisper: Connected";
            statusBarItem.tooltip = "CodeWhisper IDE Connection";
            sendHandshake();
            registerListeners();
            ws.onmessage = (ev) => {
                try {
                    const msg = JSON.parse(ev.data);
                    if (msg.type === "command" && msg.requestId) {
                        handleCommand(msg.requestId, msg.command || "", msg.params || {});
                    }
                }
                catch (_) { }
            };
        };
        ws.onclose = () => {
            disconnect();
            retryTimer = setTimeout(connect, RETRY_MS);
        };
        ws.onerror = () => {
            disconnect();
            retryTimer = setTimeout(connect, RETRY_MS);
        };
    }
    catch (_) {
        retryTimer = setTimeout(connect, RETRY_MS);
    }
}
function activate(context) {
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left);
    statusBarItem.text = "$(plug) CodeWhisper: Connecting...";
    statusBarItem.tooltip = "CodeWhisper IDE Connection";
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);
    connect();
}
function deactivate() {
    if (retryTimer) {
        clearTimeout(retryTimer);
        retryTimer = null;
    }
    disconnect();
}
