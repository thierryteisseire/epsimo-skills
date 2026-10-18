---
name: epsimo-company-data
description: Company data and lead generation with Epsimo. The API Bridge (tools.epsimo.org) searches the official French company registry by name, SIREN, NAF code, headcount, revenue, departement, postal code or GPS radius, qualifies and enriches company websites, finds the likely professional email of a named person, extracts page text and answers questions about a site. The 8 Epsimo Apify actors (quaking_pail) scrape websites to Markdown, audit SEO, scrape Google SERPs, find LinkedIn leads, scrape LinkedIn jobs and crawl website contacts. Use this skill whenever the user wants to find French companies or look up a SIREN, build a lead or prospect list by departement, city or postal code, qualify or enrich company websites, find a CEO or contact email, scrape a website to Markdown, scrape Google results or LinkedIn jobs, or export company data to CSV, and whenever they mention Epsimo, tools.epsimo.org, epsimo.org, API Bridge or quaking_pail, even if they do not name the tool.
---

# Epsimo company data

Two products, one skill:

- **API Bridge** (`https://tools.epsimo.org`): REST + MCP API for B2B company data, billed in Epsimo credits (EUR 0.04 each). Key in the `x-token` header, read from `EPSIMO_API_KEY`.
- **Epsimo Apify actors** (`https://apify.com/quaking_pail`): 8 scrapers and lead tools, billed per event on the user's Apify account. Token read from `APIFY_TOKEN`.

The bundled CLI `scripts/epsimo.py` (path relative to this skill's directory; Python 3.9+, standard library only) calls both, prints the cost before every paid call, handles errors and retries, and exports CSV. Prefer it over hand-written curl: it refuses misspelled fields (the API silently ignores them and would bill an unfiltered search) and it flattens registry results correctly.

Reference files, read the one you need before building a request:

- `references/api-bridge.md`: every API Bridge function, all request fields, registry codes (headcount brackets, NAF, sections), response fields.
- `references/actors.md`: every actor, its input, output, limits and price.
- `references/mcp-setup.md`: MCP configuration for Claude Code, Claude Desktop and Cursor, for both servers.

## 1. Choose the tool

| The user wants | Use | Cost |
| --- | --- | --- |
| French companies by name, NAF activity, size, headcount, revenue, departement, postal code, director | `call entreprise` | 1 credit per page of up to 25 |
| French companies around a GPS point (max 50 km) | `call entreprise-geo` | 1 credit per page |
| Industry, audience, B2B/B2C, value proposition of one website | `call qualify` | 4 credits, 1 if cached |
| Registry record + qualification + email domain (+ contact email) in one call | `call enrich` | 8 credits, 3 if cached |
| Likely email of a named person at a known company website | `call email-verify` | 2 credits, free if not found |
| A short fact stated on a website (offer, pricing, leadership page) | `call question` | 3 credits |
| Text of one page | `call scrape` | 2 credits |
| Balance and quota | `usage` | free |
| Many pages of a site as Markdown | actor `ai-website-content-markdown-scraper` | Apify, per page |
| SEO audit of a site | actor `ai-seo-content-markdown-scraper` | Apify, per page |
| Google results as rows (title, URL, snippet) | actor `google-serp-scraper` | Apify, per result |
| Google results as one text blob for an LLM | actor `google-condensed-serp-scraper` | Apify, per Google page |
| Public LinkedIn profiles matching a description | actor `google-serp-scraper-lead-finder` | Apify, per lead |
| LinkedIn job listings | actor `linkedin-job-scraping` | Apify, per job |
| Emails and phones published on company sites | actor `contact-crawler` | Apify, per site with a contact |
| Qualify a batch of domains on Apify | actor `ai-company-url-lead-qualify` | Apify, per company |

When both products can do the job, use the one the user has a key for. If they have neither, the API Bridge free plan (100 credits per month, https://tools.epsimo.org/#signup) is the quicker start; Apify needs an account and token.

## 2. Check keys without exposing them

```bash
python3 scripts/epsimo.py usage                     # needs EPSIMO_API_KEY, free
test -n "$APIFY_TOKEN" && echo "APIFY_TOKEN is set"  # never echo the value
```

Never print, log, paste into a URL, write to a file or commit `EPSIMO_API_KEY` or `APIFY_TOKEN`. Do not read `.env` files to find them. If a key is missing, tell the user where to get it and ask them to export it in their shell; do not ask them to paste it into the chat.

## 3. Estimate the cost, then run

Credits and Apify charges are real money, so the user should know the cost before you spend it.

1. Build the request from the reference file. For registry searches, start with `per_page: 25` and read `total_results` and `total_pages` from the first page.
2. Estimate: credits x calls (x EUR 0.04), or Apify price x result cap. `--dry-run` prints the estimate without calling anything; for actors it fetches the live price from the public Apify record.
3. Before a batch (more than a handful of paid calls), run `usage` and compare `free_balance + purchased_balance` and the remaining monthly quota to the estimate. If the batch costs more than about 50 credits or USD 1, or would use most of the balance, state the cost and ask before running.
4. Run with the CLI. Cap actor runs with `--max-charge-usd` and with the actor's own limit (`max_results`, `max_urls`, `max_pages`).
5. Afterwards, report what was spent: the `credits_consumed` difference between the two `usage` calls, or the sum of per-call prices if other jobs share the key. If it stays at 0 after paid calls, the key is not metered; say so and give the list-price cost instead.

### CLI quick reference

```bash
# Registry search, 3 pages of 25 (3 credits), straight to CSV
python3 scripts/epsimo.py call entreprise --pages 3 --csv firms.csv \
  --json '{"activite_principale":"69.20Z","departement":"06","etat_administratif":"A","per_page":25}'

# One website
python3 scripts/epsimo.py call qualify --json '{"url":"https://acme.fr"}'
python3 scripts/epsimo.py call email-verify --json '{"url":"https://acme.fr","first_name":"Jean","last_name":"Dupont"}'

# Apify actor with a cost cap
python3 scripts/epsimo.py actor google-serp-scraper --max-charge-usd 0.10 --csv serp.csv \
  --json '{"search_query_base":"expert comptable","location":"Nice","max_results":10}'

# Estimate only
python3 scripts/epsimo.py actor contact-crawler --dry-run --json '{"urls":["https://example.com"]}'
```

- Cost and warnings go to stderr; data goes to stdout as JSON.
- `--csv PATH` writes a flat UTF-8 CSV (opens cleanly in Excel) and prints only a summary (`rows`, `columns`, `total_results`, ...) to stdout, which keeps large results out of your context. Read the CSV to build the answer.
- `--save PATH` keeps the raw JSON, so you never pay twice for the same data.
- `--json @input.json` reads the body from a file.
- `--pages N` (registry only) fetches consecutive pages and stops at the last one.
- Exit code 1 with `Error: ...` on stderr means nothing usable came back. Read the message before doing anything else.

## 4. Location searches: report the matching office, not the HQ

`departement`, `code_postal`, `code_commune`, `region`, `epci` and the geo search match **any establishment (office)** of a company, not its head office. A Courbevoie (92) firm with one branch in Nice is a correct result for `departement: "06"`, and its `siege` still says Courbevoie. Users read that as "wrong location" unless you show the office that matched.

- The matched offices are in `matching_etablissements` (commune, postal code, address, SIRET). The CSV export puts them first: `matching_office_commune`, `matching_office_postal_code`, `matching_office_address`, `other_matching_offices`, then `hq_city`, `hq_postal_code`.
- In tables, lead with the matching office and label the HQ column "HQ" so the difference is visible. Add one line explaining that HQ can be elsewhere.
- If the user wants companies **headquartered** in the area, filter the rows yourself on `hq_postal_code` (or `siege.code_postal`) starting with the departement code and say how many were dropped. There is no HQ-only filter in the API.
- `activite_principale`, `tranche_effectif_salarie` and `categorie_entreprise` describe the legal unit (the whole company), not the office.

## 5. Handle errors without looping

| What you see | Meaning | Do |
| --- | --- | --- |
| HTTP 402 | Not enough credits (`route costs N, available M`) | Stop. Report balance, link https://tools.epsimo.org/#pricing (packs: 1,000 / 5,000 / 10,000 credits for 40 / 200 / 400 EUR). |
| HTTP 403 | Bad or missing key, or terms not accepted | Stop. Ask the user to check `EPSIMO_API_KEY` and accept https://tools.epsimo.org/legal/terms. |
| HTTP 422 | A field is invalid | Fix the named field and resend once. |
| HTTP 429 | Rate limit (free keys 60 requests/minute, pro 300) or monthly quota | The CLI waits `Retry-After` and retries once. If it still fails, or the quota is reached, stop and tell the user. |
| HTTP 503 | French registry busy, 0 credits | Same as 429: one retry after `Retry-After`, then stop. |
| HTTP 200 with body `status` not 200 | Business failure (site unreadable, invalid URL, nothing found) | Not billed. Report it for that row and move on. |
| `email-verify` `status` `not_found` / `suppressed` | No address, or the person or domain opted out | Free. Never try to work around a suppression. |
| Apify 408 | Run over 300 s | Lower the cap or run asynchronously (see `references/actors.md`). |
| Apify 403 `full-permission-actor-not-approved` | First run of this actor on this Apify account; nothing was charged | See "First run of an actor" below. |

### First run of an actor on an Apify account

Some Epsimo actors ask for full account permissions, and Apify makes the account owner approve that once, by hand, before the first API run. The error body carries an `approvalUrl` (the CLI prints it). Retrying cannot help and an agent cannot approve on the user's behalf, because the approval is a trust decision about the user's own account.

What the user needs from you is the result plus a way to get the Epsimo actor working next time, so do not just stop:

1. Give them the approval link and say it is one click, once per account (Apify Console, review the permissions, approve). Then the same command works.
2. If you can talk to the user, ask whether they want to approve and rerun, or get the results now from an alternative.
3. If you cannot ask (batch or unattended run), or they asked for results right away, use the closest alternative and say so in the deliverable: for Google results, Apify's own `apify/google-search-scraper` (input and cost cap in `references/actors.md`); for one page of text, `call scrape`; for website qualification, `call qualify`. Label the output with the tool that actually produced it, because the columns, locale and price differ from the Epsimo actor.

Never retry a failing call in a loop, and never re-run a paid batch just to reformat its output: use `--save` and work from the saved JSON.

## 6. Present results honestly

- **Emails are guesses.** `email-verify` and the `enrich` contact are inferred from published address patterns and MX/SPF/DMARC checks; the mailbox is never probed (no SMTP). Label them "likely" or "pattern-inferred", show `confidence`, and never call them verified or deliverable. Emails from `contact-crawler` were published on the website; say that instead.
- **Qualification is an estimate.** Industry, market, audience and answers come from a language model reading the website.
- **Cite the registry.** With French registry data, add: "Source: API Recherche d'Entreprises (DINUM), Licence Ouverte 2.0".
- **Show the denominator.** "25 of 539 matching companies (page 1 of 22)" tells the user how much is left and what the rest would cost.
- **Translate codes.** Headcount codes (`11` = 10-19 employees), status (`A` = active), category (`PME` = SME). The CSV export already does this.
- **Missing is not zero.** Empty finances mean not published. A revenue of 0 next to a non-zero net income usually means revenue was not disclosed.
- **Directors are legal roles.** `dirigeants` lists legal representatives (`Président de SAS`, `Gérant`, `Directeur Général`), sometimes a holding company rather than a person. For "the CEO" of a French company, the `Président` or `Directeur Général` is the best registry signal; say which role you used.
- **Scraped data can be stale or wrong.** SERP and LinkedIn results reflect what the scraper saw at run time.
- Personal data (names, emails, LinkedIn profiles) falls under GDPR. When the user builds outreach lists, a one-line reminder about lawful use is enough.

Default output: a Markdown table with the most useful columns, followed by the total, the cost, the source line and any caveat that applies. Offer the CSV when there are more than about 20 rows or the user asked for a file.

## 7. Recipes

### Lead list from the registry (departement, activity, size) to CSV

1. Map the request to filters: activity to a NAF code (`69.20Z` accounting, more in `references/api-bridge.md`), "at least 10 employees" to `tranche_effectif_salarie: "11,12,21,22,31,32,41,42,51,52,53"`, active only with `etat_administratif: "A"`, location with `departement` (two digits, keep the leading zero: `"06"`).
2. Fetch page 1 with `per_page: 25` and `--save`. Read `total_results` / `total_pages`; total cost = `total_pages` credits.
3. If the rest is cheap (a few credits), fetch it with `--pages`; otherwise ask how many the user wants.
4. Export with `--csv`. Present the top rows with the matching office first, the count, the cost and the source line.

A plain-text `q` such as "comptable" matches names, so it misses firms with unrelated names and catches unrelated ones. Prefer the NAF code and add `q` only to narrow by name.

### Qualify websites and find the CEO's likely email

Per company:

1. `qualify` the URL (4 credits, 1 if cached).
2. Match the website to its legal entity (see below), then take the CEO from that entity's `dirigeants`: the `Président` / `Directeur Général` (or `Gérant`). Non-French company: `question` with "Who is the CEO or founder?" (3 credits, answer comes only from the site's text), or ask the user.
3. `email-verify` with the URL, first and last name (2 credits, free if not found).

That is about 7 credits per French company. `enrich` with `first_name` / `last_name` does registry + qualification + contact in one call (8 credits) once you know the name. Present one row per company: name, SIREN, industry, market, value proposition, CEO (with role and where the name came from), likely email with confidence, and the "pattern-inferred, not verified" caveat.

**Matching a website to the right legal entity.** A brand name search can return dozens of entities: groups have a holding, operating subsidiaries and namesakes, and the biggest or first result is often not the one behind the site. Picking the wrong one gives the wrong CEO, so treat the match as something to establish, not assume:

- One clear hit (same name, active, plausible size): use it.
- Several entities sharing the brand: the site's legal notice (mentions légales, linked in the footer; French law requires it) names the publisher and its SIREN. Read it if you can fetch pages yourself, or `call scrape` on that page (2 credits), then look the SIREN up with `entreprise` `q` = SIREN.
- If that entity's `Président` is itself a company (a holding), the person the user means by "CEO" usually leads the group: look the holding up by its SIREN and take its `Président` / `Gérant`.
- Report the SIREN and, when it was not obvious, one line on how you matched it (e.g. "site published by X, SIREN ..., subsidiary of holding Y").

### Google results as a table

1. Actor `google-serp-scraper` with `search_query_base` = the keywords, `location` = the city, `max_results` = what the user asked for (10 results = about USD 0.011 on the FREE tier, plus the start event).
2. Run with `--max-charge-usd` set a little above the estimate. On a 403 `full-permission-actor-not-approved`, follow "First run of an actor" in section 5.
3. Table: rank (dataset order), title, URL, displayed URL, snippet. When `urlType` is `origin`, mark the URL as the homepage only.
4. Mention that results come from Google in English for the US with the city in the query, so the order may differ from what the user sees in their own browser.

### Website to Markdown

One page: `call scrape` (2 credits, plain text). Several pages or a whole site: actor `ai-website-content-markdown-scraper` with `max_urls` as the cost cap and `search_engine: "None"` unless extra discovery is needed.

## 8. Do not

- Do not present an inferred email as verified or deliverable.
- Do not report a company's HQ as the place that matched a location filter.
- Do not start a bulk run without checking `usage` and telling the user the cost.
- Do not loop on 429 or 503: one retry after `Retry-After`, then stop.
- Do not send fields that are not in the reference tables.
- Do not print, log, commit or put in a URL any API key or token.
- Do not hardcode actor prices in what you tell the user as current: use `--dry-run` or the Store page.
