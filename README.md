# Notability AI Bridge

Connect your Notability notes to any AI assistant. Search, read, and query your handwritten notes from Claude, ChatGPT, Littlebird, and any MCP-compatible tool.

## How It Works

1. Notability auto-backs up your notes as PDFs to Google Drive
2. You authorize this app to read that Google Drive folder via OAuth 2.0
3. You get a unique MCP URL to add to your AI assistant
4. Your AI can now search and read all your Notability notes

## MCP Tools

| Tool | Description |
|------|-------------|
| `list_folders` | List all Notability folders from your backups |
| `list_notes` | List all notes (PDFs) in your backups, optionally filtered by folder |
| `read_note` | Read the full text content of a specific note by file ID |
| `search_notes` | Full-text search across all your notes with context snippets |

## Setup

### 1. Google Cloud OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable the **Google Drive API**
4. Go to **Credentials** > **Create Credentials** > **OAuth client ID**
5. Choose **Web application**
6. Add your deployment URL + `/auth/callback` as an authorized redirect URI
7. Copy the **Client ID** and **Client Secret**

### 2. Deploy on Railway

1. Fork this repo
2. Create a new Railway project from the repo
3. Add a **Volume** mounted at `/data` (for SQLite storage)
4. Set environment variables:

```
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
OAUTH_REDIRECT_URI=https://your-app.up.railway.app/auth/callback
BASE_URL=https://your-app.up.railway.app
```

5. Deploy

### 3. User Onboarding

1. Visit your deployment URL (e.g., `https://your-app.up.railway.app`)
2. Click **Connect Your Google Drive**
3. Authorize Google Drive access
4. Get redirected to your dashboard with your unique MCP URL
5. Copy the MCP URL and add it to your AI assistant

### 4. Connect to Your AI Assistant

**Claude Desktop:** Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "notability": {
      "url": "https://your-app.up.railway.app/mcp/YOUR_API_KEY"
    }
  }
}
```

**Littlebird:** Settings > Integrations > Add Custom MCP > paste URL

**Any MCP client:** Use `https://your-app.up.railway.app/mcp/YOUR_API_KEY` as your MCP server endpoint.

## Pricing Tiers

| Plan | Price | Daily Limit | Features |
|------|-------|-------------|----------|
| Free | $0/mo | 50 calls | All 4 tools |
| Pro | $5/mo | 1,000 calls | Priority support, advanced search |
| Enterprise | Custom | Unlimited | SSO, SLA |

## Tech Stack

- **Python 3.12** + **FastMCP** for MCP protocol
- **Starlette** + **Uvicorn** for web server
- **SQLite** (WAL mode) for user/token/usage storage
- **Google OAuth 2.0** for per-user Drive access
- **Railway** for deployment with persistent volume

## API Key Authentication

API keys can be passed in three ways:
1. **URL path**: `/mcp/{api_key}` (recommended for MCP clients)
2. **Authorization header**: `Authorization: Bearer {api_key}`
3. **Query parameter**: `/mcp?key={api_key}`

## Development

```bash
pip install -r requirements.txt
export GOOGLE_CLIENT_ID=...
export GOOGLE_CLIENT_SECRET=...
export OAUTH_REDIRECT_URI=http://localhost:8080/auth/callback
export BASE_URL=http://localhost:8080
python server.py
```

## Disclaimer

Notability AI Bridge is an independent tool and is not affiliated with, endorsed by, or sponsored by Notability or Google. Notability is a trademark of Ginger Labs, Inc.
