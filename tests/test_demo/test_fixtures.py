"""Tests for demo fixture data integrity and completeness."""

from src.demo.fixtures import (
    CONNECTOR_CONFIGS,
    DECISION_IDS,
    DECISIONS,
    DEMO_ORG_ID,
    DEPLOYS,
    EDGES,
    GOAL_IDS,
    GOALS,
    ORG_MEMBERS,
    PERSON_BY_KEY,
    PERSON_IDS,
    PERSONS,
    PR_IDS,
    PROJECT_IDS,
    PROJECTS,
    PRS,
    TASK_IDS,
    TASKS,
    _id,
)

# ---- Count requirements ----


def test_fixture_counts():
    """Ensure fixtures meet minimum data requirements."""
    assert len(TASKS) >= 50
    assert len(PRS) >= 20
    assert len(DEPLOYS) >= 18
    assert len(PERSONS) >= 12
    assert len(GOALS) >= 14
    assert len(PROJECTS) >= 7
    assert len(DECISIONS) >= 20
    assert len(EDGES) >= 100


# ---- Uniqueness checks ----


def test_no_duplicate_task_ids():
    """Each task key should be unique."""
    keys = [t["key"] for t in TASKS]
    assert len(keys) == len(set(keys))


def test_no_duplicate_person_keys():
    """Each person key should be unique."""
    keys = [p["key"] for p in PERSONS]
    assert len(keys) == len(set(keys))


def test_no_duplicate_pr_keys():
    """Each PR key should be unique."""
    keys = [p["key"] for p in PRS]
    assert len(keys) == len(set(keys))


def test_no_duplicate_deploy_keys():
    """Each deploy key should be unique."""
    keys = [d["key"] for d in DEPLOYS]
    assert len(keys) == len(set(keys))


def test_no_duplicate_goal_keys():
    """Each goal key should be unique."""
    keys = [g["key"] for g in GOALS]
    assert len(keys) == len(set(keys))


def test_no_duplicate_decision_keys():
    """Each decision key should be unique."""
    keys = [d["key"] for d in DECISIONS]
    assert len(keys) == len(set(keys))


def test_no_duplicate_project_keys():
    """Each project key should be unique."""
    keys = [p["key"] for p in PROJECTS]
    assert len(keys) == len(set(keys))


# ---- UUID determinism ----


def test_uuids_are_deterministic():
    """Calling _id with the same name should return the same UUID."""
    id1 = _id("test-entity")
    id2 = _id("test-entity")
    assert id1 == id2


def test_uuids_differ_for_different_names():
    """Different names should produce different UUIDs."""
    id1 = _id("entity-a")
    id2 = _id("entity-b")
    assert id1 != id2


def test_demo_org_id_is_deterministic():
    """DEMO_ORG_ID should be consistent."""
    assert DEMO_ORG_ID == _id("demo-org")


# ---- ID map consistency ----


def test_person_ids_match_persons():
    """PERSON_IDS should have one entry per PERSONS item."""
    assert len(PERSON_IDS) == len(PERSONS)
    for person in PERSONS:
        assert person["key"] in PERSON_IDS


def test_task_ids_match_tasks():
    """TASK_IDS should have one entry per TASKS item."""
    assert len(TASK_IDS) == len(TASKS)
    for task in TASKS:
        assert task["key"] in TASK_IDS


def test_pr_ids_match_prs():
    assert len(PR_IDS) == len(PRS)
    for pr in PRS:
        assert pr["key"] in PR_IDS


def test_goal_ids_match_goals():
    assert len(GOAL_IDS) == len(GOALS)
    for goal in GOALS:
        assert goal["key"] in GOAL_IDS


def test_project_ids_match_projects():
    assert len(PROJECT_IDS) == len(PROJECTS)
    for proj in PROJECTS:
        assert proj["key"] in PROJECT_IDS


def test_decision_ids_match_decisions():
    assert len(DECISION_IDS) == len(DECISIONS)
    for dec in DECISIONS:
        assert dec["key"] in DECISION_IDS


# ---- Data structure validation ----


def test_persons_have_required_fields():
    """Each person should have name, email, role, key."""
    for person in PERSONS:
        assert "key" in person
        assert "name" in person
        assert "email" in person
        assert "role" in person


def test_tasks_have_required_fields():
    """Each task should have key, title, assignee, status, priority."""
    for task in TASKS:
        assert "key" in task
        assert "title" in task
        assert "assignee" in task
        assert "status" in task
        assert "priority" in task


def test_task_assignees_exist():
    """Every task assignee should reference a valid person key."""
    person_keys = {p["key"] for p in PERSONS}
    for task in TASKS:
        assert task["assignee"] in person_keys, (
            f"Task {task['key']} has unknown assignee: {task['assignee']}"
        )


def test_pr_authors_exist():
    """Every PR author should reference a valid person key."""
    person_keys = {p["key"] for p in PERSONS}
    for pr in PRS:
        assert pr["author"] in person_keys, f"PR {pr['key']} has unknown author: {pr['author']}"


def test_goals_have_required_fields():
    """Each goal should have key, title, level, owner, target_value, current_value."""
    for goal in GOALS:
        assert "key" in goal
        assert "title" in goal
        assert "level" in goal
        assert "owner" in goal
        assert "target_value" in goal
        assert "current_value" in goal


def test_goal_parent_references_valid():
    """If a goal has a parent_key, it should reference another goal."""
    goal_keys = {g["key"] for g in GOALS}
    for goal in GOALS:
        if goal.get("parent_key"):
            assert goal["parent_key"] in goal_keys, f"Goal {goal['key']} has invalid parent_key: {goal['parent_key']}"


def test_project_task_references_valid():
    """Project task_keys should reference valid task keys."""
    task_keys = {t["key"] for t in TASKS}
    for proj in PROJECTS:
        for tk in proj["task_keys"]:
            assert tk in task_keys, f"Project {proj['key']} references unknown task: {tk}"


def test_project_goal_references_valid():
    """Project goal_keys should reference valid goal keys."""
    goal_keys = {g["key"] for g in GOALS}
    for proj in PROJECTS:
        for gk in proj["goal_keys"]:
            assert gk in goal_keys, f"Project {proj['key']} references unknown goal: {gk}"


# ---- Edge validation ----


def test_edges_have_required_fields():
    """Each edge should have from_entity_id, to_entity_id, type."""
    for edge in EDGES:
        assert "from_entity_id" in edge
        assert "to_entity_id" in edge
        assert "type" in edge


def test_edges_keys_unique():
    """Edge keys should be unique."""
    keys = [e["key"] for e in EDGES]
    assert len(keys) == len(set(keys))


# ---- Connector configs ----


def test_connector_configs_count():
    """Should have configs for Linear, GitHub, and Slack."""
    assert len(CONNECTOR_CONFIGS) == 3
    connectors = {c["connector"] for c in CONNECTOR_CONFIGS}
    assert "linear" in connectors
    assert "github" in connectors
    assert "slack" in connectors


# ---- Org members ----


def test_org_members_count():
    """Should have enough org members for demo."""
    assert len(ORG_MEMBERS) >= 8


def test_org_member_keys_are_person_keys():
    """Org member keys should reference valid person keys."""
    person_keys = {p["key"] for p in PERSONS}
    for member in ORG_MEMBERS:
        assert member["key"] in person_keys


def test_person_by_key_lookup():
    """PERSON_BY_KEY should allow lookup by key."""
    assert PERSON_BY_KEY["alice"]["name"] == "Alice Chen"
    assert PERSON_BY_KEY["alice"]["email"] == "alice@demo.numen.team"
