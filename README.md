# Epsimo skills

Agent Skills for [Epsimo](https://epsimo.org) company data. One skill so far:

| Skill | What it does |
| --- | --- |
| [`epsimo-company-data`](skills/epsimo-company-data/SKILL.md) | Search the official French company registry (name, SIREN, NAF code, headcount, revenue, departement, postal code, GPS radius), qualify and enrich company websites, find the likely professional email of a named person, extract page text and ask questions about a site, and run the 8 Epsimo Apify actors (website to Markdown, SEO audit, Google SERP, LinkedIn leads and jobs, contact crawler, URL qualification). Exports CSV. |

The skill teaches an agent which tool fits the request, how to build valid requests, how to estimate and report the cost before spending, and how to present results (Markdown table, totals, source line, CSV). It ships a standard-library Python CLI (`scripts/epsimo.py`, Python 3.9+) that calls both products, prints the cost before every paid call, rejects misspelled fields and handles retries.

## Contents

```
skills/epsimo-company-data/
  SKILL.md                  instructions loaded by the agent
  references/api-bridge.md  every API Bridge function, fields, registry codes
  references/actors.md      every Epsimo Apify actor, input, output, price
  references/mcp-setup.md   MCP config for Claude Code, Claude Desktop, Cursor
  scripts/epsimo.py         CLI for both products (no dependencies)
  evals/evals.json          test prompts used to evaluate the skill
```

## Install

### Claude Code

Copy the skill folder into your personal or project skills directory:

```bash
git clone https://github.com/thierryteisseire/epsimo-skills.git
# all projects
mkdir -p ~/.claude/skills && cp -R epsimo-skills/skills/epsimo-company-data ~/.claude/skills/
# or one project only
mkdir -p .claude/skills && cp -R epsimo-skills/skills/epsimo-company-data .claude/skills/
```

Claude Code picks it up on the next session.

### skills CLI (Claude Code, Cursor, Codex and other agents)

With the open [skills CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add thierryteisseire/epsimo-skills --skill epsimo-company-data
# user-wide instead of project, for a specific agent
npx skills add thierryteisseire/epsimo-skills --skill epsimo-company-data -g -a claude-code
```

A project install records it in `skills-lock.json`:

```json
"epsimo-company-data": {
  "source": "thierryteisseire/epsimo-skills",
  "sourceType": "github",
  "skillPath": "skills/epsimo-company-data/SKILL.md"
}
```

### Claude.ai and Claude Desktop

Download `epsimo-company-data.skill` from the [latest release](https://github.com/thierryteisseire/epsimo-skills/releases/latest) and upload it in Settings, Capabilities, Skills. The `.skill` file is a zip of the skill folder (without `evals/`). Code execution must be enabled for the bundled CLI to run.

### Cursor, Codex and other agents

The skill is a plain folder with a `SKILL.md`, so any agent that reads Agent Skills can use it: copy `skills/epsimo-company-data` into the agent's skills directory (for example `.agents/skills/`, `.cursor/skills/` or `~/.codex/skills/`, depending on the agent), or use the skills CLI above. Agents without skill support can be pointed at `SKILL.md` directly as context. To expose the tools over MCP instead, see [`references/mcp-setup.md`](skills/epsimo-company-data/references/mcp-setup.md).

## Configuration

Set the keys for the products you use as environment variables. Do not put them in files you commit.

| Variable | Used for | Where to get it |
| --- | --- | --- |
| `EPSIMO_API_KEY` | API Bridge (`tools.epsimo.org`), sent as the `x-token` header | https://tools.epsimo.org/#signup (free plan: 100 credits per month) |
| `APIFY_TOKEN` | Epsimo Apify actors (`apify.com/quaking_pail`) | Apify Console, Settings, API & Integrations |

You only need the one for the product you use. Check the setup with:

```bash
python3 skills/epsimo-company-data/scripts/epsimo.py usage
```

## Costs

Both products bill real money. The skill estimates the cost before running and asks before large batches; `--dry-run` prints the estimate without calling anything.

API Bridge, in Epsimo credits (EUR 0.04 each; packs of 1,000 / 5,000 / 10,000 credits for 40 / 200 / 400 EUR, see https://tools.epsimo.org/#pricing):

| Call | Credits |
| --- | --- |
| `entreprise`, `entreprise-geo` (registry search, per page of up to 25) | 1 |
| `qualify` (website qualification) | 4, 1 if cached |
| `enrich` (registry + qualification + email domain/contact) | 8, 3 if cached |
| `email-verify` (likely email of a named person) | 2, free if not found |
| `question` (answer from a website's text) | 3 |
| `scrape` (text of one page) | 2 |

Apify actors, billed per event on your Apify account (FREE-tier prices at the time of writing, lower on paid plans; the Apify Store page is authoritative and `epsimo.py actor <slug> --dry-run` fetches the live price):

| Actor | Price |
| --- | --- |
| `ai-website-content-markdown-scraper` | USD 0.03 per page |
| `ai-seo-content-markdown-scraper` | USD 0.0066 per page |
| `google-serp-scraper` | USD 0.0011 per result |
| `google-condensed-serp-scraper` | USD 0.0087 per Google page of 10 |
| `google-serp-scraper-lead-finder` | USD 0.0033 per lead |
| `linkedin-job-scraping` | USD 0.00165 per job |
| `contact-crawler` | USD 0.0055 per website with a contact found |
| `ai-company-url-lead-qualify` | USD 0.011 per qualified company |

## Data and licence

Registry data comes from the API Recherche d'Entreprises (DINUM) under Licence Ouverte 2.0. Emails returned by `email-verify` are pattern-inferred, not verified; check your obligations (GDPR) before contacting anyone.

This repository is released under the [MIT License](LICENSE). MIT was chosen as the default for a permissive, widely compatible open-source licence.
