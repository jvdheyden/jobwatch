# Structured Digest Schema

Daily digests are now written in JSON first and rendered to markdown second.

Source of truth path:
- `artifacts/digests/<track>/YYYY-MM-DD.json`

Render command:
- `python3 ../../scripts/render_digest.py --track <track> --date YYYY-MM-DD`

## Top-level shape

```json
{
  "schema_version": 1,
  "track": "core_crypto",
  "date": "2026-03-29",
  "runs": [
    {
      "kind": "initial",
      "generated_at": "2026-03-29T08:04:21+01:00"
    }
  ]
}
```

`runs` must be a non-empty array. The first run must have `kind: "initial"`.

## Run shape

Each run must be an object.

Required fields:

- `kind`: `initial` or `update`
- `generated_at`: ISO-like timestamp string

Optional fields:

- `executive_summary`: short paragraph
- `recommended_actions`: array of bullet strings
- `top_matches`: array of fully scored, detailed roles
- `other_new_roles`: array of scored, shorter roles
- `filtered_roles`: array of explicitly filtered roles
- `source_notes`: array of source coverage notes
- `notes_for_next_run`: array of bullet strings
- `discovery_artifacts`: array of artifact paths used for the run

If an optional array is omitted, the renderer treats it as an empty array. If
`executive_summary` is omitted or null, the renderer treats it as an empty
string. For readability, prefer writing all run arrays explicitly, even when
they are empty.

Same-day reruns append another run object with `kind: "update"`.

## `top_matches[]`

Required fields:

- `company`
- `title`
- `listing_url`
- `recommendation`: `apply_now`, `watch`, or `skip`

Optional fields:

- `job_key`
- `alternate_url`
- `location`
- `remote`
- `team_or_domain`
- `posted_date`
- `updated_date`
- `source`
- `source_url`
- `fit_score`: number or null; omitted/null renders as `unknown`
- `why_match`: array of short bullets; omitted renders as an empty array
- `concerns`

For useful digests, include `fit_score` and `why_match` whenever the role is
reportable. Use null only when the score is genuinely unknown.

## `other_new_roles[]`

Required fields:

- `company`
- `title`
- `listing_url`
- `recommendation`: `apply_now`, `watch`, or `skip`
- `short_note`

Optional fields:

- `job_key`
- `alternate_url`
- `location`
- `source`
- `fit_score`: number or null; omitted/null renders as `unknown`

For useful digests, include `fit_score` whenever the role is reportable. Use
null only when the score is genuinely unknown.

## `filtered_roles[]`

Required fields:

- `company`
- `title`
- `reason_filtered_out`

Optional fields:

- `listing_url`

## `source_notes[]`

Required fields:

- `source`
- `discovery_mode`
- `status`: `complete`, `partial`, or `failed`

Optional fields:

- `listing_pages_scanned`: string, number, or null
- `search_terms_tried`: array of strings; omitted renders as an empty array
- `result_pages_summary`: string, number, or null
- `direct_job_pages_opened`: string, number, or null
- `limitations`: array of strings; omitted renders as an empty array
- `note`

Use `null` or omit optional string/scalar fields when unknown. Do not use empty
strings for optional values.

## Minimal example

```json
{
  "schema_version": 1,
  "track": "core_crypto",
  "date": "2026-03-29",
  "runs": [
    {
      "kind": "initial",
      "generated_at": "2026-03-29T08:04:21+01:00",
      "executive_summary": "One strong new role cleared the bar today.",
      "recommended_actions": [
        "Review LayerZero Labs soon."
      ],
      "top_matches": [
        {
          "company": "LayerZero Labs",
          "title": "Cryptographer",
          "listing_url": "https://www.iacr.org/jobs/item/4189",
          "location": "Vancouver, BC Canada",
          "source": "IACR Jobs",
          "fit_score": 9,
          "recommendation": "apply_now",
          "why_match": [
            "Exact applied-cryptography fit.",
            "Strong zero-knowledge systems emphasis."
          ],
          "concerns": [
            "Appears Vancouver-based rather than clearly remote."
          ]
        }
      ],
      "other_new_roles": [],
      "filtered_roles": [],
      "source_notes": [],
      "notes_for_next_run": [
        "Keep Coinbase due until coverage is complete."
      ],
      "discovery_artifacts": [
        "artifacts/discovery/core_crypto/2026-03-29.json"
      ]
    }
  ]
}
```
