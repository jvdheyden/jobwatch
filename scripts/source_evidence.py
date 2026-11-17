"""Bounded posting evidence shared by setup, curation and quality evaluation."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from source_config import file_lock, write_json_atomic

MAX_REFERENCES = 20
MAX_CANARIES = 40
MAX_SOURCE_CANARIES = 5
EVIDENCE_MAX_BYTES = 64 * 1024
PROVENANCES = {"user_supplied", "official_page", "independent_probe", "discovery_output", "legacy"}
INDEPENDENT_PROVENANCES = {"user_supplied", "official_page", "independent_probe"}


class EvidenceError(ValueError):
    pass


def text(value: Any, field: str, limit: int = 1000) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise EvidenceError(f"{field} must be a string of at most {limit} characters")
    return " ".join(value.split())


def identifier(value: Any, field: str) -> str:
    result = text(value, field, 80)
    if not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", result):
        raise EvidenceError(f"{field} must be a lowercase underscore identifier")
    return result


def posting_url(value: Any, field: str = "url") -> str:
    result = text(value, field, 4096)
    try:
        parsed = urlsplit(result)
    except ValueError as exc:
        raise EvidenceError(f"{field} is not a valid URL") from exc
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise EvidenceError(f"{field} must be an absolute http(s) URL without credentials")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise EvidenceError(f"{field} must use https except for loopback fixtures")
    try:
        port = parsed.port
    except ValueError as exc:
        raise EvidenceError(f"{field} has an invalid port") from exc
    host = parsed.hostname.lower()
    host = f"[{host}]" if ":" in host else host
    if port and (parsed.scheme, port) not in {("https", 443), ("http", 80)}:
        host += f":{port}"
    return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/") or "/", parsed.query, ""))


def identity_url(value: str) -> str:
    """Keep job-defining query parameters; discard only known tracking parameters."""
    if not value:
        return ""
    parsed = urlsplit(value)
    query = sorted((k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                   if not k.lower().startswith("utm_") and k.lower() not in {"gclid", "fbclid"})
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", urlencode(query), ""))


def matches_posting(candidate: dict, evidence: dict) -> bool:
    posting_id = evidence.get("posting_id")
    candidate_id = candidate.get("posting_id") or candidate.get("job_id") or candidate.get("requisition_id")
    if posting_id and candidate_id:
        return str(posting_id) == str(candidate_id)
    if evidence.get("url"):
        wanted = identity_url(evidence["url"])
        return any(identity_url(candidate.get(key) or "") == wanted for key in ("url", "alternate_url"))
    if posting_id:
        return False
    normalize = lambda s: " ".join(str(s or "").casefold().split())
    return bool(evidence.get("title")) and normalize(candidate.get("title")) == normalize(evidence["title"])


def _records(value: Any, limit: int, field: str) -> list[dict]:
    if not isinstance(value, list) or len(value) > limit or any(not isinstance(v, dict) for v in value):
        raise EvidenceError(f"{field} must contain at most {limit} objects")
    return value


def _keys(record: dict, allowed: set[str], required: set[str], field: str) -> None:
    if set(record) - allowed or required - set(record):
        raise EvidenceError(f"{field} has unknown or missing fields")


def _unique(records: list[dict], field: str) -> list[dict]:
    if len({r['id'] for r in records}) != len(records):
        raise EvidenceError(f"{field} has duplicate ids")
    if len(json.dumps(records).encode()) > EVIDENCE_MAX_BYTES:
        raise EvidenceError(f"{field} exceeds evidence size limit")
    return records


def normalize_references(value: Any) -> list[dict]:
    result = []
    for raw in _records(value, MAX_REFERENCES, "reference_jobs"):
        _keys(raw, {"id", "url", "title", "employer", "relevance", "source_id", "association_reason"}, {"id", "url"}, "reference job")
        result.append({"id": identifier(raw["id"], "reference id"), "url": posting_url(raw["url"]),
                       **{k: text(raw.get(k, ""), k) for k in ("title", "employer", "relevance", "association_reason")},
                       "source_id": identifier(raw["source_id"], "source_id") if raw.get("source_id") else None})
    return _unique(result, "reference_jobs")


def normalize_canaries(value: Any) -> list[dict]:
    result = []
    counts: dict[str, int] = {}
    for raw in _records(value, MAX_CANARIES, "canaries"):
        allowed = {"id", "source_id", "reference_job_id", "title", "url", "posting_id", "provenance", "availability",
                   "scope", "checked_on", "expires_on", "evidence_url", "evidence_note"}
        _keys(raw, allowed, {"id", "source_id", "provenance", "availability", "scope"}, "canary")
        record = {k: text(raw.get(k, ""), k, 4096 if k in {"url", "evidence_url"} else 1000)
                  for k in allowed - {"reference_job_id"}}
        for key in ("id", "source_id"):
            record[key] = identifier(record[key], key)
        record["reference_job_id"] = identifier(raw["reference_job_id"], "reference_job_id") if raw.get("reference_job_id") else None
        if not any(record[k] for k in ("url", "posting_id", "title")):
            raise EvidenceError("canary needs a posting identity")
        for key in ("url", "evidence_url"):
            if record[key]:
                record[key] = posting_url(record[key], key)
        for key, allowed_values in (("provenance", PROVENANCES), ("availability", {"live", "expired", "unknown"}),
                                    ("scope", {"in_scope", "out_of_scope", "unknown"})):
            if record[key] not in allowed_values:
                raise EvidenceError(f"invalid canary {key}")
        for key in ("checked_on", "expires_on"):
            if record[key]:
                try:
                    record[key] = date.fromisoformat(record[key]).isoformat()
                except ValueError as exc:
                    raise EvidenceError(f"{key} must be an ISO date") from exc
        if record["availability"] != "unknown":
            if not record["checked_on"] or not record["evidence_url"] or not record["evidence_note"]:
                raise EvidenceError("confirmed availability needs checked_on, evidence_url and evidence_note")
            if not record["expires_on"]:
                record["expires_on"] = (date.fromisoformat(record["checked_on"]) + timedelta(days=14)).isoformat()
        if record["checked_on"] and record["expires_on"] and record["expires_on"] < record["checked_on"]:
            raise EvidenceError("canary review deadline precedes check")
        counts[record['source_id']] = counts.get(record['source_id'], 0) + 1
        if counts[record['source_id']] > MAX_SOURCE_CANARIES:
            raise EvidenceError(f"at most {MAX_SOURCE_CANARIES} canaries per source")
        result.append(record)
    return _unique(result, "canaries")


def canary_json_schema() -> dict:
    fields = ["id", "source_id", "reference_job_id", "title", "url", "posting_id", "provenance", "availability", "scope",
              "checked_on", "expires_on", "evidence_url", "evidence_note"]
    properties = {k: {"type": "string"} for k in fields}
    properties["reference_job_id"] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    for key, values in (("provenance", sorted(PROVENANCES - {"legacy", "discovery_output"})),
                        ("availability", ["live", "expired", "unknown"]), ("scope", ["in_scope", "out_of_scope", "unknown"])):
        if key in properties:
            properties[key] = {"type": "string", "enum": values}
    return {"type": "object", "additionalProperties": False, "required": fields, "properties": properties}


def stored_canaries(integration: dict, source_id: str) -> list[dict]:
    """Read v1 singular evidence conservatively; never rewrite it merely by loading."""
    if "canaries" in integration:
        return normalize_canaries(integration["canaries"])
    old = integration.get("canary") or {"title": integration.get("canary_title", ""), "url": integration.get("canary_url", "")}
    if not isinstance(old, dict) or not (old.get("title") or old.get("url")):
        return []
    return [{"id": "legacy_canary", "source_id": source_id, "reference_job_id": None,
             "title": old.get("title", ""), "url": old.get("url", ""), "posting_id": "", "provenance": "legacy",
             "availability": "unknown", "scope": "unknown" if old.get("review_required") else "in_scope",
             "checked_on": "", "expires_on": old.get("expires_on", ""), "evidence_url": "", "evidence_note": "Legacy evidence requires independent review."}]


def load_references(path: Path, track: str) -> list[dict]:
    if not path.exists():
        return []
    if path.stat().st_size > EVIDENCE_MAX_BYTES:
        raise EvidenceError("reference file exceeds size limit")
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or payload.get("track") != track or set(payload) != {"schema_version", "track", "reference_jobs"}:
        raise EvidenceError("invalid reference file contract")
    return normalize_references(payload["reference_jobs"])


def reference_payload(track: str, references: list[dict]) -> dict:
    payload = {"schema_version": 1, "track": track, "reference_jobs": normalize_references(references)}
    if len((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()) > EVIDENCE_MAX_BYTES:
        raise EvidenceError("reference file exceeds size limit")
    return payload


def merge_references(path: Path, track: str, references: list[dict]) -> None:
    incoming = normalize_references(references)
    with file_lock(path):
        existing = {r['id']: r for r in load_references(path, track)}
        for record in incoming:
            if record['id'] in existing and existing[record['id']] != record:
                raise EvidenceError(f"reference {record['id']} already exists with different content; review explicitly")
            existing[record['id']] = record
        write_json_atomic(path, reference_payload(track, list(existing.values())))


def register_canaries(integration: dict, canaries: list[dict], source_id: str) -> None:
    incoming = normalize_canaries(canaries)
    current = {c['id']: c for c in stored_canaries(integration, source_id)}
    added = False
    for record in incoming:
        if record['source_id'] != source_id:
            raise EvidenceError("canary source does not match registration target")
        old = current.get(record['id'])
        if old and old != record:
            raise EvidenceError(f"canary {record['id']} already exists; use availability review or confirmed-expiration rotation")
        added = added or old is None
        current[record['id']] = record
    integration['canaries'] = normalize_canaries(list(current.values()))
    if added:
        integration['status'] = 'pending'
        integration.pop('last_attempted', None)
        integration['verification'] = 'pending'


def initial_source_state(sources: list[dict], canaries: list[dict]) -> dict:
    state = {}
    for source in sources:
        integration = {"status": "pending", "verification": "unverified"}
        register_canaries(integration, [c for c in canaries if c['source_id'] == source['id']], source['id'])
        state[source['id']] = {"last_checked": None, "integration": integration}
    return state


def canary_id(url: str) -> str:
    return "posting_" + hashlib.sha256(identity_url(url).encode()).hexdigest()[:16]


def check_posting_availability(canary: dict, *, today: str, timeout: int = 15) -> dict:
    """Independently inspect a vacancy. Ambiguous/dynamic/error pages stay unknown."""
    from html.parser import HTMLParser
    from probe_career_source import fetch_http

    url = canary.get('url') or canary.get('evidence_url')
    result = {'availability': 'unknown', 'checked_on': today, 'evidence_url': url or '',
              'evidence_note': 'No independently verifiable vacancy URL.'}
    if not url:
        return result
    try:
        html, final_url, status, hints = fetch_http(url, timeout)
    except (OSError, ValueError, LookupError) as exc:
        result['evidence_note'] = f'Availability check failed: {exc}'[:1000]
        return result
    result['evidence_url'] = final_url or url
    if status in {404, 410}:
        result.update(availability='expired', evidence_note=f'Official vacancy returned HTTP {status}.')
        return result
    if status != 200:
        result['evidence_note'] = '; '.join(hints) or f'HTTP {status}; availability could not be established.'
        return result

    class JsonLD(HTMLParser):
        def __init__(self):
            super().__init__()
            self.active = False
            self.parts = []
            self.blocks = []
        def handle_starttag(self, tag, attrs):
            if tag == 'script':
                self.active = dict(attrs).get('type', '').lower() == 'application/ld+json'
                self.parts = []
        def handle_data(self, data):
            if self.active:
                self.parts.append(data)
        def handle_endtag(self, tag):
            if tag == 'script' and self.active:
                self.blocks.append(''.join(self.parts))
                self.active = False

    parser = JsonLD()
    parser.feed(html)
    postings = []
    def visit(value):
        if isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, dict):
            types = value.get('@type', [])
            if types == 'JobPosting' or isinstance(types, list) and 'JobPosting' in types:
                postings.append(value)
            if '@graph' in value:
                visit(value['@graph'])
    for block in parser.blocks:
        try:
            visit(json.loads(block))
        except (ValueError, RecursionError):
            continue
    for posting in postings:
        raw_id = posting.get('identifier', '')
        posting_id = raw_id.get('value', '') if isinstance(raw_id, dict) else raw_id
        candidate = {'title': posting.get('title', ''), 'url': posting.get('url', ''), 'posting_id': posting_id}
        if not candidate['url'] and len(postings) == 1 and identity_url(final_url) == identity_url(url):
            candidate['url'] = final_url
        if not matches_posting(candidate, canary):
            continue
        valid_through = posting.get('validThrough', '')
        if valid_through:
            try:
                if date.fromisoformat(str(valid_through)[:10]) < date.fromisoformat(today):
                    result.update(availability='expired', evidence_note='Matching official JobPosting has a past validThrough date.')
                    return result
            except ValueError:
                result['evidence_note'] = 'Matching JobPosting has an invalid validThrough date; review manually.'
                return result
        if not posting.get('title') or not posting.get('description'):
            continue
        result.update(availability='live', evidence_note='Matching official JobPosting has title and role detail; no expired validity date.',
                      expires_on=(date.fromisoformat(today) + timedelta(days=14)).isoformat())
        return result
    result['evidence_note'] = 'No matching, current structured JobPosting established; review the official vacancy manually.'
    return result


def effective_canaries(canaries: list[dict], candidates: list[dict], *, today: str, timeout: int = 15) -> list[dict]:
    """Resolve uncertain/stale evidence outside scheduled discovery; preserve stored records."""
    resolved = []
    for record in canaries:
        current = dict(record)
        if record.get('availability') == 'expired' or record.get('scope') == 'out_of_scope':
            resolved.append(current)
            continue
        # A same-day explicit observation is already independent evidence. Older
        # missing postings are rechecked; expiration of a review is not job closure.
        present = any(matches_posting(c, record) for c in candidates)
        stale = not record.get('expires_on') or record['expires_on'] < today or record.get('checked_on', '') > today
        needs_check = record.get('availability') != 'live' or stale or (not present and record.get('checked_on') != today)
        if needs_check:
            observation = check_posting_availability(record, today=today, timeout=timeout)
            current.update(observation)
            current['prior_evidence'] = dict(record)
        resolved.append(current)
    return resolved
