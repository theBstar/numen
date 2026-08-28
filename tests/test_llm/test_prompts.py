"""Tests for Claude prompt templates."""

from src.llm.prompts import (
    _DIFF_TRUNCATION_LIMIT,
    build_briefing_narrative_prompt,
    build_bug_trace_prompt,
    build_pr_summary_prompt,
)

# ---- build_pr_summary_prompt ----


def test_pr_summary_returns_tuple():
    """Should return a (system, user) prompt tuple."""
    system, user = build_pr_summary_prompt(
        pr_title="Fix auth",
        pr_description="Fixes the login redirect",
        diff_text="diff --git a/auth.py",
        linked_tasks=[],
    )
    assert isinstance(system, str)
    assert isinstance(user, str)


def test_pr_summary_includes_title():
    system, user = build_pr_summary_prompt(
        pr_title="Implement PKCE flow",
        pr_description="Adds PKCE support for OAuth",
        diff_text="some diff",
        linked_tasks=[],
    )
    assert "Implement PKCE flow" in user


def test_pr_summary_includes_diff():
    system, user = build_pr_summary_prompt(
        pr_title="Title",
        pr_description="Desc",
        diff_text="diff --git a/main.py\n+new_function()",
        linked_tasks=[],
    )
    assert "diff --git a/main.py" in user
    assert "+new_function()" in user


def test_pr_summary_includes_description():
    system, user = build_pr_summary_prompt(
        pr_title="Title",
        pr_description="This fixes the critical auth bug",
        diff_text="diff",
        linked_tasks=[],
    )
    assert "This fixes the critical auth bug" in user


def test_pr_summary_empty_description():
    system, user = build_pr_summary_prompt(
        pr_title="Title",
        pr_description="",
        diff_text="diff",
        linked_tasks=[],
    )
    assert "No description provided" in user


def test_pr_summary_includes_linked_tasks():
    tasks = [
        {"title": "ENG-4501: Fix bug", "goal_tags": ["Retention"]},
        {"title": "ENG-4502: Another fix", "goal_tags": []},
    ]
    system, user = build_pr_summary_prompt(
        pr_title="Title",
        pr_description="Desc",
        diff_text="diff",
        linked_tasks=tasks,
    )
    assert "ENG-4501" in user
    assert "Retention" in user
    assert "ENG-4502" in user


def test_pr_summary_no_linked_tasks():
    system, user = build_pr_summary_prompt(
        pr_title="Title",
        pr_description="Desc",
        diff_text="diff",
        linked_tasks=[],
    )
    assert "No linked tasks" in user


def test_pr_summary_truncates_long_diff():
    long_diff = "x" * (_DIFF_TRUNCATION_LIMIT + 1000)
    system, user = build_pr_summary_prompt(
        pr_title="Title",
        pr_description="Desc",
        diff_text=long_diff,
        linked_tasks=[],
    )
    assert "[diff truncated]" in user
    # The truncated diff should be at most _DIFF_TRUNCATION_LIMIT + the truncation message
    diff_section = user.split("```")[1]  # Extract between code fences
    assert len(diff_section) < _DIFF_TRUNCATION_LIMIT + 100


def test_pr_summary_includes_file_history():
    system, user = build_pr_summary_prompt(
        pr_title="Title",
        pr_description="Desc",
        diff_text="diff",
        linked_tasks=[],
        file_history=[{"file": "auth.py", "commits": 5}],
    )
    assert "file history" in user.lower()
    assert "auth.py" in user


def test_pr_summary_system_prompt_content():
    system, user = build_pr_summary_prompt(
        pr_title="Title",
        pr_description="Desc",
        diff_text="diff",
        linked_tasks=[],
    )
    assert "Numen" in system
    assert "summarize" in system.lower() or "Summarize" in system


# ---- build_briefing_narrative_prompt ----


def test_briefing_narrative_returns_tuple():
    system, user = build_briefing_narrative_prompt(
        items=[],
        role="engineer",
        person_name="Alice",
    )
    assert isinstance(system, str)
    assert isinstance(user, str)


def test_briefing_narrative_includes_person_name():
    system, user = build_briefing_narrative_prompt(
        items=[{"title": "Fix bug", "urgency_score": 0.8, "why_it_matters": "Blocks things"}],
        role="engineer",
        person_name="Alice Chen",
    )
    assert "Alice Chen" in system
    assert "Alice Chen" in user


def test_briefing_narrative_includes_role():
    system, user = build_briefing_narrative_prompt(
        items=[],
        role="pm",
        person_name="Eve",
    )
    assert "pm" in system


def test_briefing_narrative_includes_items():
    items = [
        {"title": "ENG-4501: Fix auth", "urgency_score": 0.9, "why_it_matters": "Critical"},
        {"title": "PR Review: Rate limiter", "urgency_score": 0.7, "why_it_matters": "Requested"},
    ]
    system, user = build_briefing_narrative_prompt(
        items=items,
        role="engineer",
        person_name="Alice",
    )
    assert "ENG-4501" in user
    assert "PR Review" in user


def test_briefing_narrative_empty_items():
    system, user = build_briefing_narrative_prompt(
        items=[],
        role="engineer",
        person_name="Bob",
    )
    assert "No items today" in user


# ---- build_bug_trace_prompt ----


def test_bug_trace_returns_tuple():
    system, user = build_bug_trace_prompt(
        error_info={"message": "NullPointerException", "stack": "at main.py:42"},
        deploy_info=None,
        related_files=[],
    )
    assert isinstance(system, str)
    assert isinstance(user, str)


def test_bug_trace_includes_error_info():
    system, user = build_bug_trace_prompt(
        error_info={"message": "ConnectionRefused", "service": "auth-svc"},
        deploy_info=None,
        related_files=[],
    )
    assert "ConnectionRefused" in user


def test_bug_trace_includes_deploy_info():
    system, user = build_bug_trace_prompt(
        error_info={"message": "error"},
        deploy_info={"sha": "abc123", "environment": "production"},
        related_files=[],
    )
    assert "abc123" in user
    assert "production" in user


def test_bug_trace_no_deploy_info():
    system, user = build_bug_trace_prompt(
        error_info={"message": "error"},
        deploy_info=None,
        related_files=[],
    )
    assert "No recent deploy" in user


def test_bug_trace_includes_related_files():
    system, user = build_bug_trace_prompt(
        error_info={"message": "error"},
        deploy_info=None,
        related_files=["src/auth.py", "src/config.py"],
    )
    assert "src/auth.py" in user
    assert "src/config.py" in user


def test_bug_trace_no_related_files():
    system, user = build_bug_trace_prompt(
        error_info={"message": "error"},
        deploy_info=None,
        related_files=[],
    )
    assert "No related files" in user


def test_bug_trace_system_prompt_content():
    system, user = build_bug_trace_prompt(
        error_info={"message": "error"},
        deploy_info=None,
        related_files=[],
    )
    assert "root-cause" in system.lower() or "root cause" in system.lower()
    assert "Numen" in system
