# MCP setup: API Bridge and Apify

Use this when the user wants the tools inside their MCP client instead of (or as well as) `scripts/epsimo.py`. Both servers bill exactly like the REST APIs.

Keep keys out of files that get committed or shared. Prefer environment variables; where a client needs the literal value in its config file, keep that file out of version control.

## API Bridge MCP (tools.epsimo.org)

- URL: `https://tools.epsimo.org/mcp` (Streamable HTTP, JSON-RPC 2.0).
- Auth: header `x-token: $EPSIMO_API_KEY` (or `Authorization: Bearer $EPSIMO_API_KEY`). `initialize` and `tools/list` are public; every `tools/call` needs the key.
- Tools: `qualify_company`, `enrich_company`, `find_email`, `search_french_companies`, `search_companies_near`, `scrape_page`, `ask_website`, `get_usage`. Same credits, rate limits and response bodies as REST.

### Claude Code

```bash
claude mcp add --transport http api-bridge https://tools.epsimo.org/mcp --header "x-token: $EPSIMO_API_KEY"
```

### Claude Desktop

Claude Desktop speaks stdio only, so bridge the HTTP endpoint with `mcp-remote` in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "api-bridge": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://tools.epsimo.org/mcp", "--header", "x-token:${EPSIMO_API_KEY}"],
      "env": {"EPSIMO_API_KEY": "ab_live_..."}
    }
  }
}
```

Replace `ab_live_...` with the key. There is no space after `x-token:` on purpose: some clients split arguments on spaces.

### Cursor (`.cursor/mcp.json`) and other HTTP clients

```json
{
  "mcpServers": {
    "api-bridge": {
      "type": "http",
      "url": "https://tools.epsimo.org/mcp",
      "headers": {"x-token": "ab_live_..."}
    }
  }
}
```

Add `.cursor/mcp.json` to `.gitignore` when it holds a real key.

## Apify MCP (Epsimo actors)

- URL: `https://mcp.apify.com?tools=quaking_pail/<slug>` loads one actor as a tool. Load several with commas, for example `https://mcp.apify.com?tools=quaking_pail/google-serp-scraper,quaking_pail/contact-crawler`.
- Auth: `Authorization: Bearer $APIFY_TOKEN`. Without a header the client signs in with OAuth in the browser (Apify's recommended remote option).
- Slugs: `ai-website-content-markdown-scraper`, `ai-seo-content-markdown-scraper`, `google-serp-scraper`, `google-condensed-serp-scraper`, `google-serp-scraper-lead-finder`, `linkedin-job-scraping`, `contact-crawler`, `ai-company-url-lead-qualify`.
- Runs are billed per event to the Apify account. Apify's generic `call-actor` tool accepts `maxTotalChargeUsd` in `callOptions` to cap a run.

### Claude Code

```bash
claude mcp add --transport http apify "https://mcp.apify.com?tools=quaking_pail/google-serp-scraper,quaking_pail/contact-crawler" --header "Authorization: Bearer $APIFY_TOKEN"
```

### Claude Desktop

```json
{
  "mcpServers": {
    "apify": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.apify.com?tools=quaking_pail/google-serp-scraper", "--header", "Authorization:${AUTH_HEADER}"],
      "env": {"AUTH_HEADER": "Bearer apify_api_..."}
    }
  }
}
```

The `Bearer ...` value lives in the env var so the argument list has no space in it.

### Cursor and other HTTP clients

```json
{
  "mcpServers": {
    "apify": {
      "url": "https://mcp.apify.com?tools=quaking_pail/google-serp-scraper",
      "headers": {"Authorization": "Bearer apify_api_..."}
    }
  }
}
```

Remove `headers` to sign in with OAuth instead of storing the token.

## Checking the setup

- API Bridge: call `get_usage` (free). A 403 means the key is wrong or the terms at https://tools.epsimo.org/legal/terms are not accepted.
- Apify: list the tools; the actor appears as a tool named like `quaking_pail--<slug>`. Run it once with a small cap (`max_results: 1` or `max_urls: 1`).
