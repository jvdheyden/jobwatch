from __future__ import annotations

from discover import http
from discover.core import SourceConfig
from discover.sources import generic_html

LISTING_HTML = """
<html><body>
  <a href="/job_posting/senior-product-manager-312036">Apply now</a>
  <a href="/job_posting/full-stack-developer-senior-292895">Apply now</a>
  <a href="/values">Values</a>
</body></html>
"""

# Mirrors the real Factorial page shape: GTM/Sentry <script> and theme <style>
# blocks inlined as text nodes, then the breadcrumb and JD body rendered as
# separate block-level lines.
DETAIL_HTML = """
<html><head>
  <script>(function(w,d,s,l,i){w[l]=w[l]||[];})(window,document,'script','dataLayer','GTM-X');</script>
  <style>@font-face { font-family: 'Poppins'; } .bg-themed-500 { background-color: #111; }</style>
</head><body>
  <div>Senior Product Manager (German-speaking)</div>
  <div>Values</div><div>Benefits</div><div>Jobs</div><div>Offices</div>
  <div>Jobs</div><div>&gt;</div><div>Senior Product Manager (German-speaking)</div>
  <h1>Senior Product Manager (German-speaking)</h1>
  <div>Permanent</div><div>Full time</div><div>Hybrid</div>
  <div>(Munich, Barcelona, Spain)</div>
  <div>Product Management</div>
  <div>THE ROLE:</div>
  <div>Own the product end-to-end and drive delivery from first brief to final release.</div>
  <div>WHAT WE'RE LOOKING FOR:</div>
  <div>2-4 years in product management, ideally in a digital agency or consultancy context.</div>
  <a href="/apply">Apply now</a>
  <div>Privacy policy</div>
  <div>FACTORIAL uses cookies to personalise content and ads.</div>
</body></html>
"""

# Second posting from the same listing. The listing exposes anonymous "Apply
# now" links for every role, so the provider opens each job page it enumerates,
# not just the term-matching one.
DEV_DETAIL_HTML = """
<html><head>
  <script>(function(w,d,s,l,i){w[l]=w[l]||[];})(window,document,'script','dataLayer','GTM-X');</script>
  <style>@font-face { font-family: 'Poppins'; }</style>
</head><body>
  <div>Jobs</div><div>&gt;</div><div>Senior Full-Stack Developer</div>
  <h1>Senior Full-Stack Developer</h1>
  <div>Permanent</div><div>Full time</div><div>Remote</div>
  <div>(Munich, Germany)</div>
  <div>Engineering</div>
  <div>THE ROLE:</div>
  <div>Build and ship customer-facing web applications across the stack.</div>
  <div>WHAT WE'RE LOOKING FOR:</div>
  <div>5+ years building production web services with TypeScript and Node.</div>
  <a href="/apply">Apply now</a>
  <div>Privacy policy</div>
</body></html>
"""


def _source() -> SourceConfig:
    return SourceConfig(
        source="MVST",
        url="https://mvst.factorialhr.com/",
        discovery_mode="factorial",
        last_checked=None,
        cadence_group="every_run",
        source_id="mvst",
    )


def test_factorial_provider_recovers_title_location_and_detail(monkeypatch):
    detail_url = "https://mvst.factorialhr.com/job_posting/senior-product-manager-312036"
    dev_detail_url = "https://mvst.factorialhr.com/job_posting/full-stack-developer-senior-292895"
    pages = {
        "https://mvst.factorialhr.com/": LISTING_HTML,
        detail_url: DETAIL_HTML,
        dev_detail_url: DEV_DETAIL_HTML,
    }

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        return pages[generic_html.helpers.normalize_url_without_fragment(url)]

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)

    coverage = generic_html.discover_factorial(_source(), ["product manager"], timeout_seconds=5)

    candidate = next(c for c in coverage.candidates if c.url == detail_url)
    # Real title replaces the anonymous "Apply now" listing text.
    assert candidate.title == "Senior Product Manager (German-speaking)"
    assert candidate.location == "Munich, Barcelona, Spain"
    # Terms are recomputed against the enriched title/location/detail, not the
    # anonymous listing text the initial HTML pass saw.
    assert candidate.matched_terms == ["product manager"]
    assert dev_detail_url not in {item.url for item in coverage.candidates}
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    # Substantive role detail lands in notes (what the detail_depth validator reads).
    assert "Own the product end-to-end" in candidate.notes
    assert "2-4 years in product management" in candidate.notes
    # Script/style noise never leaks into the extracted copy.
    assert "GTM" not in candidate.notes
    assert "font-face" not in candidate.notes
    assert "@font-face" not in candidate.description
    assert "GTM-X" not in candidate.description
    assert coverage.direct_job_pages_opened == 2


def test_factorial_detail_lines_strip_script_and_style():
    lines = generic_html.factorial_detail_lines(DETAIL_HTML)
    joined = " ".join(lines)
    assert "GTM" not in joined
    assert "font-face" not in joined
    assert "Senior Product Manager (German-speaking)" in joined
