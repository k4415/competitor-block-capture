from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from typing import Any
from urllib.parse import parse_qs

from listing_os.notion.client import NotionClient

from .notion_workspace import create_research_workspace
from .runner import ResearchRequest, collect_research_bundle
from .v2.notion_workspace import create_v2_research_workspace
from .v2.profiles import resolve_genre_profile
from .v2.quality import evaluate_v2_quality
from .v2.replace import discover_v1_page_ids
from .v2.runner import ResearchV2Request, collect_v2_research_bundle

try:  # Optional dependency for the local UI.
    from fastapi import BackgroundTasks, FastAPI, Request
    from fastapi.responses import HTMLResponse
except ImportError:  # pragma: no cover - depends on optional web extras.
    BackgroundTasks = None  # type: ignore[assignment]
    FastAPI = None  # type: ignore[assignment]
    HTMLResponse = None  # type: ignore[assignment]
    Request = None  # type: ignore[assignment]


@dataclass
class JobState:
    job_id: str
    status: str = "queued"
    message: str = ""
    result: dict[str, Any] | None = None
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


JOBS: dict[str, JobState] = {}


def create_app():
    if FastAPI is None or HTMLResponse is None or Request is None or BackgroundTasks is None:  # pragma: no cover
        raise RuntimeError("FastAPI is not installed. Run `python3 -m pip install -e .[web]`.")

    app = FastAPI(title="Research OS")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(render_index())

    @app.post("/runs", response_class=HTMLResponse)
    async def start_run(request: Request, background_tasks: BackgroundTasks):
        form = parse_qs((await request.body()).decode("utf-8"))
        category_name = _first(form, "category_name")
        parent_page_id = _first(form, "parent_page_id") or os.getenv("NOTION_PARENT_PAGE_ID", "de02e0f0cbe8824ca79201a3b390bd43")
        memo = _first(form, "memo")
        depth = _first(form, "depth") or "standard"
        urls = [line.strip() for line in _first(form, "competitor_urls").splitlines() if line.strip()]
        replace_v1 = _first(form, "replace_v1") == "on"
        job_id = f"job-{len(JOBS) + 1}"
        JOBS[job_id] = JobState(job_id=job_id, message="queued")
        background_tasks.add_task(_run_v2_job, job_id, category_name, parent_page_id, memo, depth, urls, replace_v1)
        return HTMLResponse(render_job(JOBS[job_id]))

    @app.get("/runs/{job_id}", response_class=HTMLResponse)
    async def show_run(job_id: str):
        return HTMLResponse(render_job(JOBS.get(job_id) or JobState(job_id=job_id, status="missing", error="job not found")))

    return app


def render_index() -> str:
    parent_default = os.getenv("NOTION_PARENT_PAGE_ID", "de02e0f0cbe8824ca79201a3b390bd43")
    content = f"""
  <section class="studio-card">
    <div class="card-heading">
      <div>
        <p class="eyebrow">Research Context</p>
        <h2>リサーチ条件</h2>
      </div>
      <span class="card-pill">V2 Pipeline</span>
    </div>
    <form method="post" action="/runs" class="research-form">
      <div class="form-grid">
        <label class="field">
          <span class="field-label">カテゴリ名</span>
          <span class="field-help">例: 結婚相談所、金買取、植毛、いびき治療</span>
          <input name="category_name" value="結婚相談所" required>
        </label>
        <label class="field">
          <span class="field-label">検索深度</span>
          <span class="field-help">通常は standard 推奨です。</span>
          <select name="depth">
            <option value="standard">standard</option>
            <option value="light">light</option>
            <option value="deep">deep</option>
          </select>
        </label>
      </div>
      <label class="field">
        <span class="field-label">Notion出力先ページIDまたはURL</span>
        <span class="field-help">ジャンルページと4種のリサーチDBをこの配下に作成します。</span>
        <input name="parent_page_id" value="{_e(parent_default)}" required>
      </label>
      <label class="field">
        <span class="field-label">競合比較サイトURL</span>
        <span class="field-help">1行1URL。ここに入れたURLだけを直接競合サイトとして扱います。</span>
        <textarea name="competitor_urls" class="large-textarea" required></textarea>
      </label>
      <label class="field">
        <span class="field-label">説明メモ</span>
        <span class="field-help">任意。重点調査したい訴求、除外したい情報、ASP条件などを記載できます。</span>
        <textarea name="memo" placeholder="比較リスティング向け。直接競合URLを重点調査。"></textarea>
      </label>
      <label class="check-field">
        <input type="checkbox" name="replace_v1" checked>
        <span>
          <strong>V1削除して再作成</strong>
          <small>Research OSが作成した旧ページだけを対象にします。</small>
        </span>
      </label>
      <button type="submit" class="primary-button">リサーチを実行</button>
    </form>
  </section>
"""
    return _render_shell(
        title="比較リス リサーチOS",
        subtitle="カテゴリ名と直接競合URLから、Notion上に根拠付きリサーチDBを生成します。",
        active_step=1,
        content=content,
    )


def render_job(job: JobState) -> str:
    result = job.result or {}
    rows = "".join(
        f'<div class="count-card"><span>{_e(str(key))}: {_e(str(value))}</span></div>'
        for key, value in (result.get("row_counts") or {}).items()
    )
    page_url = result.get("category_page_url", "")
    refresh = ""
    if job.status in {"queued", "running"}:
        refresh = f'<meta http-equiv="refresh" content="2; url=/runs/{job.job_id}">'
    metrics = _render_empty_metrics()
    if result:
        notion_created = "あり" if result.get("notion_created") else "なし"
        openai_status = ""
        if "openai_available" in result:
            openai_status = "設定済み" if result.get("openai_available") else "未設定"
        metrics = _render_metrics(
            [
                ("入力カテゴリ", result.get("input_category", "")),
                ("正規化カテゴリ", result.get("canonical_category", "")),
                ("競合URL数", result.get("competitor_url_count", 0)),
                ("収集ソース数", result.get("source_count", 0)),
                ("品質判定", result.get("quality_status", "")),
                ("Notion作成", notion_created),
                ("要確認件数", result.get("needs_review_count", 0)),
                ("取得失敗URL", ", ".join(result.get("failed_urls") or []) or "なし"),
                *(
                    [
                        ("OpenAI", openai_status),
                        ("seedソース数", result.get("seed_source_count", 0)),
                        ("競合取得ソース数", result.get("competitor_source_count", 0)),
                        ("調査モード", result.get("research_mode", "")),
                        ("不足項目", " / ".join(result.get("quality_missing") or []) or "なし"),
                        ("次に直す入力", result.get("next_action", "")),
                    ]
                    if openai_status
                    else []
                ),
            ]
        )
    alert = _render_job_alert(job, page_url)
    row_counts = f"""
    <section class="studio-card compact-card">
      <div class="card-heading">
        <div>
          <p class="eyebrow">Row Counts</p>
          <h2>作成対象件数</h2>
        </div>
      </div>
      <div class="row-counts">{rows or '<div class="count-card muted-card"><span>まだ件数はありません</span></div>'}</div>
    </section>
"""
    content = f"""
  {alert}
  <section class="studio-card compact-card">
    <div class="card-heading">
      <div>
        <p class="eyebrow">Job Metrics</p>
        <h2>実行状況</h2>
      </div>
      <span class="status-badge status-{_e(job.status)}">Status: {_e(job.status)}</span>
    </div>
    {metrics}
  </section>
  {row_counts}
  <a href="/" class="secondary-button">戻る</a>
"""
    active_step = 3 if job.status == "done" else 2
    return _render_shell(
        title="リサーチ実行結果",
        subtitle=f"ジョブID: {job.job_id}",
        active_step=active_step,
        content=content,
        job=job,
        refresh=refresh,
    )


def _render_shell(
    *,
    title: str,
    subtitle: str,
    active_step: int,
    content: str,
    job: JobState | None = None,
    refresh: str = "",
) -> str:
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {refresh}
  <title>{_e(title)}</title>
  <style>{_studio_css()}</style>
</head>
<body>
  <div class="app-shell">
    {_render_sidebar(job)}
    <div class="studio-main">
      <header class="topbar">
        {_render_step_bar(active_step)}
      </header>
      <main class="content-wrap">
        <section class="content-inner">
          <div class="page-title-block">
            <p class="eyebrow">Research OS</p>
            <h1>{_e(title)}</h1>
            <p>{_e(subtitle)}</p>
          </div>
          {content}
        </section>
      </main>
    </div>
  </div>
</body>
</html>"""


def _render_sidebar(job: JobState | None) -> str:
    status = job.status if job else "idle"
    message = job.message if job and job.message else "入力待ち"
    job_label = job.job_id if job else "新規リサーチ"
    return f"""
<aside class="studio-sidebar">
  <div class="brand-block">
    <div class="brand-row">
      <span class="brand-text">CMOAI</span>
      <span class="brand-pill">RESEARCH OS</span>
    </div>
  </div>
  <div class="sidebar-section">
    <p class="sidebar-label">現在のモード</p>
    <div class="mode-switch">
      <span class="mode-active">リサーチ</span>
      <span>Notion</span>
      <span>検証</span>
    </div>
    <a class="sidebar-action" href="/">リサーチ実行</a>
  </div>
  <div class="sidebar-section sidebar-fill">
    <p class="sidebar-label">直近ジョブ</p>
    <div class="sidebar-job">
      <div class="sidebar-job-top">
        <strong>{_e(job_label)}</strong>
        <span class="status-dot status-dot-{_e(status)}"></span>
      </div>
      <p>{_e(message)}</p>
      <small>Status: {_e(status)}</small>
    </div>
  </div>
</aside>"""


def _render_step_bar(active_step: int) -> str:
    steps = ["コンテキスト入力", "リサーチ実行", "Notion反映"]
    items = []
    for index, label in enumerate(steps, start=1):
        if index < active_step:
            state = "past"
            marker = "✓"
        elif index == active_step:
            state = "current"
            marker = str(index)
        else:
            state = "future"
            marker = str(index)
        connector = '<span class="step-line"></span>' if index < len(steps) else ""
        items.append(
            f"""
      <div class="step-item step-{state}">
        <span class="step-marker">{marker}</span>
        <span class="step-label">{_e(label)}</span>
      </div>
      {connector}"""
        )
    return f'<nav class="step-bar" aria-label="リサーチステップ">{"".join(items)}</nav>'


def _render_job_alert(job: JobState, page_url: str) -> str:
    if job.status == "failed":
        detail = job.error or "実行中にエラーが発生しました。"
        return f"""
  <section class="alert-card alert-error">
    <div>
      <p class="alert-title">品質基準または実行条件を満たしていません</p>
      <p>{_e(job.message or "failed")}</p>
      <p class="alert-detail">{_e(detail)}</p>
    </div>
  </section>
"""
    if job.status == "done":
        notion_link = ""
        if page_url:
            notion_link = f'<a href="{_e(str(page_url))}" class="notion-link" target="_blank" rel="noreferrer">Notionページを開く</a>'
        return f"""
  <section class="alert-card alert-success">
    <div>
      <p class="alert-title">完了</p>
      <p>{_e(job.message or "Notion反映まで完了しました。")}</p>
    </div>
    {notion_link}
  </section>
"""
    if job.status in {"queued", "running"}:
        return f"""
  <section class="alert-card alert-info">
    <div>
      <p class="alert-title">処理中</p>
      <p>{_e(job.message or "実行待ちです。")}</p>
    </div>
  </section>
"""
    return f"""
  <section class="alert-card alert-info">
    <div>
      <p class="alert-title">ジョブ状態</p>
      <p>{_e(job.message or job.error or "状態を確認できません。")}</p>
    </div>
  </section>
"""


def _render_metrics(metrics: list[tuple[str, object]]) -> str:
    cards = []
    for label, value in metrics:
        text = f"{label}: {value}"
        cards.append(f'<div class="metric-card"><span>{_e(text)}</span></div>')
    return f'<div class="metric-grid">{"".join(cards)}</div>'


def _render_empty_metrics() -> str:
    return _render_metrics(
        [
            ("入力カテゴリ", "未取得"),
            ("正規化カテゴリ", "未取得"),
            ("競合URL数", 0),
            ("収集ソース数", 0),
            ("品質判定", "pending"),
            ("Notion作成", "なし"),
            ("要確認件数", 0),
            ("取得失敗URL", "なし"),
        ]
    )


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _studio_css() -> str:
    return """
:root {
  --background: #f8fafc;
  --foreground: #172033;
  --card: #ffffff;
  --muted: #f4f6f9;
  --muted-foreground: #667085;
  --border: #e5e7eb;
  --border-strong: #d0d5dd;
  --primary: #2563eb;
  --primary-soft: #eaf1ff;
  --success: #0f766e;
  --success-bg: #ecfdf5;
  --error: #b42318;
  --error-bg: #fff1f0;
  --info: #175cd3;
  --info-bg: #eff6ff;
  --radius: 12px;
  --shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
}
* {
  box-sizing: border-box;
}
html,
body {
  min-height: 100%;
}
body {
  margin: 0;
  background: var(--background);
  color: var(--foreground);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  font-size: 14px;
  line-height: 1.5;
}
a {
  color: inherit;
}
.app-shell {
  display: flex;
  min-height: 100vh;
  overflow: hidden;
}
.studio-sidebar {
  width: 264px;
  min-height: 100vh;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-right: 1px solid var(--border);
}
.brand-block {
  padding: 16px;
  border-bottom: 1px solid var(--border);
}
.brand-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-text {
  font-size: 18px;
  font-weight: 800;
  color: #111827;
}
.brand-pill,
.card-pill {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--border-strong);
  border-radius: 999px;
  padding: 3px 8px;
  color: var(--muted-foreground);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0;
}
.sidebar-section {
  padding: 14px 12px;
}
.sidebar-fill {
  flex: 1;
}
.sidebar-label {
  margin: 0 0 8px;
  padding: 0 4px;
  color: var(--muted-foreground);
  font-size: 10px;
  font-weight: 700;
}
.mode-switch {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  padding: 4px;
  background: var(--muted);
  border-radius: var(--radius);
}
.mode-switch span {
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  color: var(--muted-foreground);
  font-size: 11px;
  font-weight: 700;
}
.mode-switch .mode-active {
  background: var(--primary);
  color: #ffffff;
  box-shadow: var(--shadow);
}
.sidebar-action,
.secondary-button,
.notion-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  margin-top: 10px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  background: #ffffff;
  color: #344054;
  font-size: 12px;
  font-weight: 700;
  text-decoration: none;
}
.sidebar-action {
  width: 100%;
}
.sidebar-job {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
  background: #ffffff;
}
.sidebar-job-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.sidebar-job strong {
  font-size: 12px;
}
.sidebar-job p,
.sidebar-job small {
  margin: 5px 0 0;
  color: var(--muted-foreground);
  font-size: 11px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border-strong);
}
.status-dot-running,
.status-dot-queued {
  background: var(--primary);
}
.status-dot-done {
  background: var(--success);
}
.status-dot-failed {
  background: var(--error);
}
.studio-main {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}
.topbar {
  border-bottom: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.88);
}
.step-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 58px;
  padding: 12px 24px;
  overflow-x: auto;
}
.step-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
.step-marker {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: var(--muted);
  color: var(--muted-foreground);
  font-size: 12px;
  font-weight: 800;
}
.step-label {
  color: var(--muted-foreground);
  font-size: 13px;
}
.step-current .step-marker {
  background: var(--primary);
  color: #ffffff;
}
.step-current .step-label {
  color: var(--foreground);
  font-weight: 700;
}
.step-past .step-marker {
  background: var(--primary-soft);
  color: var(--primary);
}
.step-line {
  width: 42px;
  height: 1px;
  background: var(--border-strong);
}
.content-wrap {
  flex: 1;
  overflow-y: auto;
}
.content-inner {
  width: min(960px, calc(100% - 48px));
  margin: 0 auto;
  padding: 34px 0 48px;
}
.page-title-block {
  margin-bottom: 22px;
}
.eyebrow {
  margin: 0 0 6px;
  color: var(--muted-foreground);
  font-size: 11px;
  font-weight: 800;
}
h1,
h2,
p {
  letter-spacing: 0;
}
h1 {
  margin: 0;
  font-size: 28px;
  line-height: 1.25;
}
.page-title-block p:last-child {
  max-width: 680px;
  margin: 8px 0 0;
  color: var(--muted-foreground);
}
.studio-card,
.alert-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card);
  box-shadow: var(--shadow);
}
.studio-card {
  padding: 22px;
}
.compact-card {
  margin-top: 14px;
}
.card-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
.card-heading h2 {
  margin: 0;
  font-size: 18px;
}
.research-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(180px, 0.6fr);
  gap: 16px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.field-label {
  font-size: 12px;
  font-weight: 800;
  color: #344054;
}
.field-help {
  color: var(--muted-foreground);
  font-size: 12px;
}
input,
textarea,
select {
  width: 100%;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  background: #ffffff;
  color: var(--foreground);
  font: inherit;
  padding: 11px 12px;
  outline: none;
}
input:focus,
textarea:focus,
select:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}
textarea {
  min-height: 112px;
  resize: vertical;
}
.large-textarea {
  min-height: 190px;
}
.check-field {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--muted);
  padding: 12px;
}
.check-field input {
  width: 16px;
  height: 16px;
  margin-top: 2px;
  padding: 0;
}
.check-field strong,
.check-field small {
  display: block;
}
.check-field small {
  margin-top: 2px;
  color: var(--muted-foreground);
}
.primary-button {
  width: 100%;
  min-height: 44px;
  border: 0;
  border-radius: var(--radius);
  background: var(--primary);
  color: #ffffff;
  font: inherit;
  font-weight: 800;
  cursor: pointer;
}
.primary-button:hover {
  background: #1d4ed8;
}
.secondary-button {
  width: fit-content;
  padding: 0 16px;
}
.alert-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 14px;
  padding: 16px 18px;
}
.alert-card p {
  margin: 2px 0 0;
}
.alert-title {
  margin: 0;
  font-weight: 800;
}
.alert-detail {
  color: inherit;
  font-size: 12px;
}
.alert-error {
  border-color: #fecdca;
  background: var(--error-bg);
  color: var(--error);
}
.alert-success {
  border-color: #abefc6;
  background: var(--success-bg);
  color: var(--success);
}
.alert-info {
  border-color: #bfdbfe;
  background: var(--info-bg);
  color: var(--info);
}
.notion-link {
  flex-shrink: 0;
  margin-top: 0;
  padding: 0 14px;
  border-color: #99f6e4;
  color: var(--success);
}
.status-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 5px 9px;
  background: var(--muted);
  color: var(--muted-foreground);
  font-size: 11px;
  font-weight: 800;
}
.status-running,
.status-queued {
  background: var(--primary-soft);
  color: var(--primary);
}
.status-done {
  background: var(--success-bg);
  color: var(--success);
}
.status-failed {
  background: var(--error-bg);
  color: var(--error);
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.metric-card,
.count-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #ffffff;
  padding: 12px;
}
.metric-card span,
.count-card span {
  color: #344054;
  font-size: 12px;
  font-weight: 700;
  overflow-wrap: anywhere;
}
.row-counts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.muted-card span {
  color: var(--muted-foreground);
}
@media (max-width: 820px) {
  .app-shell {
    flex-direction: column;
    overflow: visible;
  }
  .studio-sidebar {
    width: 100%;
    min-height: 0;
    border-right: 0;
    border-bottom: 1px solid var(--border);
  }
  .sidebar-fill {
    display: none;
  }
  .content-inner {
    width: min(100% - 28px, 960px);
    padding-top: 24px;
  }
  .form-grid,
  .metric-grid,
  .row-counts {
    grid-template-columns: 1fr;
  }
  .alert-card {
    align-items: flex-start;
    flex-direction: column;
  }
}
"""


def _run_job(job_id: str, category_name: str, parent_page_id: str, memo: str, depth: str, urls: list[str]) -> None:
    job = JOBS[job_id]
    try:
        job.status = "running"
        job.message = "Web取得とリサーチ抽出を実行中"
        request = ResearchRequest(category_name=category_name, parent_page_id=parent_page_id, memo=memo, depth=depth, competitor_urls=urls)
        bundle = collect_research_bundle(request)
        job.message = "Notionに書き込み中"
        result = create_research_workspace(
            notion=NotionClient(os.environ["NOTION_API_KEY"]),
            parent_page_id=parent_page_id,
            category_name=category_name,
            memo=memo,
            bundle=bundle,
            research_run_id=request.research_run_id,
        )
        result["research_run_id"] = request.research_run_id
        result["counts"] = bundle.counts()
        job.result = result
        job.status = "done"
        job.message = "完了"
    except Exception as error:  # noqa: BLE001 - surface background job failure in UI.
        job.status = "failed"
        job.error = str(error)


def _run_v2_job(job_id: str, category_name: str, parent_page_id: str, memo: str, depth: str, urls: list[str], replace_v1: bool) -> None:
    job = JOBS[job_id]
    try:
        job.status = "running"
        job.message = "V2: ソース収集と個別リサーチ抽出を実行中"
        request = ResearchV2Request(category_name=category_name, parent_page_id=parent_page_id, memo=memo, depth=depth, competitor_urls=urls)
        profile = resolve_genre_profile(category_name)
        job.result = _v2_base_result(category_name, profile.canonical_name, urls)
        bundle = collect_v2_research_bundle(request)
        quality_report = evaluate_v2_quality(category_name, bundle, expected_competitors=len(urls))
        job.result.update(_v2_bundle_result(bundle, quality_report.status))
        job.result.update(_v2_quality_result(quality_report.missing))
        if not quality_report.passed:
            job.status = "failed"
            job.message = "品質基準未達"
            job.error = quality_report.message()
            return
        job.message = "V2: Notionに書き込み中"
        result = create_v2_research_workspace(
            notion=NotionClient(os.environ["NOTION_API_KEY"]),
            parent_page_id=parent_page_id,
            category_name=profile.canonical_name,
            memo=memo,
            bundle=bundle,
            research_run_id=request.research_run_id,
            replace_page_ids=discover_v1_page_ids() if replace_v1 else [],
        )
        result.update(job.result)
        result["research_run_id"] = request.research_run_id
        result["counts"] = bundle.counts()
        result["notion_created"] = True
        result["quality_status"] = quality_report.status
        job.result = result
        job.status = "done"
        job.message = "完了"
    except Exception as error:  # noqa: BLE001 - surface background job failure in UI.
        job.status = "failed"
        job.error = str(error)


def _first(form: dict[str, list[str]], key: str) -> str:
    return form.get(key, [""])[0]


def _v2_base_result(category_name: str, canonical_category: str, urls: list[str]) -> dict[str, Any]:
    return {
        "input_category": category_name,
        "canonical_category": canonical_category,
        "competitor_url_count": len(urls),
        "notion_created": False,
        "quality_status": "pending",
        "source_count": 0,
        "needs_review_count": 0,
        "failed_urls": [],
        "row_counts": {"category": 0, "target": 0, "players": 0, "competitor_sites": 0},
    }


def _v2_bundle_result(bundle: object, quality_status: str) -> dict[str, Any]:
    counts = bundle.counts()
    diagnostics = getattr(bundle, "diagnostics", {}) or {}
    return {
        "source_count": bundle.source_count,
        "needs_review_count": bundle.needs_review_count(),
        "failed_urls": bundle.failed_urls,
        "quality_status": quality_status,
        **diagnostics,
        "row_counts": {
            "category": counts["category_facts"],
            "target": counts["target_facts"],
            "players": counts["players"],
            "competitor_sites": counts["competitors"],
        },
    }


def _v2_quality_result(missing: tuple[str, ...]) -> dict[str, Any]:
    return {
        "quality_missing": list(missing),
        "next_action": _next_action_for_quality_missing(missing),
    }


def _next_action_for_quality_missing(missing: tuple[str, ...]) -> str:
    if not missing:
        return "なし"
    joined = " / ".join(missing)
    if "競合サイト" in joined:
        return "競合比較サイトURLを1件以上入力してください"
    if "メインプレイヤー" in joined:
        return "カテゴリ別seedまたは公式URLを追加してください"
    if "収集ソース" in joined or "カテゴリー" in joined or "ターゲット" in joined:
        return "OpenAI APIキーを設定するか、カテゴリ別seed/明示ソースを追加してください"
    return "不足項目の根拠URLを追加してください"


app = create_app()
