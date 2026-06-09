#!/usr/bin/env python3
"""Local notification-history browser for Codex Notify."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import parse


def default_db_path() -> Path:
    home = Path.home()
    candidates = [
        home
        / ".codex"
        / "plugins"
        / "data"
        / "codex-notify-codex-notify"
        / "notify_history.sqlite3",
        home
        / ".codex"
        / "plugins"
        / "data"
        / "codex-notify-codex-notify-local"
        / "notify_history.sqlite3",
        home
        / ".codex"
        / "plugins"
        / "data"
        / "codex-pushover-notify-codex-pushover-notify"
        / "notify_history.sqlite3",
        home
        / ".codex"
        / "plugins"
        / "data"
        / "codex-pushover-notify-codex-pushover-notify-local"
        / "notify_history.sqlite3",
        home / ".codex" / "codex-notify" / "notify_history.sqlite3",
        home / ".codex" / "codex-pushover-notify" / "notify_history.sqlite3",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


DEFAULT_DB_PATH = default_db_path()

COLUMNS = [
    "id",
    "created_at",
    "turn_id",
    "session_id",
    "request_id",
    "sample",
    "dry_run",
    "policy",
    "reason",
    "status",
    "duration_seconds",
    "title",
    "message",
    "url",
    "url_title",
    "title_chars",
    "message_chars",
    "message_html",
    "cwd",
    "repo",
    "branch",
    "git_sha",
    "git_dirty",
    "model",
    "permission_mode",
    "thread_source",
    "subagent_name",
    "originator",
    "focus_reason",
    "frontmost_app",
    "payload_json",
]
DEFAULT_VISIBLE_COLUMNS = [
    "id",
    "created_at",
    "status",
    "duration_seconds",
    "repo",
    "branch",
    "reason",
    "title",
    "message_chars",
    "url_title",
    "url",
]
SEARCH_COLUMNS = [
    "title",
    "message",
    "url",
    "url_title",
    "repo",
    "branch",
    "cwd",
    "reason",
    "status",
    "model",
    "thread_source",
    "subagent_name",
]

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Notification History</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f8;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #667085;
      --line: #d7dde5;
      --line-strong: #b9c3cf;
      --accent: #0f766e;
      --accent-soft: #e6f4f1;
      --warn: #b42318;
      --good: #1b7f3a;
      --code: #f1f3f5;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 13px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      height: 100vh;
      overflow: hidden;
      display: grid;
      grid-template-rows: auto auto minmax(0, 1fr);
    }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 12px 16px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      z-index: 5;
    }

    h1 {
      margin: 0;
      font-size: 16px;
      font-weight: 650;
      letter-spacing: 0;
    }

    .meta {
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }

    .header-actions {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
      min-width: 0;
    }

    .toolbar {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) 150px 150px 130px 120px auto auto;
      gap: 8px;
      padding: 10px 16px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      z-index: 4;
    }

    input, select, button {
      min-height: 32px;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      padding: 6px 8px;
    }

    button {
      cursor: pointer;
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
      font-weight: 600;
    }

    button.secondary {
      background: #fff;
      color: var(--ink);
      border-color: var(--line-strong);
      font-weight: 500;
    }

    main {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 420px;
      gap: 0;
      min-height: 0;
      overflow: hidden;
    }

    body.detail-collapsed main {
      grid-template-columns: minmax(0, 1fr) 0;
    }

    .table-wrap {
      overflow: auto;
      border-right: 1px solid var(--line);
      background: var(--panel);
      min-width: 0;
      min-height: 0;
    }

    table {
      width: max-content;
      min-width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }

    th, td {
      border-bottom: 1px solid var(--line);
      padding: 7px 8px;
      text-align: left;
      vertical-align: top;
      max-width: 320px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    th {
      position: sticky;
      top: 0;
      z-index: 3;
      background: #eef2f6;
      font-size: 12px;
      color: #344054;
      user-select: none;
      cursor: pointer;
    }

    tbody tr {
      cursor: pointer;
    }

    tbody tr:hover {
      background: #f5faf8;
    }

    tbody tr.selected {
      background: var(--accent-soft);
      outline: 1px solid #99d6cb;
      outline-offset: -1px;
    }

    .status-done { color: var(--good); font-weight: 650; }
    .status-attn { color: var(--warn); font-weight: 650; }

    aside {
      background: var(--panel);
      overflow: auto;
      padding: 14px;
      min-width: 0;
      min-height: 0;
    }

    body.detail-collapsed aside {
      display: none;
    }

    .detail-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
    }

    .detail-title {
      font-size: 14px;
      font-weight: 700;
      word-break: break-word;
    }

    .kv {
      display: grid;
      grid-template-columns: 110px minmax(0, 1fr);
      gap: 5px 8px;
      margin: 10px 0 14px;
    }

    .k {
      color: var(--muted);
      font-size: 12px;
    }

    .v {
      min-width: 0;
      overflow-wrap: anywhere;
    }

    .section {
      margin-top: 14px;
      border-top: 1px solid var(--line);
      padding-top: 12px;
    }

    .section-title {
      margin: 0 0 8px;
      font-size: 12px;
      font-weight: 700;
      color: #344054;
      text-transform: uppercase;
    }

    .rendered-message,
    pre {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      padding: 10px;
      overflow: auto;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    pre {
      background: var(--code);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
    }

    .columns {
      display: flex;
      flex-wrap: wrap;
      gap: 6px 10px;
      max-height: 150px;
      overflow: auto;
      padding: 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
    }

    .columns label {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      color: #344054;
      font-size: 12px;
      white-space: nowrap;
    }

    .empty {
      padding: 28px;
      color: var(--muted);
    }

    @media (max-width: 980px) {
      .toolbar {
        grid-template-columns: 1fr 1fr;
      }

      main {
        grid-template-columns: 1fr;
      }

      body.detail-collapsed main {
        grid-template-columns: 1fr;
      }

      aside {
        border-top: 1px solid var(--line);
      }
    }
  </style>
</head>
<body>
  <header>
    <h1>Notification History</h1>
    <div class="header-actions">
      <button id="togglePanel" class="secondary">Hide detail</button>
      <div class="meta" id="dbMeta">Loading...</div>
    </div>
  </header>

  <section class="toolbar">
    <input id="search" type="search" placeholder="Search title, message, repo, reason...">
    <select id="status"><option value="">All statuses</option></select>
    <select id="repo"><option value="">All repos</option></select>
    <select id="limit">
      <option>25</option>
      <option selected>50</option>
      <option>100</option>
      <option>200</option>
    </select>
    <button id="refresh">Refresh</button>
    <button id="prev" class="secondary">Prev</button>
    <button id="next" class="secondary">Next</button>
  </section>

  <main>
    <section class="table-wrap">
      <table>
        <thead><tr id="head"></tr></thead>
        <tbody id="rows"></tbody>
      </table>
      <div class="empty" id="empty" hidden>No notifications found.</div>
    </section>

    <aside>
      <div class="detail-head">
        <div class="detail-title" id="detailTitle">Select a notification</div>
        <button id="copy" class="secondary">Copy</button>
      </div>

      <div class="kv" id="detailMeta"></div>

      <div class="section">
        <p class="section-title">Rendered Message</p>
        <div class="rendered-message" id="rendered"></div>
      </div>

      <div class="section">
        <p class="section-title">Plain Message</p>
        <pre id="plain"></pre>
      </div>

      <div class="section">
        <p class="section-title">Columns</p>
        <div class="columns" id="columns"></div>
      </div>
    </aside>
  </main>

  <script>
    const allColumns = __COLUMNS__;
    const defaultVisible = __DEFAULT_VISIBLE_COLUMNS__;

    function loadVisibleColumns() {
      let saved = null;
      try {
        saved = JSON.parse(localStorage.getItem("visibleColumns") || "null");
      } catch {
        saved = null;
      }
      if (!Array.isArray(saved)) return new Set(defaultVisible);
      const visible = new Set(saved.filter((column) => allColumns.includes(column)));
      if (localStorage.getItem("visibleColumnsVersion") !== "2") {
        visible.add("url");
        localStorage.setItem("visibleColumns", JSON.stringify([...visible]));
        localStorage.setItem("visibleColumnsVersion", "2");
      }
      return visible;
    }

    const state = {
      rows: [],
      count: 0,
      offset: 0,
      sort: "created_at",
      order: "desc",
      selected: null,
      visible: loadVisibleColumns(),
    };

    const $ = (id) => document.getElementById(id);

    function api(path, params = {}) {
      const url = new URL(path, window.location.origin);
      for (const [key, value] of Object.entries(params)) {
        if (value !== "" && value !== null && value !== undefined) url.searchParams.set(key, value);
      }
      return fetch(url).then((res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        return res.json();
      });
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function formatTime(value) {
      if (!value) return "";
      return new Date(value * 1000).toLocaleString();
    }

    function formatDuration(value) {
      if (value === null || value === undefined || value === "") return "";
      const total = Math.round(Number(value));
      if (Number.isNaN(total)) return "";
      if (total < 60) return `${total}s`;
      const minutes = Math.floor(total / 60);
      const seconds = total % 60;
      if (minutes < 60) return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
      return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
    }

    function formatCell(column, value) {
      if (column === "created_at") return formatTime(value);
      if (column === "duration_seconds") return formatDuration(value);
      if (column === "sample" || column === "dry_run" || column === "message_html") return value ? "yes" : "no";
      return value ?? "";
    }

    function statusClass(value) {
      if (String(value).toLowerCase().includes("attention")) return "status-attn";
      if (String(value).toLowerCase() === "done") return "status-done";
      return "";
    }

    function sanitizePushoverHtml(message) {
      const allowed = new Set(["B", "I", "U", "FONT", "A", "BR"]);
      const parser = new DOMParser();
      const doc = parser.parseFromString(`<div>${message || ""}</div>`, "text/html");

      function walk(node) {
        if (node.nodeType === Node.TEXT_NODE) return escapeHtml(node.textContent);
        if (node.nodeType !== Node.ELEMENT_NODE) return "";
        const tag = node.tagName;
        const body = Array.from(node.childNodes).map(walk).join("");
        if (tag === "DIV" || tag === "BODY" || tag === "HTML") return body;
        if (!allowed.has(tag)) return body;
        if (tag === "BR") return "<br>";
        if (tag === "FONT") {
          const color = node.getAttribute("color") || "";
          const safeColor = /^#[0-9a-fA-F]{6}$/.test(color) ? ` color="${color}"` : "";
          return `<font${safeColor}>${body}</font>`;
        }
        if (tag === "A") {
          const href = node.getAttribute("href") || "";
          const safeHref = /^https?:\\/\\//.test(href) ? ` href="${escapeHtml(href)}" target="_blank" rel="noreferrer"` : "";
          return `<a${safeHref}>${body}</a>`;
        }
        return `<${tag.toLowerCase()}>${body}</${tag.toLowerCase()}>`;
      }

      return Array.from(doc.body.childNodes).map(walk).join("");
    }

    function renderMetaValue(key, value) {
      if (key === "url" && value && /^https?:\\/\\//.test(String(value))) {
        const safeUrl = escapeHtml(value);
        return `<a href="${safeUrl}" target="_blank" rel="noreferrer">${safeUrl}</a>`;
      }
      return escapeHtml(value || "");
    }

    function renderColumns() {
      $("columns").innerHTML = allColumns.map((column) => `
        <label>
          <input type="checkbox" value="${escapeHtml(column)}" ${state.visible.has(column) ? "checked" : ""}>
          ${escapeHtml(column)}
        </label>
      `).join("");

      $("columns").querySelectorAll("input").forEach((input) => {
        input.addEventListener("change", () => {
          if (input.checked) state.visible.add(input.value);
          else state.visible.delete(input.value);
          localStorage.setItem("visibleColumns", JSON.stringify([...state.visible]));
          localStorage.setItem("visibleColumnsVersion", "2");
          renderTable();
        });
      });
    }

    function renderTable() {
      const columns = allColumns.filter((column) => state.visible.has(column));
      $("head").innerHTML = columns.map((column) => {
        const marker = state.sort === column ? (state.order === "asc" ? " ↑" : " ↓") : "";
        return `<th data-column="${escapeHtml(column)}">${escapeHtml(column)}${marker}</th>`;
      }).join("");

      $("head").querySelectorAll("th").forEach((th) => {
        th.addEventListener("click", () => {
          const column = th.dataset.column;
          if (state.sort === column) state.order = state.order === "asc" ? "desc" : "asc";
          else {
            state.sort = column;
            state.order = "desc";
          }
          state.offset = 0;
          loadRows();
        });
      });

      $("rows").innerHTML = state.rows.map((row) => `
        <tr data-id="${row.id}" class="${state.selected && state.selected.id === row.id ? "selected" : ""}">
          ${columns.map((column) => {
            const value = formatCell(column, row[column]);
            const klass = column === "status" ? statusClass(value) : "";
            return `<td class="${klass}" title="${escapeHtml(value)}">${escapeHtml(value)}</td>`;
          }).join("")}
        </tr>
      `).join("");

      $("empty").hidden = state.rows.length > 0;
      $("rows").querySelectorAll("tr").forEach((tr) => {
        tr.addEventListener("click", () => {
          const row = state.rows.find((candidate) => String(candidate.id) === tr.dataset.id);
          handleRowClick(row);
        });
      });
    }

    function setDetailCollapsed(collapsed) {
      document.body.classList.toggle("detail-collapsed", collapsed);
      $("togglePanel").textContent = collapsed ? "Show detail" : "Hide detail";
      localStorage.setItem("detailCollapsed", collapsed ? "1" : "0");
    }

    function handleRowClick(row) {
      if (!row) return;
      const sameRow = state.selected && state.selected.id === row.id;
      selectRow(row);
      setDetailCollapsed(sameRow ? !document.body.classList.contains("detail-collapsed") : false);
    }

    function selectRow(row) {
      state.selected = row;
      renderTable();
      if (!row) return;
      $("detailTitle").textContent = `#${row.id} ${row.title || ""}`;
      const meta = [
        ["created", formatTime(row.created_at)],
        ["status", row.status],
        ["reason", row.reason],
        ["duration", formatDuration(row.duration_seconds)],
        ["repo", [row.repo, row.branch, row.git_sha, row.git_dirty].filter(Boolean).join(" | ")],
        ["chars", `${row.title_chars || 0} title / ${row.message_chars || 0} message`],
        ["request", row.request_id],
        ["url title", row.url_title],
        ["url", row.url],
        ["turn", row.turn_id],
      ];
      $("detailMeta").innerHTML = meta.map(([key, value]) => `
        <div class="k">${escapeHtml(key)}</div><div class="v">${renderMetaValue(key, value)}</div>
      `).join("");
      $("rendered").innerHTML = row.message_html ? sanitizePushoverHtml(row.message || "") : escapeHtml(row.message || "");
      $("plain").textContent = row.message || "";
    }

    async function loadSummary() {
      const summary = await api("/api/summary");
      $("dbMeta").textContent = `${summary.rows} rows | ${summary.db_path}`;
      for (const status of summary.statuses) {
        $("status").insertAdjacentHTML("beforeend", `<option>${escapeHtml(status)}</option>`);
      }
      for (const repo of summary.repos) {
        $("repo").insertAdjacentHTML("beforeend", `<option>${escapeHtml(repo)}</option>`);
      }
    }

    async function loadRows() {
      const limit = Number($("limit").value);
      const data = await api("/api/notifications", {
        search: $("search").value.trim(),
        status: $("status").value,
        repo: $("repo").value,
        limit,
        offset: state.offset,
        sort: state.sort,
        order: state.order,
      });
      state.rows = data.rows;
      state.count = data.count;
      $("dbMeta").textContent = `${data.count} matched | showing ${state.offset + 1}-${Math.min(state.offset + data.rows.length, data.count)} | ${data.db_path}`;
      renderTable();
      if (state.rows.length && (!state.selected || !state.rows.some((row) => row.id === state.selected.id))) {
        selectRow(state.rows[0]);
      } else if (!state.rows.length) {
        state.selected = null;
        $("detailTitle").textContent = "Select a notification";
        $("detailMeta").innerHTML = "";
        $("rendered").innerHTML = "";
        $("plain").textContent = "";
      }
    }

    function debounce(fn, delay) {
      let timer = null;
      return (...args) => {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => fn(...args), delay);
      };
    }

    $("refresh").addEventListener("click", () => loadRows());
    $("prev").addEventListener("click", () => {
      state.offset = Math.max(0, state.offset - Number($("limit").value));
      loadRows();
    });
    $("next").addEventListener("click", () => {
      state.offset = Math.min(Math.max(0, state.count - 1), state.offset + Number($("limit").value));
      loadRows();
    });
    $("copy").addEventListener("click", async () => {
      if (!state.selected) return;
      await navigator.clipboard.writeText(JSON.stringify(state.selected, null, 2));
    });
    $("togglePanel").addEventListener("click", () => {
      setDetailCollapsed(!document.body.classList.contains("detail-collapsed"));
    });
    for (const id of ["status", "repo", "limit"]) {
      $(id).addEventListener("change", () => {
        state.offset = 0;
        loadRows();
      });
    }
    $("search").addEventListener("input", debounce(() => {
      state.offset = 0;
      loadRows();
    }, 220));

    renderColumns();
    if (localStorage.getItem("detailCollapsed") === "1") {
      setDetailCollapsed(true);
    }
    loadSummary().then(loadRows).catch((error) => {
      $("dbMeta").textContent = error.message;
      $("empty").hidden = false;
      $("empty").textContent = error.message;
    });
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="notification history SQLite DB")
    parser.add_argument("--host", default="127.0.0.1", help="bind host")
    parser.add_argument("--port", type=int, default=60605, help="bind port")
    return parser.parse_args()


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def existing_table_columns(conn: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in conn.execute("PRAGMA table_info(notification_history)")}


def selectable_columns(existing: set[str]) -> list[str]:
    return [column for column in COLUMNS if column in existing]


def json_response(handler: BaseHTTPRequestHandler, payload: object, status: int = 200) -> None:
    encoded = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def text_response(
    handler: BaseHTTPRequestHandler,
    body: str,
    *,
    content_type: str = "text/html; charset=utf-8",
    status: int = 200,
) -> None:
    encoded = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def query_values(conn: sqlite3.Connection, column: str, existing: set[str]) -> list[str]:
    if column not in existing:
        return []
    rows = conn.execute(
        f"""
        SELECT DISTINCT {column}
        FROM notification_history
        WHERE {column} IS NOT NULL AND {column} != ''
        ORDER BY {column}
        LIMIT 200
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def build_where(params: dict[str, list[str]], existing: set[str]) -> tuple[str, list[str]]:
    filters: list[str] = []
    values: list[str] = []
    search = first(params, "search")
    status = first(params, "status")
    repo = first(params, "repo")

    searchable = [column for column in SEARCH_COLUMNS if column in existing]
    if search and searchable:
        filters.append(
            "("
            + " OR ".join([f"{column} LIKE ?" for column in searchable])
            + ")"
        )
        values.extend([f"%{search}%"] * len(searchable))
    if status and "status" in existing:
        filters.append("status = ?")
        values.append(status)
    if repo and "repo" in existing:
        filters.append("repo = ?")
        values.append(repo)

    return ("WHERE " + " AND ".join(filters), values) if filters else ("", values)


def first(params: dict[str, list[str]], key: str, default: str = "") -> str:
    values = params.get(key, [])
    return values[0] if values else default


def bounded_int(value: str, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(maximum, max(minimum, parsed))


def summary_payload(conn: sqlite3.Connection, db_path: Path) -> dict[str, object]:
    existing = existing_table_columns(conn)
    row_count = conn.execute("SELECT COUNT(*) FROM notification_history").fetchone()[0]
    return {
        "db_path": str(db_path),
        "rows": row_count,
        "columns": COLUMNS,
        "statuses": query_values(conn, "status", existing),
        "repos": query_values(conn, "repo", existing),
    }


def notifications_payload(
    conn: sqlite3.Connection,
    db_path: Path,
    params: dict[str, list[str]],
) -> tuple[dict[str, object], int]:
    existing = existing_table_columns(conn)
    columns = selectable_columns(existing)
    if not columns:
        return {"error": "notification_history has no known columns"}, 500

    sort = first(params, "sort", "created_at")
    if sort not in existing:
        sort = "created_at" if "created_at" in existing else columns[0]
    order = first(params, "order", "desc").lower()
    order = "ASC" if order == "asc" else "DESC"
    tie_breaker = ", id DESC" if "id" in existing and sort != "id" else ""
    limit = bounded_int(first(params, "limit", "50"), 50, 1, 500)
    offset = bounded_int(first(params, "offset", "0"), 0, 0, 1_000_000)
    where, values = build_where(params, existing)

    count = conn.execute(
        f"SELECT COUNT(*) FROM notification_history {where}",
        values,
    ).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT {", ".join(columns)}
        FROM notification_history
        {where}
        ORDER BY {sort} {order}{tie_breaker}
        LIMIT ? OFFSET ?
        """,
        [*values, limit, offset],
    ).fetchall()
    hydrated_rows: list[dict[str, object]] = []
    for row in rows:
        hydrated = {column: None for column in COLUMNS}
        hydrated.update(dict(row))
        hydrated_rows.append(hydrated)
    return (
        {
            "db_path": str(db_path),
            "count": count,
            "limit": limit,
            "offset": offset,
            "rows": hydrated_rows,
        },
        200,
    )


def make_handler(db_path: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            parsed = parse.urlparse(self.path)
            params = parse.parse_qs(parsed.query)
            if parsed.path == "/":
                html = INDEX_HTML.replace("__COLUMNS__", json.dumps(COLUMNS)).replace(
                    "__DEFAULT_VISIBLE_COLUMNS__",
                    json.dumps(DEFAULT_VISIBLE_COLUMNS),
                )
                text_response(self, html)
                return
            if parsed.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if parsed.path == "/api/summary":
                self.summary()
                return
            if parsed.path == "/api/notifications":
                self.notifications(params)
                return
            json_response(self, {"error": "not found"}, status=404)

        def summary(self) -> None:
            if not db_path.exists():
                json_response(self, {"error": f"DB not found: {db_path}"}, status=404)
                return
            with connect(db_path) as conn:
                payload = summary_payload(conn, db_path)
            json_response(self, payload)

        def notifications(self, params: dict[str, list[str]]) -> None:
            if not db_path.exists():
                json_response(self, {"error": f"DB not found: {db_path}"}, status=404)
                return

            with connect(db_path) as conn:
                payload, status = notifications_payload(conn, db_path, params)
            json_response(self, payload, status=status)

    return Handler


def main() -> int:
    args = parse_args()
    db_path = Path(args.db).expanduser()
    handler = make_handler(db_path)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving notification history from {db_path}")
    print(f"http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
