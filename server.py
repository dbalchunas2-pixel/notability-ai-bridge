"""
Notability MCP SaaS Server
Multi-user MCP server that bridges Notability PDF auto-backups
from Google Drive to AI assistants. Each user connects their own
Google Drive via OAuth 2.0 and gets a unique API key.

Architecture:
  - FastMCP for MCP protocol (tools: list_folders, list_notes, read_note, search_notes)
  - Starlette for web routes (landing, auth, dashboard)
  - SQLite for user/token/usage storage
  - Google OAuth 2.0 for per-user Drive access
  - API key auth on MCP endpoint via path parameter or Bearer header
"""

import os
import io
import time
import glob
import json
import logging
import secrets
from datetime import datetime
from pathlib import Path

from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse, RedirectResponse, PlainTextResponse
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware

from database import (
    init_db, get_user_by_api_key, get_user_by_id, log_usage,
    check_rate_limit, get_usage_stats, get_usage_today,
    regenerate_api_key, PLAN_LIMITS,
)
from oauth import (
    get_auth_url, handle_oauth_callback, get_user_drive_service,
    get_user_folder_id, GOOGLE_CLIENT_ID,
)
from legal import PRIVACY_HTML, TERMS_HTML
from billing import create_checkout_session, create_portal_session, handle_webhook

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("notability-mcp")

# --- Config ---
BASE_URL = os.environ.get("BASE_URL", "")
PORT = int(os.environ.get("PORT", 8080))
DATA_DIR = os.environ.get("DATA_DIR", "/data")

# --- Per-request user context ---
import contextvars
_current_user_id = contextvars.ContextVar("user_id", default=None)
_current_api_key = contextvars.ContextVar("api_key", default=None)


def get_current_user_id() -> int:
    uid = _current_user_id.get()
    if uid is None:
        raise RuntimeError("No authenticated user in context")
    return uid


# --- PDF utilities ---

def _extract_pdf_text(pdf_bytes: bytes, max_chars: int = 50000) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append(f"--- Page {i+1} ---\n{text}")
    full_text = "\n\n".join(pages)
    if len(full_text) > max_chars:
        full_text = full_text[:max_chars] + f"\n\n[... truncated at {max_chars} characters ...]"
    return full_text


def _drive_list_files(service, folder_id: str) -> list[dict]:
    """Recursively list all PDFs in a Drive folder."""
    all_files = []
    def _list_in_parent(parent_id):
        token = None
        while True:
            results = service.files().list(
                q=f"'{parent_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, size, parents)",
                pageSize=200, pageToken=token,
            ).execute()
            for item in results.get("files", []):
                if item["mimeType"] == "application/vnd.google-apps.folder":
                    _list_in_parent(item["id"])
                elif item["mimeType"] == "application/pdf":
                    all_files.append(item)
            token = results.get("nextPageToken")
            if not token:
                break
    _list_in_parent(folder_id)
    return all_files


def _drive_get_subfolders(service, folder_id: str) -> list[dict]:
    """Get immediate subfolders of a Drive folder."""
    results = service.files().list(
        q=f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        fields="files(id, name)", pageSize=100,
    ).execute()
    return results.get("files", [])


# --- MCP Server with per-user tools ---

mcp = FastMCP("notability-saas")


def _track_usage(tool_name: str, params: str = ""):
    """Log usage for the current user."""
    uid = _current_user_id.get()
    if uid:
        log_usage(uid, tool_name, params)


def _check_limit() -> tuple[bool, str]:
    """Check rate limit for current user."""
    uid = _current_user_id.get()
    if uid is None:
        return False, "Not authenticated"
    user = get_user_by_id(uid)
    if not user:
        return False, "User not found"
    return check_rate_limit(uid, user.get("plan", "free"))


@mcp.tool
def list_folders() -> str:
    """List all Notability folders from your Google Drive backups."""
    allowed, msg = _check_limit()
    if not allowed:
        return f"Rate limit: {msg}"
    start = time.time()
    try:
        user_id = get_current_user_id()
        service = get_user_drive_service(user_id)
        folder_id = get_user_folder_id(user_id)
        subfolders = _drive_get_subfolders(service, folder_id)
        folders = [f["name"] for f in subfolders]
        _track_usage("list_folders")
        return "\n".join(folders) if folders else "(root - no subfolders)"
    except Exception as e:
        return f"Error: {e}"
    finally:
        _track_usage("list_folders", f"duration={int((time.time()-start)*1000)}ms")


@mcp.tool
def list_notes(folder: str = "") -> str:
    """List all Notability notes (PDFs) in your backups. Optionally filter by folder name."""
    allowed, msg = _check_limit()
    if not allowed:
        return f"Rate limit: {msg}"
    start = time.time()
    try:
        user_id = get_current_user_id()
        service = get_user_drive_service(user_id)
        backup_id = get_user_folder_id(user_id)

        if folder:
            subfolders = _drive_get_subfolders(service, backup_id)
            target = next((f for f in subfolders if f["name"] == folder), None)
            search_id = target["id"] if target else backup_id
        else:
            search_id = backup_id

        notes = _drive_list_files(service, search_id)
        if not notes:
            return "No notes found."

        lines = []
        for note in notes:
            name = note.get("name", "Untitled")
            file_id = note.get("id", "")
            size_kb = round(int(note.get("size", 0)) / 1024, 1)
            mtime = note.get("modifiedTime", "unknown")[:16].replace("T", " ")
            lines.append(f"{name} | {file_id} | {size_kb} KB | {mtime}")
        _track_usage("list_notes", f"folder={folder}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool
def read_note(note_id: str) -> str:
    """Read the full text content of a specific Notability note.
    Use the file ID from list_notes, or the note path.
    """
    allowed, msg = _check_limit()
    if not allowed:
        return f"Rate limit: {msg}"
    start = time.time()
    try:
        user_id = get_current_user_id()
        service = get_user_drive_service(user_id)
        pdf_bytes = service.files().get_media(fileId=note_id).execute()
        text = _extract_pdf_text(pdf_bytes)
        _track_usage("read_note", f"note_id={note_id[:20]}")
        return text if text.strip() else "Note appears to be empty or handwritten."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool
def search_notes(query: str, max_results: int = 10) -> str:
    """Search across all your Notability notes for a keyword or phrase.
    Returns matching notes with surrounding context.
    """
    allowed, msg = _check_limit()
    if not allowed:
        return f"Rate limit: {msg}"
    start = time.time()
    try:
        user_id = get_current_user_id()
        service = get_user_drive_service(user_id)
        backup_id = get_user_folder_id(user_id)
        drive_notes = _drive_list_files(service, backup_id)
        notes = [{"name": n.get("name", "?"), "id": n.get("id", "")} for n in drive_notes]

        if not notes:
            return "No notes available to search."

        query_lower = query.lower()
        results = []
        for note in notes:
            try:
                pdf_bytes = service.files().get_media(fileId=note["id"]).execute()
                text = _extract_pdf_text(pdf_bytes, max_chars=100000)
                if query_lower in text.lower():
                    idx = text.lower().find(query_lower)
                    context = text[max(0, idx-100):idx+len(query)+200].replace("\n", " ").strip()
                    results.append(f"{note['name']}\n  ...{context}...")
                    if len(results) >= max_results:
                        break
            except Exception:
                continue

        _track_usage("search_notes", f"query={query[:50]}")
        if results:
            return f"Found {len(results)} match(es):\n\n" + "\n\n".join(results)
        return f"No matches for '{query}'."
    except Exception as e:
        return f"Error: {e}"


# --- API Key Auth Middleware ---

class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Extract API key from URL path or Authorization header for /mcp routes."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path.startswith("/mcp"):
            api_key = None

            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                api_key = auth_header[7:].strip()

            if not api_key:
                parts = path.strip("/").split("/")
                if len(parts) >= 2 and parts[0] == "mcp":
                    api_key = parts[1]

            if not api_key:
                api_key = request.query_params.get("key", "")

            if not api_key:
                return JSONResponse(
                    {"error": "Missing API key. Include it in the URL path (/mcp/{key}), Authorization header, or ?key= param."},
                    status_code=401
                )

            user = get_user_by_api_key(api_key)
            if not user:
                return JSONResponse(
                    {"error": "Invalid API key. Check your dashboard for the correct key."},
                    status_code=403
                )

            _current_user_id.set(user["id"])
            _current_api_key.set(api_key)

            if path != "/mcp" and path != "/mcp/":
                request.scope["path"] = "/mcp"
                request.scope["raw_path"] = b"/mcp"

        response = await call_next(request)

        _current_user_id.set(None)
        _current_api_key.set(None)

        return response


# --- Web Routes ---

def get_base_url(request: Request) -> str:
    if BASE_URL:
        return BASE_URL.rstrip("/")
    scheme = request.url.scheme
    host = request.headers.get("host", request.url.netloc)
    return f"{scheme}://{host}"


async def landing_page(request: Request):
    """Serve the landing page."""
    try:
        with open(Path(__file__).parent / "landing.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Error: landing.html not found</h1>",
            status_code=500
        )

async def auth_start(request: Request):
    base = get_base_url(request)
    if not GOOGLE_CLIENT_ID:
        return HTMLResponse(
            "<h1>Setup Required</h1><p>GOOGLE_CLIENT_ID env var not set. "
            "See README for Google Cloud setup instructions.</p>",
            status_code=500
        )
    email = request.query_params.get("email", "")
    auth_url = get_auth_url(base, email)
    return RedirectResponse(auth_url)


async def auth_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state", "")
    error = request.query_params.get("error")

    if error:
        return HTMLResponse(f"<h1>Authorization Error</h1><p>{error}</p>", status_code=400)
    if not code:
        return HTMLResponse("<h1>Error</h1><p>No authorization code received.</p>", status_code=400)

    try:
        user = handle_oauth_callback(code, state)
        return RedirectResponse(f"/dashboard?key={user['api_key']}&welcome=1")
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return HTMLResponse(f"<h1>Setup Error</h1><p>{e}</p><p><a href='/'>Go home</a></p>", status_code=500)


async def dashboard(request: Request):
    api_key = request.query_params.get("key", "")
    welcome = request.query_params.get("welcome", "")

    if not api_key:
        return HTMLResponse(
            "<h1>Dashboard</h1><p>API key required. <a href='/auth'>Connect your Google Drive</a> to get started.</p>",
            status_code=401
        )

    user = get_user_by_api_key(api_key)
    if not user:
        return HTMLResponse("<h1>Invalid API key</h1>", status_code=403)

    stats = get_usage_stats(user["id"])
    used_today = get_usage_today(user["id"])
    limit = PLAN_LIMITS.get(user.get("plan", "free"), 50)

    base = get_base_url(request)
    mcp_url = f"{base}/mcp/{api_key}"

    html = render_dashboard(user, stats, used_today, limit, mcp_url, welcome)
    return HTMLResponse(html)


async def api_usage(request: Request):
    api_key = request.query_params.get("key", "")
    if not api_key:
        return JSONResponse({"error": "API key required"}, status_code=401)
    user = get_user_by_api_key(api_key)
    if not user:
        return JSONResponse({"error": "Invalid API key"}, status_code=403)
    stats = get_usage_stats(user["id"])
    used_today = get_usage_today(user["id"])
    limit = PLAN_LIMITS.get(user.get("plan", "free"), 50)
    return JSONResponse({
        "user": {"email": user["email"], "plan": user.get("plan", "free")},
        "usage_today": used_today,
        "daily_limit": limit if limit > 0 else "unlimited",
        "stats": stats,
    })


async def health(request: Request):
    return JSONResponse({"status": "ok", "service": "notability-mcp-saas"})


# --- HTML Templates ---
# (Landing page and dashboard templates are large HTML strings)
# Full templates at: https://github.com/dbalchunas2-pixel/notability-ai-bridge/blob/main/server.py



def render_dashboard(user, stats, used_today, limit, mcp_url, welcome):
    limit_display = str(limit) if limit > 0 else "unlimited"
    welcome_banner = (
        '<div style="background: #1a2e1a; border: 1px solid #22c55e; padding: 16px; border-radius: 12px; margin-bottom: 24px;">'
        '<h3 style="color: #22c55e; margin-bottom: 8px;">Setup Complete!</h3>'
        '<p style="color: #86efac;">Your Google Drive is connected. Copy your MCP URL below and add it to your AI assistant.</p>'
        '</div>'
    ) if welcome else ""

    tool_stats = ""
    for tool, count in stats.get("by_tool", {}).items():
        tool_stats += f"<tr><td>{tool}</td><td>{count}</td></tr>"

    usage_pct = min(100, int(used_today / max(limit, 1) * 100)) if limit > 0 else 5

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard - Notability AI Bridge</title>
<style>
:root {{ --bg: #0f1117; --card: #1a1d28; --accent: #6366f1; --text: #e4e4e7; --muted: #71717a; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}
.container {{ max-width: 720px; margin: 0 auto; padding: 40px 24px; }}
h1 {{ font-size: 1.6rem; margin-bottom: 24px; }}
.card {{ background: var(--card); padding: 24px; border-radius: 16px; border: 1px solid #2a2d3a; margin-bottom: 20px; }}
.card h2 {{ font-size: 1.1rem; margin-bottom: 16px; color: #a5b4fc; }}
.mcp-url {{ background: #0f1117; border: 1px solid #2a2d3a; padding: 12px 16px; border-radius: 8px; font-family: 'SF Mono', Monaco, monospace; font-size: 0.85rem; word-break: break-all; display: flex; align-items: center; gap: 12px; }}
.copy-btn {{ background: var(--accent); color: white; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 0.8rem; white-space: nowrap; }}
.stat-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }}
.stat {{ text-align: center; }}
.stat .num {{ font-size: 1.8rem; font-weight: 700; }}
.stat .label {{ font-size: 0.8rem; color: var(--muted); }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #2a2d3a; font-size: 0.9rem; }}
.usage-bar {{ background: #2a2d3a; border-radius: 20px; height: 8px; margin-top: 12px; overflow: hidden; }}
.usage-fill {{ background: var(--accent); height: 100%; border-radius: 20px; }}
footer {{ text-align: center; margin-top: 32px; padding: 16px; color: var(--muted); font-size: 0.85rem; }}
</style>
<script>
function copyText(text, btn) {{
  navigator.clipboard.writeText(text).then(() => {{
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = 'Copy', 2000);
  }});
}}
</script>
</head>
<body>
<div class="container">
{welcome_banner}
<h1>Dashboard</h1>
<div style="margin-bottom: 16px;">
<span class="plan-badge" style="padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase;">{user.get('plan', 'free')} plan</span>
<span style="color: var(--muted); margin-left: 12px;">{user['email']}</span>
</div>
<div class="card">
<h2>Your MCP URL</h2>
<p style="color: var(--muted); margin-bottom: 12px; font-size: 0.9rem;">Add this URL to your AI assistant's MCP configuration:</p>
<div class="mcp-url">
<span style="flex: 1;">{mcp_url}</span>
<button class="copy-btn" onclick="copyText('{mcp_url}', this)">Copy</button>
</div>
</div>
<div class="card">
<h2>Usage</h2>
<div class="stat-grid">
<div class="stat"><div class="num">{used_today}</div><div class="label">today</div></div>
<div class="stat"><div class="num">{stats.get('last_30_days', 0)}</div><div class="label">last 30 days</div></div>
<div class="stat"><div class="num">{stats.get('total_calls', 0)}</div><div class="label">all time</div></div>
</div>
<div class="usage-bar"><div class="usage-fill" style="width: {usage_pct}%;"></div></div>
<p style="color: var(--muted); margin-top: 8px; font-size: 0.85rem;">{used_today}/{limit_display} calls today</p>
</div>
<div class="card">
<h2>Calls by Tool</h2>
<table>
<thead><tr><th>Tool</th><th>Calls</th></tr></thead>
<tbody>
{tool_stats if tool_stats else '<tr><td colspan="2" style="color: var(--muted);">No usage yet</td></tr>'}
</tbody>
</table>
</div>
<div class="card">
<h2>Setup Instructions</h2>
<p style="color: var(--muted); font-size: 0.9rem;">Add this URL to any MCP-compatible AI assistant (Claude Desktop, Littlebird, etc.) as your MCP server endpoint.</p>
</div>
{f'<div class="card"><h2>Subscription</h2><p>Current plan: <strong>{user.get('plan', 'free')}</strong></p>{f'<a href="/upgrade?key={api_key}&plan=pro" style="display:inline-block;padding:10px 24px;background:#6366f1;color:white;text-decoration:none;border-radius:8px;font-weight:600;margin-top:12px;">Upgrade to Pro - $5/mo</a>' if user.get('plan', 'free') == 'free' else ''}{f'<a href="/portal?key={api_key}" style="display:inline-block;padding:8px 16px;background:#2a2d3a;color:#e4e4e7;text-decoration:none;border-radius:8px;font-size:0.85rem;margin-left:12px;">Manage Subscription</a>' if user.get('stripe_customer_id') else ''}</div>'}
<footer><a href="/">Home</a> | <a href="/privacy">Privacy</a> | <a href="/terms">Terms</a> | Notability AI Bridge</footer>
</div>
</body>
</html>"""


# --- Billing & Legal Routes ---

async def upgrade(request):
    """Start Stripe checkout for upgrading to a paid plan."""
    api_key = request.query_params.get("key", "")
    plan = request.query_params.get("plan", "pro")
    if not api_key:
        return JSONResponse({"error": "API key required"}, status_code=401)
    user = get_user_by_api_key(api_key)
    if not user:
        return JSONResponse({"error": "Invalid API key"}, status_code=403)
    try:
        checkout_url = create_checkout_session(user["id"], plan, api_key)
        return RedirectResponse(checkout_url)
    except Exception as e:
        return HTMLResponse(f"<h1>Checkout Error</h1><p>{e}</p><p><a href='/dashboard?key={api_key}'>Back</a></p>", status_code=500)

async def customer_portal(request):
    """Redirect to Stripe Customer Portal for subscription management."""
    api_key = request.query_params.get("key", "")
    if not api_key:
        return JSONResponse({"error": "API key required"}, status_code=401)
    user = get_user_by_api_key(api_key)
    if not user:
        return JSONResponse({"error": "Invalid API key"}, status_code=403)
    customer_id = user.get("stripe_customer_id", "")
    if not customer_id:
        return HTMLResponse("<h1>No subscription found</h1><p>You don't have an active subscription to manage.</p>")
    try:
        portal_url = create_portal_session(customer_id, api_key)
        return RedirectResponse(portal_url)
    except Exception as e:
        return HTMLResponse(f"<h1>Portal Error</h1><p>{e}</p>", status_code=500)

async def stripe_webhook(request):
    """Handle Stripe webhook events."""
    body = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        result = handle_webhook(body, signature)
        return JSONResponse({"received": True, "result": result})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

async def privacy_page(request):
    """Serve the Privacy Policy page."""
    return HTMLResponse(PRIVACY_HTML)

async def terms_page(request):
    """Serve the Terms of Service page."""
    return HTMLResponse(TERMS_HTML)


# --- App Assembly ---

def create_app():
    """Create the ASGI application combining web routes and MCP server."""
    init_db()

    # Register web routes as custom routes on the MCP server
    mcp.custom_route("/", methods=["GET"])(landing_page)
    mcp.custom_route("/auth", methods=["GET"])(auth_start)
    mcp.custom_route("/auth/callback", methods=["GET"])(auth_callback)
    mcp.custom_route("/dashboard", methods=["GET"])(dashboard)
    mcp.custom_route("/upgrade", methods=["GET"])(upgrade)
    mcp.custom_route("/portal", methods=["GET"])(customer_portal)
    mcp.custom_route("/webhook", methods=["POST"])(stripe_webhook)
    mcp.custom_route("/privacy", methods=["GET"])(privacy_page)
    mcp.custom_route("/terms", methods=["GET"])(terms_page)
    mcp.custom_route("/api/usage", methods=["GET"])(api_usage)
    mcp.custom_route("/health", methods=["GET"])(health)

    # Create the ASGI app with middleware
    # MCP endpoint will be at /mcp by default
    app = mcp.http_app(middleware=[Middleware(APIKeyAuthMiddleware)])
    return app


app = create_app()


if __name__ == "__main__":
    logger.info(f"Starting Notability MCP SaaS on port {PORT}")
    mcp.run(transport="http", host="0.0.0.0", port=PORT)

