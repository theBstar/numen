"""Structured provenance models for recommendation tracing."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SourceTrace(BaseModel):
    """What raw data was pulled and from where."""

    source: str  # "linear", "github", "slack"
    entity_id: str  # UUID as string
    entity_name: str
    source_url: str | None = None  # Link back to the source tool
    fetched_at: str | None = None
    fields_used: list[str] = Field(default_factory=list)


class GraphTrace(BaseModel):
    """How the context graph connected entities."""

    traversal_type: (
        str  # "blocking_chain", "goal_linkage", "mention_scan", "ownership", "review_assignment"
    )
    path: list[dict] = Field(
        default_factory=list
    )  # [{entity_id, entity_name, edge_type, direction}]
    depth: int = 0
    entities_visited: int = 0
    description: str = ""  # Human-readable: "ENG-4530 BLOCKS ENG-4521 TAGGED_TO Retention +15%"


class ScoringTrace(BaseModel):
    """How one urgency factor was computed."""

    factor_name: str  # "staleness_days", "is_blocking_others", etc.
    weight: float  # The weight for this factor (e.g., 0.35)
    raw_value: float  # The raw factor value (0-1)
    weighted_value: float  # raw * weight * 100
    explanation: str  # Human-readable: "This task blocks 2 others downstream"
    evidence: list[dict] = Field(default_factory=list)  # Supporting data points


class LLMTrace(BaseModel):
    """What the LLM produced and with what context."""

    model: str = ""
    prompt_summary: str = ""  # Abbreviated prompt description
    input_entities: list[str] = Field(default_factory=list)  # Entity IDs
    input_token_count: int = 0
    output_token_count: int = 0
    reasoning: str = ""  # The LLM's narrative output
    grounding_entities: list[str] = Field(default_factory=list)
    latency_ms: int = 0


class RecommendationTrace(BaseModel):
    """Full trace for one briefing item / recommendation."""

    recommendation_id: str = ""  # UUID as string
    generated_at: str = ""
    source_traces: list[SourceTrace] = Field(default_factory=list)
    graph_traces: list[GraphTrace] = Field(default_factory=list)
    scoring_traces: list[ScoringTrace] = Field(default_factory=list)
    llm_trace: LLMTrace | None = None
    total_latency_ms: int = 0
