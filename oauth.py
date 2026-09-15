"""
Google Drive OAuth 2.0 flow for Notability MCP SaaS.
Each user authorizes their own Google Drive access via OAuth.
"""

import os
import json
import logging
import urllib.parse
from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build

from database import (
    get_user_by_email, create_user, store_oauth_token,
    get_oauth_token, update_access_token, create_oauth_state,
    validate_oauth_state,
)

logger = logging.getLogger("notability-mcp-oauth")

# OAuth config from env vars
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
# The redirect URI must match what's configured in Google Cloud Console
OAUTH_REDIRECT_URI = os.environ.get("OAUTH_REDIRECT_URI", "")

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

NOTABILITY_FOLDER_NAME = os.environ.get("NOTABILITY_FOLDER_NAME", "Notability")


def get_auth_url(base_url: str, email: str = "") -> str:
    """Generate the Google OAuth authorization URL."""
    state = create_oauth_state(email) if email else ""
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI or f"{base_url}/auth/callback",
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",  # Force consent to get refresh token
    }
    if state:
        params["state"] = state
        params["login_hint"] = email

    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def exchange_code(code: str) -> dict:
    """Exchange authorization code for tokens."""
    import urllib.request

    data = urllib.parse.urlencode({
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def refresh_access_token(refresh_token: str) -> dict:
    """Refresh an expired access token."""
    import urllib.request

    data = urllib.parse.urlencode({
        "refresh_token": refresh_token,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "grant_type": "refresh_token",
    }).encode()

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def handle_oauth_callback(code: str, state: str) -> dict:
    """Handle the OAuth callback. Creates user, stores tokens.
    Returns user info dict.
    """
    # Validate state
    email = validate_oauth_state(state) if state else ""

    # Exchange code for tokens
    token_data = exchange_code(code)
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 3600)

    # Get user email from Google if not from state
    if not email:
        email = get_user_email_from_token(access_token)

    if not email:
        raise ValueError("Could not determine user email from OAuth flow")

    # Create or get user
    user = get_user_by_email(email)
    if not user:
        user = create_user(email)

    # Find the Notability folder in their Drive
    drive_folder_id = find_notability_folder(access_token)

    # Store tokens
    store_oauth_token(user["id"], access_token, refresh_token or "", expires_in, drive_folder_id)

    logger.info(f"OAuth completed for user {email}, folder_id={drive_folder_id}")
    return user


def get_user_email_from_token(access_token: str) -> str:
    """Get user email from Google userinfo endpoint."""
    import urllib.request
    req = urllib.request.Request(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            info = json.loads(resp.read())
            return info.get("email", "")
    except Exception as e:
        logger.error(f"Failed to get user email: {e}")
        return ""


def find_notability_folder(access_token: str) -> str:
    """Find the Notability folder in the user's Google Drive."""
    creds = Credentials(token=access_token)
    service = build("drive", "v3", credentials=creds)
    results = service.files().list(
        q=f"mimeType = 'application/vnd.google-apps.folder' and name = '{NOTABILITY_FOLDER_NAME}' and trashed = false",
        fields="files(id, name)", pageSize=10,
    ).execute()
    folders = results.get("files", [])
    if folders:
        return folders[0]["id"]
    # If no Notability folder, return empty - user can set it later
    logger.warning(f"No '{NOTABILITY_FOLDER_NAME}' folder found in user's Drive")
    return ""


def get_user_drive_service(user_id: int):
    """Get an authenticated Google Drive service for a specific user.
    Handles token refresh automatically.
    """
    token_data = get_oauth_token(user_id)
    if not token_data:
        raise RuntimeError("User has not connected Google Drive. Visit the dashboard to authorize.")

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")
    expiry_str = token_data.get("token_expiry", "")

    # Check if token needs refresh
    needs_refresh = False
    if expiry_str:
        try:
            expiry = datetime.fromisoformat(expiry_str)
            if datetime.utcnow() > expiry - timedelta(minutes=5):
                needs_refresh = True
        except (ValueError, TypeError):
            needs_refresh = True
    else:
        needs_refresh = True

    if needs_refresh and refresh_token:
        logger.info(f"Refreshing access token for user {user_id}")
        new_tokens = refresh_access_token(refresh_token)
        access_token = new_tokens.get("access_token")
        expires_in = new_tokens.get("expires_in", 3600)
        update_access_token(user_id, access_token, expires_in)

    creds = Credentials(token=access_token, refresh_token=refresh_token)
    return build("drive", "v3", credentials=creds)


def get_user_folder_id(user_id: int) -> str:
    """Get the stored Notability folder ID for a user."""
    token_data = get_oauth_token(user_id)
    if not token_data:
        raise RuntimeError("User has not connected Google Drive.")
    folder_id = token_data.get("drive_folder_id", "")
    if not folder_id:
        raise RuntimeError(
            f"No '{NOTABILITY_FOLDER_NAME}' folder found in your Google Drive. "
            "Make sure Notability auto-backup is enabled and set to PDF format."
        )
    return folder_id
