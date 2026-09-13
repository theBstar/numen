"""Experiment 5 question set - product knowledge, one hop to four, plus a conflict.

Same shape as the hop ladder, asked of the product wiki instead of the work
graph. Rung 1 is a document lookup that search handles. Rung 4 walks
document -> feature -> tickets -> projects -> initiatives.

The last question is different in kind: two documents specify the same thing
and disagree. Neither arm is handed the answer - the wiki arm can see the two
documents belong to one feature, which is a hint about where to look, not a
verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from benchmarks import questions as q
from benchmarks.identities import BY_KEY
from benchmarks.wiki_fixtures import DOC_BY_ID, FEATURE_BY_SLUG


def _linear(person: str) -> str:
    return BY_KEY[person].linear.handle


def _people_for(slug: str) -> list[str]:
    return sorted(_linear(p) for p in FEATURE_BY_SLUG[slug]["implementation"]["people"])


def _initiatives_for(slug: str) -> list[str]:
    inits = set()
    for key in FEATURE_BY_SLUG[slug]["implementation"]["tasks"]:
        for p in q.PROJECTS:
            if any(n["identifier"] == key for n in p["issues"]["nodes"]):
                inits.update(n["id"] for n in p["initiatives"]["nodes"])
    return sorted(inits)


@dataclass
class WikiQ:
    qid: str
    hops: int
    text: str
    why: str
    expected_ids: list[str]
    distractor_ids: list[str] = field(default_factory=list)


W1 = WikiQ(
    qid="W1-which-doc",
    hops=1,
    text=("Which product document specifies the fix for Safari sign-in failures? "
          "Return the document id."),
    why="A search hit. A wiki layer should add nothing.",
    expected_ids=["PRD-001"],
    distractor_ids=["PRD-003", "PRD-005"],
)

W2 = WikiQ(
    qid="W2-doc-author",
    hops=2,
    text=("Who wrote the product document about resolving people across GitHub, Linear "
          "and Slack? Return their Linear user id."),
    why="Find the document, then map its author onto a Linear identity.",
    expected_ids=[_linear("eve")],
    distractor_ids=[_linear("grace"), _linear("frank")],
)

W3 = WikiQ(
    qid="W3-who-is-building-it",
    hops=3,
    text=("Who is implementing the feature specified in PRD-004? "
          "Return the Linear user ids."),
    why=("document -> feature -> tickets -> assignees. The document names no "
         "implementers; tickets carry a spec link back to it."),
    expected_ids=_people_for("daily-briefing"),
    distractor_ids=[_linear("eve")],
)

W4 = WikiQ(
    qid="W4-doc-to-initiative",
    hops=4,
    text=("Which company initiatives does the work specified in PRD-002 serve? "
          "Return only the initiative ids."),
    why="document -> feature -> tickets -> projects -> initiatives.",
    expected_ids=_initiatives_for("connector-rate-limiting"),
    distractor_ids=["goal-enterprise", "goal-integrations"],
)

W5 = WikiQ(
    qid="W5-contradiction",
    hops=2,
    text=("Two product documents give different retry policies for the same system. "
          "Return both document ids."),
    why=("Both arms must read and compare. The wiki arm can see the two documents "
         "describe one feature; the document arm has to find them by search."),
    expected_ids=["PRD-002", "PRD-006"],
    distractor_ids=["PRD-005", "PRD-003"],
)

WIKI_LADDER: tuple[WikiQ, ...] = (W1, W2, W3, W4, W5)

_ = DOC_BY_ID
