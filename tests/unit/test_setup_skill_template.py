from __future__ import annotations

from pathlib import Path


def test_setup_skill_uses_generic_tracked_agents_template(repo_root: Path) -> None:
    skill_text = (repo_root / ".agents" / "skills" / "set-up" / "SKILL.md").read_text()
    template_path = repo_root / "shared" / "templates" / "track_AGENTS.md"
    template_text = template_path.read_text()

    assert "tracks/core_crypto/AGENTS.md" not in skill_text
    assert "Use `shared/templates/track_AGENTS.md` as the base template." in skill_text
    assert "tracks/{track_slug}/CLAUDE.md" in skill_text
    assert "contains exactly `@AGENTS.md`" in skill_text
    assert template_path.exists()
    assert "../../profile/cv.md" in template_text
    assert "../../cv.md" not in template_text
    assert "Use the project skill `find-jobs`." in template_text
    assert "Use the project skill `rank-jobs`." in template_text

    for placeholder in ("{track_display_name}", "{track_slug}", "{user_name}", "{fit_language}"):
        assert placeholder in template_text

    for forbidden in ("core_crypto", "applied cryptography"):
        assert forbidden not in skill_text
        assert forbidden not in template_text


def test_setup_agents_template_keeps_production_workflow_contract(repo_root: Path) -> None:
    template_text = (
        repo_root / "shared" / "templates" / "track_AGENTS.md"
    ).read_text()

    required_fragments = [
        "../../artifacts/discovery/{track_slug}/YYYY-MM-DD.json",
        "../../artifacts/digests/{track_slug}/YYYY-MM-DD.json",
        "./sources.json",
        "./source_state.json",
        "markdown rendering, ranked-overview rebuilds, and seen-jobs updates to the runner",
        "Same-Day Reruns",
        "Do not report roles already listed in `./seen_jobs.json`.",
        "Do not manually update source state.",
        "Do not manually update `./seen_jobs.json`.",
    ]

    for fragment in required_fragments:
        assert fragment in template_text

    assert "last_checked` column in `./sources.md`" not in template_text


def test_setup_profile_templates_are_tracked_defaults(repo_root: Path) -> None:
    cv_template = repo_root / ".agents" / "skills" / "set-up" / "templates" / "profile" / "cv.md"
    prefs_template = (
        repo_root / ".agents" / "skills" / "set-up" / "templates" / "profile" / "prefs_global.md"
    )
    gitignore_text = (repo_root / ".gitignore").read_text()

    assert "/profile/" in gitignore_text
    assert cv_template.exists()
    assert prefs_template.exists()
    assert "JOB_AGENT_PROFILE_TEMPLATE: cv.md" in cv_template.read_text()
    assert "JOB_AGENT_PROFILE_TEMPLATE: prefs_global.md" in prefs_template.read_text()


def test_source_discovery_uses_local_profile_cv_path(repo_root: Path) -> None:
    discovery_text = (repo_root / ".agents" / "skills" / "discover-sources" / "SKILL.md").read_text()

    assert "`profile/cv.md`" in discovery_text
    assert "`cv.md`" not in discovery_text


def test_setup_step5_templates_live_under_shared_templates(repo_root: Path) -> None:
    shared_templates = repo_root / "shared" / "templates"
    skill_text = (repo_root / ".agents" / "skills" / "set-up" / "SKILL.md").read_text()

    expected = [
        "track_prefs.md",
        "track_sources.json",
        "track_match_rules.json",
        "track_source_state.json",
        "track_AGENTS.md",
    ]
    for name in expected:
        path = shared_templates / name
        assert path.exists(), f"missing shared template: {name}"
        assert f"shared/templates/{name}" in skill_text

    legacy_track_agents = (
        repo_root / ".agents" / "skills" / "set-up" / "templates" / "track_AGENTS.md"
    )
    assert not legacy_track_agents.exists()


def test_setup_skill_ends_with_first_digest_preview_step(repo_root: Path) -> None:
    skill_text = (repo_root / ".agents" / "skills" / "set-up" / "SKILL.md").read_text()

    assert "### 6. First local digest preview" in skill_text
    assert "bash scripts/run_track.sh --track {track_slug}" in skill_text
    assert "tracks/{track_slug}/digests/YYYY-MM-DD.md" in skill_text
    assert "artifacts/digests/{track_slug}/YYYY-MM-DD.json" in skill_text
    assert "### 7. Delivery preferences and local config handholding" in skill_text
    assert "### 8. Validation" in skill_text
    assert "### 9. Final response" in skill_text


def test_start_setup_agent_prompt_requires_digest_preview(repo_root: Path) -> None:
    prompt_text = (repo_root / "scripts" / "start_setup_agent.sh").read_text()

    assert "bash scripts/run_track.sh --track <track>" in prompt_text
    assert "preview" in prompt_text.lower()
    assert "tracks/<track>/digests/YYYY-MM-DD.md" in prompt_text
