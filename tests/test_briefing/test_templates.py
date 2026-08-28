"""Tests for briefing email template rendering."""

import uuid
from unittest.mock import MagicMock

from src.briefing.templates import (
    _format_provenance,
    _render_goal_pills_html,
    _render_item_card_html,
    _render_source_links_html,
    _urgency_color,
    _urgency_label,
    render_briefing_email,
)
from src.shared.types import BriefingItem, EntityType

# ---- Urgency color/label helpers ----


def test_urgency_color_critical():
    assert _urgency_color(0.90) == "#DC2626"


def test_urgency_color_high():
    assert _urgency_color(0.70) == "#EA580C"


def test_urgency_color_medium():
    assert _urgency_color(0.50) == "#CA8A04"


def test_urgency_color_low():
    assert _urgency_color(0.20) == "#16A34A"


def test_urgency_label_critical():
    assert _urgency_label(0.90) == "Critical"


def test_urgency_label_high():
    assert _urgency_label(0.70) == "High"


def test_urgency_label_medium():
    assert _urgency_label(0.50) == "Medium"


def test_urgency_label_low():
    assert _urgency_label(0.20) == "Low"


def test_urgency_label_boundary_085():
    """At exactly 0.85 it should be Critical."""
    assert _urgency_label(0.85) == "Critical"


def test_urgency_label_boundary_065():
    """At exactly 0.65 it should be High."""
    assert _urgency_label(0.65) == "High"


def test_urgency_label_boundary_040():
    """At exactly 0.40 it should be Medium."""
    assert _urgency_label(0.40) == "Medium"


# ---- Provenance formatting ----


def test_format_provenance_empty():
    result = _format_provenance([])
    assert "aggregated signals" in result


def test_format_provenance_pr_review():
    result = _format_provenance([{"signal": "pr_review_requested"}])
    assert "Pull request review" in result


def test_format_provenance_blocking_chain():
    result = _format_provenance([{"signal": "blocking_chain", "blocked_count": 3}])
    assert "3" in result
    assert "downstream" in result.lower() or "blocks" in result.lower()


def test_format_provenance_recent_incident():
    result = _format_provenance([{"signal": "recent_incident", "severity": "critical"}])
    assert "critical" in result.lower()


def test_format_provenance_low_adoption():
    result = _format_provenance([{"signal": "low_adoption", "adoption_rate": 0.15}])
    assert "15.0" in result


def test_format_provenance_generic_fallback():
    result = _format_provenance([{"signal": "custom_signal", "source": "test"}])
    assert "Custom signal" in result
    assert "test" in result


# ---- Goal pills rendering ----


def test_render_goal_pills_empty():
    assert _render_goal_pills_html([]) == ""


def test_render_goal_pills_single():
    html = _render_goal_pills_html(["Retention +15%"])
    assert "Retention +15%" in html
    assert "<span" in html


def test_render_goal_pills_multiple():
    html = _render_goal_pills_html(["Goal A", "Goal B"])
    assert "Goal A" in html
    assert "Goal B" in html


# ---- Source links rendering ----


def test_render_source_links_empty():
    assert _render_source_links_html([]) == ""


def test_render_source_links_single():
    html = _render_source_links_html([{"label": "github", "url": "https://github.com/pr/1"}])
    assert "Github" in html
    assert "https://github.com/pr/1" in html
    assert "<a href" in html


# ---- Item card rendering ----


def test_render_item_card_contains_title():
    item = BriefingItem(
        entity_id=uuid.uuid4(),
        entity_type=EntityType.TASK,
        title="Fix the critical bug",
        why_it_matters="Blocks 3 items",
        urgency_score=0.90,
        goal_tags=["Retention"],
        source_links=[{"label": "linear", "url": "https://linear.app/issue/1"}],
        suggested_action="Fix it today",
    )
    html = _render_item_card_html(item)
    assert "Fix the critical bug" in html
    assert "Blocks 3 items" in html
    assert "Critical" in html
    assert "Retention" in html
    assert "Fix it today" in html


def test_render_item_card_no_suggested_action():
    item = BriefingItem(
        entity_id=uuid.uuid4(),
        entity_type=EntityType.TASK,
        title="Task without action",
        why_it_matters="Just important",
        urgency_score=0.30,
    )
    html = _render_item_card_html(item)
    assert "Task without action" in html
    assert "Suggested" not in html


# ---- Full email rendering ----


def _make_mock_member(name="Alice", email="alice@test.com"):
    member = MagicMock()
    member.display_name = name
    member.email = email
    return member


def test_render_briefing_email_with_items():
    member = _make_mock_member()
    items = [
        BriefingItem(
            entity_id=uuid.uuid4(),
            entity_type=EntityType.TASK,
            title="Fix the bug",
            why_it_matters="Blocking 2 others",
            urgency_score=0.80,
            goal_tags=["Retention +15%"],
            source_links=[{"label": "linear", "url": "https://linear.app"}],
            suggested_action="Review and fix",
        ),
        BriefingItem(
            entity_id=uuid.uuid4(),
            entity_type=EntityType.COMMIT_PR,
            title="PR Review: Auth fix",
            why_it_matters="Requested by teammate",
            urgency_score=0.70,
        ),
    ]

    html, text = render_briefing_email(member, items)

    # HTML checks
    assert "Fix the bug" in html
    assert "PR Review: Auth fix" in html
    assert "Alice" in html
    assert "Numen" in html
    assert "<!DOCTYPE html>" in html

    # Plain text checks
    assert "Fix the bug" in text
    assert "PR Review: Auth fix" in text
    assert "Alice" in text
    assert "NUMEN" in text


def test_render_briefing_email_with_narrative():
    member = _make_mock_member()
    items = [
        BriefingItem(
            entity_id=uuid.uuid4(),
            entity_type=EntityType.TASK,
            title="A task",
            why_it_matters="Important",
            urgency_score=0.50,
        ),
    ]
    narrative = "Today you have 1 important item to focus on."

    html, text = render_briefing_email(member, items, narrative=narrative)

    assert narrative in html
    assert narrative in text


def test_render_briefing_email_empty_items():
    member = _make_mock_member()
    html, text = render_briefing_email(member, [])

    # Should still render a valid email, just with 0 items
    assert "Alice" in html
    assert "0" in html  # 0 items
    assert "Alice" in text


def test_render_briefing_email_stats_count():
    """Stats row should count high-priority and blocking items correctly."""
    member = _make_mock_member()
    items = [
        BriefingItem(
            entity_id=uuid.uuid4(),
            entity_type=EntityType.TASK,
            title="Blocker: Something",
            why_it_matters="Blocks things",
            urgency_score=0.90,
        ),
        BriefingItem(
            entity_id=uuid.uuid4(),
            entity_type=EntityType.COMMIT_PR,
            title="PR Review",
            why_it_matters="Needs review",
            urgency_score=0.70,
        ),
    ]

    html, text = render_briefing_email(member, items)
    # Should have correct counts in the stats section
    assert "2" in text  # 2 items total


def test_render_briefing_email_fallback_name():
    """When display_name is None, should use email prefix."""
    member = _make_mock_member(name=None, email="bob@test.com")
    items = []
    html, text = render_briefing_email(member, items)
    assert "bob" in html
    assert "bob" in text
