# Numen MCP - Agent Setup

> `$NUMEN_URL` below is **your** Numen instance - `http://localhost:8001` for
> the default Docker Compose setup, or whatever host you deployed it to. The
> trailing slash on `/mcp/` is required: the MCP server is a mounted sub-app,
> so `/mcp` returns 404.

Connect any MCP-capable AI agent to your Numen workspace. The MCP server
exposes 28 tools for task management, PRD synthesis, PR lifecycle, and
context retrieval scoped to your org.

## TL;DR

1. Visit $NUMEN_URL/mcp-setup, mint an API key (90-day default).
2. Run the install command for your agent (Claude Code, Conductor, Cursor, etc.).
3. In your agent: ask it to call `hello_numen`. You're done.

The key is shown once. Save it somewhere the agent can reach (config file).
Manage keys at `/account/keys`.

---

## Get an API key

Sign in at $NUMEN_URL and visit `/mcp-setup`. Pick your client.
The mint button generates a key bound to your user + your default org. Default
expiry is **90 days**; rotate via `/account/keys`.

For programmatic clients (Conductor, Claude Code, headless CI), use the web
flow endpoint directly:

```
POST $NUMEN_URL/api/living/auth/web?client=claude_code
Authorization: Bearer <your numen JWT>
```

Returns JSON with the plaintext key and a per-client install snippet. The
plaintext is only in this response; lose it and you mint a new one.

---

## Connect Claude Code

Single command:

```bash
claude mcp add --transport http numen $NUMEN_URL/mcp/ \
  --header "Authorization: Bearer numen_<your_key>"
```

Restart Claude Code. In your next session, ask the agent: **"Call hello_numen
first."** It returns your org info, the available tool index, and a sample
first call.

---

## Connect Conductor

```bash
conductor mcp add numen \
  --url $NUMEN_URL/mcp/ \
  --header "Authorization: Bearer numen_<your_key>"
```

(Conductor MCP support is recent; older builds may need the JSON-config form
shown for Cursor below.)

---

## Connect Cursor

Add to `~/.cursor/mcp.json` (or via Settings -> MCP Servers):

```json
{
  "mcpServers": {
    "numen": {
      "url": "$NUMEN_URL/mcp/",
      "headers": {
        "Authorization": "Bearer numen_<your_key>"
      }
    }
  }
}
```

---

## Connect Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "numen": {
      "url": "$NUMEN_URL/mcp/",
      "headers": {
        "Authorization": "Bearer numen_<your_key>"
      }
    }
  }
}
```

Restart Claude Desktop.

---

## Connect Windsurf

Settings -> MCP, paste:

```json
{
  "mcpServers": {
    "numen": {
      "url": "$NUMEN_URL/mcp/",
      "headers": {
        "Authorization": "Bearer numen_<your_key>"
      }
    }
  }
}
```

---

## Local stdio (numen-mcp CLI)

For local development and CI:

```json
{
  "mcpServers": {
    "numen": {
      "command": "numen-mcp",
      "env": {
        "NUMEN_API_KEY": "numen_<your_key>"
      }
    }
  }
}
```

---

## First call

Once connected, the *only* tool call your agent needs to learn the surface is:

```
hello_numen()
```

Returns: org info, member/entity counts, available tools grouped by intent,
a sample first call, your latest briefing snippet (if user-bound).

`org_id` is auto-resolved from your API key over SSE - **omit it from tool
calls.** The legacy stdio mode still requires explicit `org_id`.

## Verify auth

If something looks wrong, hit:

```bash
curl $NUMEN_URL/mcp/ \
  -H "Authorization: Bearer numen_<your_key>"
```

A `401` means the key is invalid, expired, or revoked. Visit `/account/keys`
to rotate.

## What to read next

- [`docs/recipes.md`](recipes.md) - copy-paste recipes for common workflows.
- [`docs/troubleshooting.md`](troubleshooting.md) - error code -> resolution.
- [`docs/system-prompt-cookbook.md`](system-prompt-cookbook.md) - paste-into-CLAUDE.md
  templates that nudge the agent toward the right tool calls.
