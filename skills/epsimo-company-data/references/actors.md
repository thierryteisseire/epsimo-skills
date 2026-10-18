# Epsimo Apify actors reference (Apify user quaking_pail)

Derived from https://epsimo.org/llms-full.txt (recorded from the public Apify API on 2026-10-18). Per-actor files with the full README: `https://epsimo.org/actors/<slug>.md`. Prices change: `scripts/epsimo.py actor <slug> --dry-run` prints the live price, and the Apify Store page is authoritative.

## Contents

1. [How to run any actor](#how-to-run-any-actor)
2. [Which actor for which job](#which-actor-for-which-job)
3. [ai-website-content-markdown-scraper](#ai-website-content-markdown-scraper)
4. [ai-seo-content-markdown-scraper](#ai-seo-content-markdown-scraper)
5. [google-serp-scraper](#google-serp-scraper)
6. [google-condensed-serp-scraper](#google-condensed-serp-scraper)
7. [google-serp-scraper-lead-finder](#google-serp-scraper-lead-finder)
8. [linkedin-job-scraping](#linkedin-job-scraping)
9. [contact-crawler](#contact-crawler)
10. [ai-company-url-lead-qualify](#ai-company-url-lead-qualify)

## How to run any actor

- Token: an Apify API token in `$APIFY_TOKEN` (Apify Console, Settings, API & Integrations). Send it as `Authorization: Bearer $APIFY_TOKEN`; avoid `?token=` because URLs end up in logs.
- Billing: pay per event on the user's Apify account (not Epsimo credits). Every run also has a tiny `apify-actor-start` event (USD 0.00005 per GB of memory on the FREE tier).
- Synchronous run that returns the dataset items:

```bash
curl -X POST "https://api.apify.com/v2/acts/quaking_pail~<slug>/run-sync-get-dataset-items" \
  -H "Authorization: Bearer $APIFY_TOKEN" \
  -H "Content-Type: application/json" \
  -d @input.json
```

- Runs longer than 300 s return HTTP 408 on that endpoint. Lower the result cap, or start the run asynchronously (`POST https://api.apify.com/v2/acts/quaking_pail~<slug>/runs`) and read the dataset when it finishes.
- `maxTotalChargeUsd` (query parameter) caps the cost of a run; `scripts/epsimo.py actor ... --max-charge-usd 0.50` sets it.
- MCP: `https://mcp.apify.com?tools=quaking_pail/<slug>` loads one actor as a tool (comma-separate several). See `mcp-setup.md`.
- Output is scraped from public pages: it can be incomplete, outdated or wrong. Results can contain personal data (GDPR applies); the user is responsible for lawful use.

## Which actor for which job

| Job | Actor | Billed per (FREE tier, 2026-10-18) |
| --- | --- | --- |
| Website pages as clean Markdown (RAG, agents) | `ai-website-content-markdown-scraper` | page, USD 0.03 |
| SEO audit of each page + Markdown | `ai-seo-content-markdown-scraper` | page, USD 0.0066 |
| Google organic results, one row per result | `google-serp-scraper` | result, USD 0.0011 |
| Google results condensed into one text for an LLM | `google-condensed-serp-scraper` | Google page of 10, USD 0.0087 |
| Public LinkedIn profiles matching a description | `google-serp-scraper-lead-finder` | lead, USD 0.0033 |
| LinkedIn job listings by keyword and location | `linkedin-job-scraping` | job, USD 0.00165 |
| Emails, phones, team names published on company sites | `contact-crawler` | website with a contact found, USD 0.0055 |
| Value proposition, industry, market from domains (batch) | `ai-company-url-lead-qualify` | qualified company, USD 0.011 |

Paid Apify plans get lower tiered prices (BRONZE to DIAMOND). One page of a single site through the API Bridge (`scrape`, 2 credits = EUR 0.08) can be cheaper to set up than an actor run when the user already has an Epsimo key and no Apify token.

## ai-website-content-markdown-scraper

Crawls a website (headless Chrome, same domain) and returns each page's main content as Markdown with URL and title.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `start_urls` | array of `{"url": ...}` | yes | - | Start pages. |
| `max_depth` | integer | no | 1 | Link depth. |
| `max_urls` | integer | no | 10 | Page cap = cost cap. |
| `search_engine` | string | no | `Google` | `Google`, `Bing`, `DuckDuckGo`, `None`. Discovers extra same-domain pages first; `None` is faster and cheaper. |

```json
{"start_urls": [{"url": "https://example.com"}], "max_depth": 1, "max_urls": 10, "search_engine": "None"}
```

Output per page: `url`, `title`, `content` (Markdown). Failed pages are not stored or charged. Bot-blocking sites can still fail. Fewer pages than `max_urls` means the site has fewer links within `max_depth`.

## ai-seo-content-markdown-scraper

Store name "Ai SEO Content Curator". Audits every page (title, meta description, headings, canonical, Open Graph, status code) and returns the main content as Markdown.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `start_urls` | array of `{"url": ...}` | yes | - | |
| `max_depth` | integer | no | 1 | 0 = start URLs only. |
| `max_urls` | integer | no | 10 | One dataset item (and charge) per page. |
| `search_engine` | string | no | `Google` | Label only; does not change scraping. |

Output per page: `url`, `info` (`status`, `title`, `htmlLang`, `wordCount`, ...), `network` (`HttpResponseCode`, `loadTime`, `HttpContentType`), `seoAudit` (checks valued `ok`, `absent`, `problematic`, `missing`, plus counts such as `h1Count`), `content`, `timestamp`, `search_engine`. No overall SEO score. Pages with error status (404) are stored with their status code and charged, since that is an audit result.

## google-serp-scraper

Google organic results: title, URL, breadcrumb, snippet. The query is built from the fields.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `search_query_base` | string | yes | - | Market or type of company, e.g. `expert comptable`. |
| `domain` | string | no | `""` | Industry added to the query. |
| `location` | string | no | `""` | City or country added to the query. |
| `info_to_retrieve` | string | no | `""` | Exact phrase added in quotes (e.g. `email`). Leave blank unless needed, it narrows results. |
| `max_results` | integer | no | 100 | 1-300 (about 10 per Google page, max 30 pages). Cost cap. |
| `proxyConfiguration` | object | no | `{"useApifyProxy": true, "apifyProxyGroups": ["GOOGLE_SERP"]}` | Keep the default group. |

```json
{"search_query_base": "expert comptable", "location": "Nice", "max_results": 10}
```

Output per result: `title`, `url`, `displayedUrl`, `description`, `emphasizedKeywords`, `type` (always `organic`), `urlType`. `urlType: "exact"` = deep link; `urlType: "origin"` = Google encrypted the link, so `url` is only the site homepage. Say which when presenting.

Limits: results come from Google in English for the US, so put the city in `location`. Ads, maps pack and featured snippets are not included; the order is the scraped organic order, not a guaranteed live ranking. "No search results were scraped" = blocked or empty query; rerun once with the default proxy.

Fallback while the actor is not yet approved on the user's account (HTTP 403 `full-permission-actor-not-approved`, see SKILL.md section 5): Apify's own `apify/google-search-scraper`. It is not an Epsimo actor, so label its output as such. The CLI only runs `quaking_pail` actors, so call it directly:

```bash
curl -s -X POST "https://api.apify.com/v2/acts/apify~google-search-scraper/run-sync-get-dataset-items?maxTotalChargeUsd=0.50" \
  -H "Authorization: Bearer $APIFY_TOKEN" -H "Content-Type: application/json" \
  -d '{"queries":"expert comptable Nice","countryCode":"fr","languageCode":"fr","maxPagesPerQuery":1,"resultsPerPage":10}'
```

- It rejects `maxTotalChargeUsd` below 0.50; that is a cap, not the price (one page of 10 results cost about USD 0.002 in testing). Check the live price on https://apify.com/apify/google-search-scraper before larger runs.
- Output: one item per Google page, results in `organicResults[]` (`position`, `title`, `url`, `displayedUrl`, `description`). Unlike the Epsimo actor it can query google.fr in French, so the ranking can differ.

## google-condensed-serp-scraper

Google results as one condensed text (`Title: snippet` separated by ` /**/ `), for an LLM prompt or market overview.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `search_query_base` | string | yes | `société de conseil` | |
| `domain` | string | yes | `IA` | Industry; also accepts operators like `site:linkedin.com/company` or `-jobs`. |
| `location` | string | yes | `Paris` | |
| `info_to_retrieve` | string | yes | `email, website` | Added in quotes. |
| `max_results` | integer | no | 100 | ceil(max_results / 10) Google pages, max 30. |
| `proxyConfiguration` | object | no | GOOGLE_SERP | Keep the default. |

Output (one row): `searchUrl`, `resultsText`, `resultsCount`, `pagesUsed`. Billed per Google page used (`serp-page`); the summary row is free. No URLs per result: use `google-serp-scraper` when the user needs links or a table.

## google-serp-scraper-lead-finder

Public LinkedIn profiles that match a plain-language description, found through Google. No login.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `profile_description` | string | yes | - | e.g. `head of growth saas`. |
| `location` | string | no | - | e.g. `Paris, France`. |
| `exclude_keywords` | array | no | - | Words to exclude; runs with exclusions may return fewer leads. |
| `max_results` | integer | no | 10 | 1-10000, capped to 1000. Cost cap. |
| `scrape_profiles` | boolean | no | `true` | Visit each profile for name, headline, location. `false` is faster; you lose only location. |
| `search_engine_strategy` | string | no | `google_with_fallback` | Keep the default (Bing is unreliable). |
| `use_direct_linkedin` | boolean | no | `false` | With `linkedin_urls`, scrape given profiles. |
| `linkedin_urls` | array | no | - | |
| `proxy_country` | string | no | `US` | `US`, `UK`, `FR`, `DE`, `CA`, `AU`, `JP`, `SG`, `NL`, `BR`, `IN`. |
| `proxy_groups`, `google_proxy_groups` | array | no | - | Leave `google_proxy_groups` empty (uses GOOGLE_SERP). |
| `max_captcha_retries` | integer | no | 3 | 1-10. |

Output per lead: `title`, `profileUrl`, `description`, `displayedUrl`, `name`, `headline`, `location`, `profileScraped`, `source`, `sourceSearchEngine`, `note` (e.g. login wall, snippet only), `scrapedAt`. A run with no leads fails and charges no leads. This is personal data: the user needs a legitimate reason under GDPR.

## linkedin-job-scraping

LinkedIn job listings by keyword and location from public guest pages (no login, no cookies), de-duplicated.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `keywords` | string | yes | `SDR` | Job title or role. |
| `location` | string | yes | `Paris` | |
| `max_pages` | integer | yes | 1 | About 10 jobs per page. Start with 1. |
| `proxyConfiguration` | object | no | off | Enable if the log shows many 429 / 999 responses (proxy billed to the Apify account). |

Output per job: `Title`, `Company`, `Location`, `Link`, `Description` (`No description available` when LinkedIn returned none). Note the capitalised field names. LinkedIn's guest search shows at most about 1,000 jobs per query: split large searches by location or keyword.

## contact-crawler

Store name "Website Contacts Crawler". Emails, phone numbers, team names and LinkedIn links published on company websites (homepage plus discovered contact, team, about, leadership pages). One row per site.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `urls` | array of string | yes | - | Main company domains work best. |
| `maxPagesPerSite` | integer | no | 10 | 1-50. |
| `delayBetweenRequests` | integer | no | 2 | Seconds, 0-30. |

Output per site: `company_name` (derived from the domain), `url`, `emails` (max 20), `phones` (max 10), `people` (names found next to a job title, max 30), `linkedin` (max 30), `pages_crawled`, `pages_failed`. Charged only for sites where at least one email or phone was found. Reads HTML only: JavaScript-rendered sites can return nothing. These emails were published on the site (not inferred), which is different from `email-verify`.

## ai-company-url-lead-qualify

Value proposition, industry, target market and target profile for a batch of domains.

| Input | Type | Required | Notes |
| --- | --- | --- | --- |
| `domains` | array of string | yes | Bare domains, e.g. `["danone.com", "qonto.com"]`. |

Output fields (dataset view, types not published): `company_domain`, `value_proposition`, `industry`, `target_audience`, `market`. Failed domains are not charged. LLM-generated estimate. It is the batch, Apify-billed equivalent of the API Bridge `qualify` function (4 credits = EUR 0.16 per site, 1 credit if cached).
