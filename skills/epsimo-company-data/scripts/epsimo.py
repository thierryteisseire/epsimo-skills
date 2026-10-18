#!/usr/bin/env python3
"""Epsimo CLI: the API Bridge (tools.epsimo.org) and the Epsimo Apify actors.

Standard library only (Python 3.9+). Keys come from the environment and are
never printed, logged or written to a file:

  EPSIMO_API_KEY   API Bridge key, sent in the x-token header
  APIFY_TOKEN      Apify API token, sent as Authorization: Bearer

Commands:

  epsimo.py usage
      Credit balance, monthly quota and per-route usage (free).

  epsimo.py call <function-id> --json '{...}' [--pages N] [--csv out.csv]
      Call one API Bridge function. Function ids: qualify, enrich, question,
      scrape, email-verify, entreprise, entreprise-geo, usage, health.

  epsimo.py actor <slug> --json '{...}' [--max-charge-usd X] [--csv out.csv]
      Run an Epsimo Apify actor synchronously and return its dataset items.

Common options:
  --json '{...}' or --json @file.json   request body / actor input
  --dry-run                             print the cost estimate, call nothing
  --csv PATH                            write a flat CSV (UTF-8 with BOM)
  --save PATH                           write the raw JSON response

The credit (or USD) cost is printed to stderr before every paid call. With
--csv, stdout gets a short JSON summary instead of the full response.

Errors: 402/403/422 stop with the API message. 429 and 503 wait Retry-After
seconds and retry once (only when the wait is 120 s or less); there is never
more than one retry.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

API_BASE = "https://tools.epsimo.org"
APIFY_BASE = "https://api.apify.com/v2"
ACTOR_OWNER = "quaking_pail"
CREDIT_EUR = 0.04
MAX_RETRY_WAIT_S = 120
USER_AGENT = "epsimo-company-data-skill/1.0"
REGISTRY_SOURCE = "API Recherche d'Entreprises (DINUM), Licence Ouverte 2.0"

# function id -> (HTTP method, path, credits, credits when cached or None)
FUNCTIONS: dict[str, tuple[str, str, int, int | None]] = {
    "qualify": ("POST", "/qualify", 4, 1),
    "enrich": ("POST", "/enrich", 8, 3),
    "question": ("POST", "/question", 3, None),
    "scrape": ("POST", "/scrape", 2, None),
    "email-verify": ("POST", "/email-verify", 2, None),
    "entreprise": ("POST", "/entreprise", 1, None),
    "entreprise-geo": ("POST", "/entreprise/geo", 1, None),
    "usage": ("GET", "/usage", 0, None),
    "health": ("GET", "/health", 0, None),
}

# Request fields per function. The API silently ignores unknown fields, so a
# misspelled filter would return unfiltered (and still billed) results.
_ENTREPRISE_FIELDS = {
    "q", "departement", "per_page", "activite_principale", "section_activite_principale",
    "categorie_entreprise", "nature_juridique", "tranche_effectif_salarie",
    "etat_administratif", "code_postal", "code_commune", "region", "epci",
    "code_collectivite_territoriale", "nom_personne", "prenoms_personne",
    "date_naissance_personne_min", "date_naissance_personne_max", "type_personne",
    "ca_min", "ca_max", "resultat_net_min", "resultat_net_max", "id_convention_collective",
    "id_finess", "id_rge", "id_uai", "convention_collective_renseignee",
    "egapro_renseignee", "est_achats_responsables", "est_alim_confiance",
    "est_association", "est_bio", "est_collectivite_territoriale",
    "est_entrepreneur_individuel", "est_entrepreneur_spectacle", "est_ess", "est_finess",
    "est_organisme_formation", "est_patrimoine_vivant", "est_qualiopi", "est_rge",
    "est_siae", "est_service_public", "est_l100_3", "est_societe_mission", "est_uai",
    "page", "page_etablissements", "limite_matching_etablissements", "minimal",
    "include", "sort_by_size",
}
KNOWN_FIELDS: dict[str, set[str]] = {
    "qualify": {"url", "refresh"},
    "enrich": {"url", "first_name", "last_name", "siren", "company_name", "refresh"},
    "question": {"url", "question"},
    "scrape": {"url"},
    "email-verify": {"url", "first_name", "last_name"},
    "entreprise": _ENTREPRISE_FIELDS,
    "entreprise-geo": {
        "lat", "long", "radius", "activite_principale", "section_activite_principale",
        "limite_matching_etablissements", "minimal", "include", "page", "per_page",
        "page_etablissements", "sort_by_size",
    },
    "usage": set(),
    "health": set(),
}
PAGINATED = {"entreprise", "entreprise-geo"}

# Actor slug -> function(input) giving the maximum number of primary events.
ACTORS: dict[str, Any] = {
    "ai-website-content-markdown-scraper": lambda i: int(i.get("max_urls", 10)),
    "ai-seo-content-markdown-scraper": lambda i: int(i.get("max_urls", 10)),
    "linkedin-job-scraping": lambda i: int(i.get("max_pages", 1)) * 10,
    "google-serp-scraper": lambda i: min(int(i.get("max_results", 100)), 300),
    "google-serp-scraper-lead-finder": lambda i: min(int(i.get("max_results", 10)), 1000),
    "contact-crawler": lambda i: len(i.get("urls") or []),
    "ai-company-url-lead-qualify": lambda i: len(i.get("domains") or []),
    "google-condensed-serp-scraper": lambda i: min(
        math.ceil(int(i.get("max_results", 100)) / 10), 30
    ),
}

HEADCOUNT = {
    "NN": "Unknown / non-employer", "00": "0 employees", "01": "1-2", "02": "3-5",
    "03": "6-9", "11": "10-19", "12": "20-49", "21": "50-99", "22": "100-199",
    "31": "200-249", "32": "250-499", "41": "500-999", "42": "1,000-1,999",
    "51": "2,000-4,999", "52": "5,000-9,999", "53": "10,000+",
}
STATUS = {"A": "Active", "C": "Ceased", "F": "Closed"}


class CliError(Exception):
    """A user-facing error; the message never contains a key."""


def info(message: str) -> None:
    print(message, file=sys.stderr)


# --- HTTP ----------------------------------------------------------------------------


def _parse(raw: bytes) -> Any:
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text) if text else None
    except json.JSONDecodeError:
        return text


def _send(method: str, url: str, headers: dict[str, str], body: Any, timeout: float):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("User-Agent", USER_AGENT)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    for name, value in headers.items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), _parse(response.read())
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers or {}), _parse(error.read())
    except urllib.error.URLError as error:
        raise CliError(f"Network error reaching {urllib.parse.urlsplit(url).netloc}: "
                       f"{error.reason}") from None
    except TimeoutError:
        raise CliError(f"Timed out after {timeout:.0f} s") from None


def request_with_retry(method, url, headers, body, timeout, describe_error):
    """Send once; on 429/503 wait Retry-After (if short) and retry exactly once."""
    status, resp_headers, payload = _send(method, url, headers, body, timeout)
    if status in (429, 503):
        wait = _retry_after(resp_headers)
        message = describe_error(status, payload)
        if wait is None or wait > MAX_RETRY_WAIT_S:
            hint = f" Retry-After is {wait} s." if wait is not None else ""
            raise CliError(f"HTTP {status}: {message}.{hint} Not retrying; try again later.")
        info(f"HTTP {status}: {message}. Waiting {wait} s, then retrying once.")
        time.sleep(wait)
        status, resp_headers, payload = _send(method, url, headers, body, timeout)
    return status, resp_headers, payload


def _retry_after(headers: dict[str, str]) -> int | None:
    for name, value in headers.items():
        if name.lower() == "retry-after":
            try:
                return max(0, int(float(value)))
            except ValueError:
                return None
    return None


# --- API Bridge ----------------------------------------------------------------------


def bridge_error(status: int, payload: Any) -> str:
    if isinstance(payload, dict):
        if payload.get("error_message"):
            return str(payload["error_message"])
        detail = payload.get("detail")
        if isinstance(detail, list):
            parts = []
            for item in detail:
                if isinstance(item, dict):
                    where = ".".join(str(p) for p in item.get("loc", []) if p != "body")
                    parts.append(f"{where}: {item.get('msg')}" if where else str(item.get("msg")))
            if parts:
                return "; ".join(parts)
        if detail:
            return str(detail)
    if isinstance(payload, str) and payload.strip():
        return payload.strip()[:300]
    return {402: "Insufficient credits", 403: "Forbidden", 422: "Validation failed",
            429: "Rate limit or monthly quota", 503: "Service busy"}.get(status, "Request failed")


_BRIDGE_HINTS = {
    402: "Buy credits at https://tools.epsimo.org/#pricing or wait for the monthly free credits.",
    403: "Check EPSIMO_API_KEY and that the key accepted https://tools.epsimo.org/legal/terms.",
    422: "Fix the request fields (see references/api-bridge.md).",
}


def bridge_key(required: bool) -> dict[str, str]:
    key = os.environ.get("EPSIMO_API_KEY", "").strip()
    if not key:
        if required:
            raise CliError("EPSIMO_API_KEY is not set. Get a free key at "
                           "https://tools.epsimo.org/#signup and export it in your shell.")
        return {}
    return {"x-token": key}


def cost_text(function_id: str, calls: int = 1) -> str:
    _, _, credits, cached = FUNCTIONS[function_id]
    if credits == 0:
        return f"{function_id}: free"
    total = credits * calls
    text = f"{function_id}: {credits} credit{'s' if credits > 1 else ''}"
    if cached is not None:
        text += f" ({cached} if cached)"
    if calls > 1:
        text += f" x up to {calls} pages = up to {total} credits"
    euros = total * CREDIT_EUR
    return text + f", EUR {euros:.2f} at EUR {CREDIT_EUR}/credit. Failed calls are free."


def check_fields(function_id: str, body: dict[str, Any]) -> None:
    unknown = sorted(set(body) - KNOWN_FIELDS[function_id])
    if unknown:
        raise CliError(f"Unknown field(s) for {function_id}: {', '.join(unknown)}. The API "
                       "ignores unknown fields, so the call would run unfiltered. "
                       "See references/api-bridge.md for the field names.")


def call_bridge(function_id: str, body: dict[str, Any]) -> Any:
    method, path, credits, _ = FUNCTIONS[function_id]
    headers = bridge_key(required=function_id != "health")
    status, _, payload = request_with_retry(
        method, API_BASE + path, headers, body if method == "POST" else None, 120, bridge_error
    )
    if status != 200:
        hint = _BRIDGE_HINTS.get(status, "")
        raise CliError(f"HTTP {status}: {bridge_error(status, payload)}. {hint}".strip())
    _warn_business_failure(function_id, payload)
    return payload


def _warn_business_failure(function_id: str, payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    status = payload.get("status")
    if function_id == "email-verify":
        if status != "valid":
            info(f"email-verify status '{status}': no address returned, not billed.")
        return
    if isinstance(status, int) and status != 200:
        message = payload.get("error_message") or "no details"
        info(f"Business failure (body status {status}): {message}. Not billed.")


def call_paginated(function_id: str, body: dict[str, Any], pages: int) -> dict[str, Any]:
    first_page = int(body.get("page", 1))
    merged: dict[str, Any] | None = None
    for offset in range(pages):
        page_body = dict(body, page=first_page + offset)
        payload = call_bridge(function_id, page_body)
        if not isinstance(payload, dict):
            raise CliError("Unexpected response shape from the registry search.")
        if merged is None:
            merged = dict(payload)
            merged["results"] = list(payload.get("results") or [])
        else:
            merged["results"].extend(payload.get("results") or [])
        merged["pages_fetched"] = offset + 1
        total_pages = int(payload.get("total_pages") or 0)
        if not payload.get("results") or first_page + offset >= total_pages:
            break
    assert merged is not None
    merged.pop("page", None)
    merged["first_page"] = first_page
    return merged


# --- Apify actors --------------------------------------------------------------------


def normalise_slug(slug: str) -> str:
    for prefix in (f"{ACTOR_OWNER}/", f"{ACTOR_OWNER}~"):
        if slug.startswith(prefix):
            slug = slug[len(prefix):]
    if slug not in ACTORS:
        raise CliError(f"Unknown actor '{slug}'. Epsimo actors: {', '.join(sorted(ACTORS))}.")
    return slug


def apify_error(status: int, payload: Any) -> str:
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        err = payload["error"]
        return f"{err.get('type', 'error')}: {err.get('message', '')}".strip(": ")
    if isinstance(payload, str) and payload.strip():
        return payload.strip()[:300]
    return "Request failed"


def actor_price(slug: str) -> dict[str, Any] | None:
    """Current pay-per-event prices from the public actor record (no token sent)."""
    try:
        status, _, payload = _send("GET", f"{APIFY_BASE}/acts/{ACTOR_OWNER}~{slug}", {}, None, 20)
    except CliError:
        return None
    if status != 200 or not isinstance(payload, dict):
        return None
    infos = (payload.get("data") or {}).get("pricingInfos") or []
    now = datetime.now(timezone.utc).isoformat()
    current = [p for p in infos if str(p.get("startedAt", "")) <= now]
    if not current:
        return None
    pricing = max(current, key=lambda p: str(p.get("startedAt", "")))
    events = ((pricing.get("pricingPerEvent") or {}).get("actorChargeEvents")) or {}
    result: dict[str, Any] = {"model": pricing.get("pricingModel"), "primary": None, "start": None}
    for name, event in events.items():
        price = event.get("eventPriceUsd")
        tiers = event.get("eventTieredPricingUsd") or {}
        if price is None and "FREE" in tiers:
            price = tiers["FREE"].get("tieredEventPriceUsd")
        entry = {"event": name, "title": event.get("eventTitle"), "usd": price}
        if event.get("isPrimaryEvent"):
            result["primary"] = entry
        elif name == "apify-actor-start":
            result["start"] = entry
    return result


def _usd(amount: float) -> str:
    return f"USD {amount:.6f}".rstrip("0").rstrip(".")


def actor_cost_text(slug: str, actor_input: dict[str, Any]) -> str:
    try:
        units = ACTORS[slug](actor_input)
    except (TypeError, ValueError):
        units = None
    price = actor_price(slug)
    store = f"https://apify.com/{ACTOR_OWNER}/{slug}"
    if not price or not price.get("primary") or price["primary"]["usd"] is None:
        return f"{slug}: pay per event on Apify; live price unavailable, check {store}."
    primary = price["primary"]
    text = f"{slug}: {_usd(primary['usd'])} per '{primary['title']}' (FREE tier"
    if price.get("start") and price["start"]["usd"] is not None:
        text += f", plus {_usd(price['start']['usd'])} actor start"
    text += ")"
    if units:
        text += f"; this input allows up to ~{units} = about {_usd(units * primary['usd'])}"
    return text + f". Billed to your Apify account; Store page: {store}"


def run_actor(slug: str, actor_input: dict[str, Any], max_charge_usd: float | None) -> Any:
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        raise CliError("APIFY_TOKEN is not set. Create a token in Apify Console "
                       "(Settings > API & Integrations) and export it in your shell.")
    query = {"format": "json", "clean": "true"}
    if max_charge_usd is not None:
        query["maxTotalChargeUsd"] = f"{max_charge_usd}"
    url = (f"{APIFY_BASE}/acts/{ACTOR_OWNER}~{slug}/run-sync-get-dataset-items?"
           + urllib.parse.urlencode(query))
    headers = {"Authorization": f"Bearer {token}"}
    status, _, payload = request_with_retry("POST", url, headers, actor_input, 330, apify_error)
    if status == 408:
        raise CliError("HTTP 408: the run took longer than 300 s. Lower max_results / max_urls, "
                       "or start it asynchronously (POST /v2/acts/.../runs) and fetch the dataset.")
    err = payload.get("error") if isinstance(payload, dict) else None
    if status == 403 and isinstance(err, dict) and err.get("type") == "full-permission-actor-not-approved":
        approval = (err.get("data") or {}).get("approvalUrl") or f"https://apify.com/{ACTOR_OWNER}/{slug}"
        raise CliError(
            "HTTP 403 full-permission-actor-not-approved: this Apify account has not yet approved the "
            f"actor's permissions (one time per account, nothing was charged). The account owner opens "
            f"{approval} in Apify Console, reviews and approves, then reruns the same command. "
            "An agent cannot approve it on the user's behalf.")
    if status >= 400:
        hint = {401: "Check APIFY_TOKEN.", 402: "Your Apify account is out of credit.",
                403: "The token lacks permission for this actor."}.get(status, "")
        raise CliError(f"HTTP {status}: {apify_error(status, payload)}. {hint}".strip())
    return payload


# --- CSV -----------------------------------------------------------------------------


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ("" if value is None else str(value))


def _office(office: Any) -> tuple[str, str]:
    if not isinstance(office, dict):
        return "", ""
    return _text(office.get("libelle_commune")), _text(office.get("code_postal"))


def _person(person: Any) -> str:
    if not isinstance(person, dict):
        return _text(person)
    if person.get("type_dirigeant") == "personne morale":
        name = _text(person.get("denomination")) or _text(person.get("siren"))
    else:
        name = " ".join(p for p in (_text(person.get("prenoms")), _text(person.get("nom"))) if p)
        name = name or _text(person.get("denomination"))
    role = _text(person.get("qualite"))
    return f"{name} ({role})" if name and role else name or role


def _latest_finances(finances: Any) -> tuple[str, Any, Any]:
    if not isinstance(finances, dict):
        return "", None, None
    years = sorted(y for y, v in finances.items() if str(y).isdigit() and isinstance(v, dict))
    if not years:
        return "", None, None
    row = finances[years[-1]]
    return years[-1], row.get("ca"), row.get("resultat_net")


ENTREPRISE_COLUMNS = [
    "name", "siren", "matching_office_commune", "matching_office_postal_code",
    "matching_office_address", "other_matching_offices", "hq_city", "hq_postal_code",
    "activity_code", "activity_label", "category", "headcount", "status", "revenue_eur",
    "net_income_eur", "fiscal_year", "directors", "source",
]


def entreprise_row(company: dict[str, Any]) -> dict[str, Any]:
    offices = [o for o in (company.get("matching_etablissements") or []) if isinstance(o, dict)]
    first = offices[0] if offices else {}
    commune, postal = _office(first)
    others = ["{} {}".format(*_office(o)).strip() for o in offices[1:]]
    siege = company.get("siege") if isinstance(company.get("siege"), dict) else {}
    year, revenue, net_income = _latest_finances(company.get("finances"))
    headcount = _text(company.get("tranche_effectif_salarie"))
    return {
        "name": _text(company.get("nom_complet")) or _text(company.get("nom_raison_sociale")),
        "siren": _text(company.get("siren")),
        "matching_office_commune": commune,
        "matching_office_postal_code": postal,
        "matching_office_address": _text(first.get("adresse")),
        "other_matching_offices": "; ".join(o for o in others if o),
        "hq_city": _text(siege.get("libelle_commune")),
        "hq_postal_code": _text(siege.get("code_postal")),
        "activity_code": _text(company.get("activite_principale")),
        "activity_label": _text(company.get("libelle_activite_principale")),
        "category": _text(company.get("categorie_entreprise")),
        "headcount": HEADCOUNT.get(headcount, headcount),
        "status": STATUS.get(_text(company.get("etat_administratif")),
                             _text(company.get("etat_administratif"))),
        "revenue_eur": revenue,
        "net_income_eur": net_income,
        "fiscal_year": year,
        "directors": "; ".join(p for p in map(_person, company.get("dirigeants") or []) if p),
        "source": REGISTRY_SOURCE,
    }


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, inner in value.items():
            out.update(flatten(inner, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        if all(not isinstance(v, (dict, list)) for v in value):
            out[prefix or "value"] = "; ".join(_text(v) for v in value)
        else:
            out[prefix or "value"] = json.dumps(value, ensure_ascii=False)
    else:
        out[prefix or "value"] = value
    return out


def rows_for(kind: str, payload: Any) -> tuple[list[str], list[dict[str, Any]]]:
    if kind in PAGINATED and isinstance(payload, dict):
        companies = [c for c in payload.get("results") or [] if isinstance(c, dict)]
        return ENTREPRISE_COLUMNS, [entreprise_row(c) for c in companies]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("results"), list):
        items = payload["results"]
    else:
        items = [payload]
    rows = [flatten(item) for item in items]
    columns: list[str] = []
    for row in rows:
        columns.extend(k for k in row if k not in columns)
    return columns, rows


def _safe_cell(value: Any) -> Any:
    # Neutralise spreadsheet formulas in scraped text (CSV injection); numbers stay numbers.
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def write_csv(path: str, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: _safe_cell(row.get(c)) for c in columns})


# --- CLI -----------------------------------------------------------------------------


def load_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    if raw.startswith("@"):
        try:
            with open(raw[1:], encoding="utf-8") as handle:
                raw = handle.read()
        except OSError as error:
            raise CliError(f"Cannot read {raw[1:]}: {error.strerror}") from None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CliError(f"--json is not valid JSON: {error.msg} (position {error.pos})") from None
    if not isinstance(value, dict):
        raise CliError("--json must be a JSON object, for example '{\"url\": \"https://acme.fr\"}'")
    return value


def emit(kind: str, payload: Any, args: argparse.Namespace) -> None:
    if args.save:
        with open(args.save, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        info(f"Saved raw JSON to {args.save}")
    if not args.csv:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    columns, rows = rows_for(kind, payload)
    write_csv(args.csv, columns, rows)
    summary: dict[str, Any] = {"csv": args.csv, "rows": len(rows), "columns": columns}
    if isinstance(payload, dict):
        for key in ("total_results", "total_pages", "first_page", "pages_fetched", "source"):
            if key in payload:
                summary[key] = payload[key]
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Epsimo API Bridge and Apify actors CLI (keys from EPSIMO_API_KEY / "
                    "APIFY_TOKEN, never printed).")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--csv", help="write results as a flat CSV to this path")
        p.add_argument("--save", help="write the raw JSON response to this path")

    common(sub.add_parser("usage", help="credit balance and usage this month (free)"))

    call = sub.add_parser("call", help="call one API Bridge function")
    call.add_argument("function", choices=sorted(FUNCTIONS))
    call.add_argument("--json", help="request body as JSON, or @file.json")
    call.add_argument("--pages", type=int, default=1,
                      help="entreprise / entreprise-geo: fetch this many pages (1 credit each)")
    call.add_argument("--dry-run", action="store_true", help="print the cost only")
    common(call)

    actor = sub.add_parser("actor", help="run an Epsimo Apify actor (quaking_pail)")
    actor.add_argument("slug", help=f"one of: {', '.join(sorted(ACTORS))}")
    actor.add_argument("--json", help="actor input as JSON, or @file.json")
    actor.add_argument("--max-charge-usd", type=float,
                       help="cap the run cost (Apify maxTotalChargeUsd)")
    actor.add_argument("--dry-run", action="store_true", help="print the live price only")
    common(actor)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "usage":
            emit("usage", call_bridge("usage", {}), args)
            return 0

        if args.command == "call":
            body = load_json(args.json)
            check_fields(args.function, body)
            if args.pages < 1:
                raise CliError("--pages must be 1 or more")
            if args.pages > 1 and args.function not in PAGINATED:
                raise CliError("--pages only applies to entreprise and entreprise-geo")
            info("Cost: " + cost_text(args.function, args.pages))
            if args.dry_run:
                return 0
            if args.pages > 1:
                payload = call_paginated(args.function, body, args.pages)
            else:
                payload = call_bridge(args.function, body)
            emit(args.function, payload, args)
            return 0

        slug = normalise_slug(args.slug)
        actor_input = load_json(args.json)
        info("Cost: " + actor_cost_text(slug, actor_input))
        if args.dry_run:
            return 0
        emit(slug, run_actor(slug, actor_input, args.max_charge_usd), args)
        return 0
    except CliError as error:
        info(f"Error: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
