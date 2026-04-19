#!/usr/bin/env python3
"""Compatibility entrypoint for modular deterministic source discovery.

Provider implementations live under `discover.sources`. New source support
should be added there and registered through the provider registry.
"""

from __future__ import annotations

from pathlib import Path

from discover.constants import (
    DEFAULT_BROWSER_TIMEOUT_MS,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_BROWSER_PAGES,
    NON_TECHNICAL_TITLE_HINTS,
    SPECIALIZED_SIGNAL_TERMS,
    TECHNICAL_TITLE_HINTS,
)
from discover.core import (
    BrowserEnrichmentResult,
    BrowserPageResult,
    BrowserStrategy,
    Candidate,
    Coverage,
    SourceConfig,
    SourceTermRule,
    attach_source_identity,
    discover_source,
    failed_coverage,
    partial_browser_unavailable_coverage,
)
from discover.helpers import (
    HTML_TAG_RE,
    DataPageCollector,
    LinkCollector,
    extract_json_array_after_marker,
    extract_json_object_after_marker,
    extract_visible_text_lines_from_html,
    extract_visible_text_marker_snippet,
    extract_visible_text_section,
    infer_remote_status,
    join_text,
    looks_like_job_link,
    match_terms,
    match_terms_with_aliases,
    merge_candidate,
    normalize_for_matching,
    normalize_heading_line,
    normalize_url_without_fragment,
    normalize_whitespace,
    should_keep_candidate,
    slugify_title,
    split_visible_lines,
    strip_html_fragment,
    truncate_text,
)
from discover.http import USER_AGENT, fetch_json, fetch_text, post_json
from discover.registry import load_registry
from discover.runner import (
    build_parser,
    coverage_to_dict,
    emit_progress,
    generated_at,
    normalize_terms,
    source_due_today,
    source_to_dict,
    write_output_text,
)
from discover.sources.ashby import ASHBY_JOB_BOARD_QUERY, discover_ashby_api
from discover.sources.bundeswehr import (
    BUNDESWEHR_COMPENSATION_HEADINGS,
    BUNDESWEHR_COMPENSATION_MARKERS,
    BUNDESWEHR_DETAIL_STOP_HEADINGS,
    BUNDESWEHR_JOB_TITLE_RE,
    BUNDESWEHR_JOBSUCHE_URL,
    BUNDESWEHR_ODATA_DETAIL_SELECT,
    BUNDESWEHR_ODATA_ENTITY_SET,
    BUNDESWEHR_ODATA_LANGUAGE,
    BUNDESWEHR_ODATA_LIST_SELECT,
    BUNDESWEHR_ODATA_OPPORTUNITY_CATEGORIES,
    BUNDESWEHR_ODATA_PAGE_SIZE,
    BUNDESWEHR_ODATA_SERVICE_ROOT,
    BUNDESWEHR_QUALIFICATION_HEADINGS,
    BUNDESWEHR_TASK_HEADINGS,
    apply_bundeswehr_detail_text,
    apply_bundeswehr_odata_detail,
    build_bundeswehr_odata_candidate,
    build_bundeswehr_odata_candidate_notes,
    build_bundeswehr_odata_candidate_url,
    build_bundeswehr_portal_candidate_url,
    bundeswehr_odata_category_filter_clause,
    bundeswehr_odata_detail_key,
    bundeswehr_odata_filter_for_category,
    bundeswehr_odata_filter_for_keyword,
    bundeswehr_odata_searchable_text,
    candidate_searchable_text,
    clean_bundeswehr_odata_value,
    discover_bundeswehr_jobsuche,
    discover_bundeswehr_odata,
    discover_bundeswehr_profile_catalog_fallback,
    extract_bundeswehr_detail_sections,
)
from discover.sources.browser import (
    BROWSER_STRATEGIES,
    GOOGLE_LOCATION_FILTERS,
    GOOGLE_RESULTS_PAGE_SIZE,
    META_DETAIL_IGNORED_LINES,
    META_DETAIL_STOP_HEADINGS,
    META_MINIMUM_QUALIFICATION_HEADINGS,
    META_PREFERRED_QUALIFICATION_HEADINGS,
    META_TASK_HEADINGS,
    accept_bosch_cookies,
    accept_thales_cookies,
    advance_asml_results,
    advance_bosch_results,
    advance_meta_results,
    apply_meta_detail_text,
    bosch_search_url,
    dismiss_onetrust_banner,
    discover_asml_browser,
    discover_automattic_browser,
    discover_browser,
    discover_coinbase_browser,
    discover_helsing_browser,
    discover_thales_browser,
    discover_trailofbits_browser,
    enrich_meta_candidates,
    extract_asml_jobs,
    extract_bosch_jobs,
    extract_google_jobs,
    extract_helsing_jobs,
    extract_meta_detail_sections,
    extract_meta_jobs,
    google_degree_filters,
    google_filter_note,
    google_location_filters,
    google_public_job_url,
    google_search_url,
    load_sync_playwright,
    meta_search_url,
    normalize_google_degree_filter,
    playwright_browsers_missing_coverage,
    playwright_import_missing_coverage,
)
from discover.sources.eightfold import (
    EIGHTFOLD_DOMAINS_BY_HOST,
    EIGHTFOLD_MAX_PAGES,
    INFINEON_RESULTS_PAGE_SIZE,
    discover_eightfold_api,
    discover_infineon_api,
    eightfold_domain_for_source,
)
from discover.sources.enbw import (
    ENBW_RESULTS_PAGE_SIZE,
    build_enbw_apply_url,
    build_enbw_job_url,
    build_enbw_search_url,
    discover_enbw_phenom,
)
from discover.sources.generic_html import (
    collect_job_links,
    discover_cybernetica_teamdash,
    discover_filtered_html_links,
    discover_html,
    discover_secunet_jobboard,
    is_same_page_link,
    looks_like_non_job_link,
)
from discover.sources.getro import (
    GETRO_RESULTS_PAGE_SIZE,
    MAX_GETRO_PAGES,
    NEXT_DATA_SCRIPT_RE,
    discover_getro_api,
    extract_next_data_payload,
)
from discover.sources.greenhouse import discover_greenhouse_api, greenhouse_board_token
from discover.sources.hackernews import (
    HN_JOB_ROW_RE,
    HN_MORE_LINK_RE,
    HN_WHOISHIRING_TITLE_RE,
    discover_hackernews_jobs,
    discover_hackernews_whoishiring_api,
    extract_first_external_url_from_html,
    infer_hn_employer,
    infer_hn_whoishiring_fields,
)
from discover.sources.iacr import (
    IACR_CONTACT_RE,
    IACR_DESCRIPTION_RE,
    IACR_PLACE_RE,
    IACR_POSTED_RE,
    IACR_POSTING_BLOCK_RE,
    IACR_UPDATED_RE,
    discover_iacr_jobs,
    split_iacr_place,
)
from discover.sources.ibm import (
    IBM_RESEARCH_GENERIC_MATCH_TERMS,
    IBM_RESULTS_PAGE_SIZE,
    IBM_SEARCH_API_URL,
    build_ibm_search_payload,
    build_ibm_title_query,
    discover_ibm_api,
    should_keep_ibm_candidate,
)
from discover.sources.lever import discover_lever_json, lever_api_url
from discover.sources.personio import (
    PERSONIO_NEXT_F_CHUNK_RE,
    discover_personio_page,
    extract_personio_jobs_from_html,
)
from discover.sources.public_service import (
    AUSWAERTIGES_AMT_ACTION_RE,
    BND_BUBBLE_RE,
    BND_RESULT_RE,
    VERFASSUNGSSCHUTZ_RSS_URL,
    build_bnd_search_url,
    discover_auswaertiges_amt_json,
    discover_bnd_career_search,
    discover_bosch_autocomplete,
    discover_verfassungsschutz_rss,
    extract_verfassungsschutz_section,
    extract_verfassungsschutz_value,
    fetch_verfassungsschutz_job_details,
)
from discover.sources.recruitee import (
    RECRUITEE_DATA_PROPS_RE,
    discover_recruitee_inline,
    extract_recruitee_app_config,
)
from discover.sources.rheinmetall import (
    MAX_RHEINMETALL_PAGES,
    RHEINMETALL_CARD_META_RE,
    RHEINMETALL_CARD_START_RE,
    RHEINMETALL_CARD_TITLE_RE,
    RHEINMETALL_CARD_URL_RE,
    RHEINMETALL_PAGE_NUMBER_RE,
    build_rheinmetall_page_url,
    discover_rheinmetall_html,
)
from discover.sources.service_bund import (
    SERVICE_BUND_DIRECT_LINK_RE,
    SERVICE_BUND_NEXT_RE,
    SERVICE_BUND_PUBLIC_INTEREST_HINTS,
    SERVICE_BUND_RESULT_RE,
    build_service_bund_search_url,
    discover_service_bund_links,
    discover_service_bund_search,
    should_keep_service_bund_candidate,
)
from discover.sources.static_pages import (
    PCD_TEAM_DETAIL_STOP_HEADINGS,
    PCD_TEAM_QUALIFICATION_HEADINGS,
    PCD_TEAM_TASK_HEADINGS,
    apply_pcd_team_detail_text,
    discover_leastauthority_careers,
    discover_neclab_jobs,
    discover_partisia_site,
    discover_pcd_team,
    discover_qedit_inline,
    discover_qusecure_careers,
    extract_pcd_team_detail_sections,
)
from discover.sources.thales import (
    THALES_PAYLOAD_TERM_ALIASES,
    THALES_RESULTS_PAGE_SIZE,
    discover_thales_html,
)
from discover.sources.workable import build_workable_job_url, discover_workable_api
from discover.sources.workday import WORKDAY_RESULTS_PAGE_SIZE, build_workday_job_url, discover_workday_api
from discover.sources.yc import discover_yc_jobs_board, extract_yc_jobs_payload
from discover.track_filters import filter_coverage_for_track, load_track_match_rules
from sap_odata import (
    build_sap_odata_list_url,
    fetch_sap_odata_all,
    fetch_sap_odata_entity,
    sap_odata_string_literal,
)
from source_config import SourceConfigError


ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_HANDLERS = {mode: adapter.discover for mode, adapter in load_registry().items()}


def load_track_config(track: str) -> tuple[list[SourceConfig], list[str], dict[str, SourceTermRule]]:
    from discover.runner import load_track_config as runner_load_track_config

    return runner_load_track_config(track, ROOT)


def main() -> int:
    from discover.runner import main as runner_main

    return runner_main(
        load_track_config_func=load_track_config,
        discover_source_func=discover_source,
        filter_coverage_func=filter_coverage_for_track,
    )


if __name__ == "__main__":
    raise SystemExit(main())
