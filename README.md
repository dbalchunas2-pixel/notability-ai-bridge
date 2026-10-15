# Notability AI Bridge

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new)

<!-- To make the button deploy this exact repo: create a Railway template from
     your fork (railway.com > New > Template from repo), then replace the link
     above with https://railway.com/deploy/<your-template-id> -->

Connect your Notability notes to any AI assistant. Search, read, and query your handwritten notes from Claude, ChatGPT, Littlebird, and any MCP-compatible tool.

Free and open source (MIT). No subscriptions, no usage fees, no paywalled notes - you self-host it, so your notes live on your own infrastructure.

## How It Works

1. Notability auto-backs up your notes as PDFs to Google Drive
2. You authorize your own instance to read that folder via OAuth 2.0
3. You get a unique MCP URL to add to your AI assistant
4. Your AI can now search and read all your Notability notes

## MCP Tools

| Tool | Description |
|------|-------------|
| `list_folders` | List all Notability folders from your backups |
| `list_notes` | List all notes (PDFs) in your backups, optionally filtered by folder |
| `read_note` | Read the full text content of a specific note by file ID |
| `search_notes` | Full-text search across all your notes with context snippets |

## Self-Hosting

The easiest path is Railway (free tier works):

1. **Fork this repo**
2. **Deploy it on Railway** - create a new project from your fork (or use the Deploy button above after creating a template)
3. **Add a Volume** mounted at `/data` so SQLite persists across restarts
4. **Create Google OAuth credentials**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a project, enable the **Google Drive API**
   - Credentials > Create Credentials > OAuth client ID > Web application
   - Add `https://your-app.up.railway.app/auth/callback` as an authorized redirect URI
5. **Set environment variables** (see [.env.example](.env.example)):
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `OAUTH_REDIRECT_URI=https://your-app.up.railway.app/auth/callback`
   - `BASE_URL=https://your-app.up.railway.app`
6. Visit your deployment URL, click **Connect Your Google Drive**, and copy your MCP URL

### Connect Your AI Assistant

Use `https://your-app.up.railway.app/mcp/YOUR_API_KEY` as your MCP server endpoint.

**Claude Desktop:** add to `claude_desktop_config.json`:
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

**Any MCP client:** the URL works as-is; the key can also go in an `Authorization: Bearer` header or `?key=` query param.

### Rate Limits

A simple per-user daily rate limit ships in as abuse protection (default: 50 tool calls/day). Since you own the instance, it's just a constant - edit `PLAN_LIMITS` in `database.py` or set every user's plan to `unlimited`. There is no billing and no plan system.

### Privacy

Your instance requests read-only Google Drive access via OAuth 2.0. PDFs are streamed in-memory and never written to disk. Google may show an "Unverified app" warning for self-hosted apps - this is normal for personal OAuth projects and safe to proceed past for an instance only you use.

## Development

```bash
pip install -r requirements.txt
cp .env.example .env  # fill in your values
python server.py
```

## Tech Stack

- **Python 3.12** + **FastMCP** for MCP protocol
- **Starlette** + **Uvicorn** for web server
- **SQLite** (WAL mode) for user/token/usage storage
- **Google OAuth 2.0** for per-user Drive access
- **Railway** for deployment with persistent volume

## Disclaimer

Notability AI Bridge is an independent tool and is not affiliated with, endorsed by, or sponsored by Notability or Google. Notability is a trademark of Ginger Labs, Inc.

## License

[MIT](LICENSE)
