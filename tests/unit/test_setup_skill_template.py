from __future__ import annotations

from pathlib import Path


def test_setup_skill_uses_generic_tracked_agents_template(repo_root: Path) -> None:
    skill_text = (repo_root / ".agents" / "skills" / "set-up" / "SKILL.md").read_text()
    template_path = repo_root / ".agents" / "skills" / "set-up" / "templates" / "track_AGENTS.md"
    template_text = template_path.read_text()

    assert "tracks/core_crypto/AGENTS.md" not in skill_text
    assert "Use `.agents/skills/set-up/templates/track_AGENTS.md` as the base template." in skill_text
    assert template_path.exists()

    for placeholder in ("{track_display_name}", "{track_slug}", "{user_name}", "{fit_language}"):
        assert placeholder in template_text

    for forbidden in ("core_crypto", "applied cryptography"):
        assert forbidden not in skill_text
        assert forbidden not in template_text


def test_setup_agents_template_keeps_production_workflow_contract(repo_root: Path) -> None:
    template_text = (
        repo_root / ".agents" / "skills" / "set-up" / "templates" / "track_AGENTS.md"
    ).read_text()

    required_fragments = [
        "../../artifacts/discovery/{track_slug}/YYYY-MM-DD.json",
        "../../artifacts/digests/{track_slug}/YYYY-MM-DD.json",
        "../../shared/ranked_jobs/{track_slug}.json",
        "../../scripts/render_digest.py --track {track_slug} --date YYYY-MM-DD",
        "../../scripts/update_ranked_overview.py --track {track_slug}",
        "Same-Day Reruns",
        "Do not report roles already listed in `../../shared/seen_jobs.md`.",
    ]

    for fragment in required_fragments:
        assert fragment in template_text
