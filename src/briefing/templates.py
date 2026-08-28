"""Role-specific HTML email templates for Numen daily briefings."""

from __future__ import annotations

from datetime import datetime, timezone

from src.shared.models import OrgMember
from src.shared.types import BriefingItem, SignalType

# ── Brand constants ──────────────────────────────────────────────────────

_BRAND_COLOR = "#4F46E5"
_BRAND_COLOR_LIGHT = "#EEF2FF"
_BRAND_COLOR_DARK = "#3730A3"
_TEXT_PRIMARY = "#1F2937"
_TEXT_SECONDARY = "#6B7280"
_TEXT_MUTED = "#9CA3AF"
_BG_WHITE = "#FFFFFF"
_BG_GRAY = "#F9FAFB"
_BORDER_COLOR = "#E5E7EB"


def _urgency_color(score: float) -> str:
    """Return hex color based on urgency score thresholds."""
    if score >= 0.85:
        return "#DC2626"  # Red -- critical
    if score >= 0.65:
        return "#EA580C"  # Orange -- high
    if score >= 0.40:
        return "#CA8A04"  # Yellow -- medium
    return "#16A34A"  # Green -- low


def _urgency_label(score: float) -> str:
    """Return human-readable urgency label."""
    if score >= 0.85:
        return "Critical"
    if score >= 0.65:
        return "High"
    if score >= 0.40:
        return "Medium"
    return "Low"


def _format_provenance(provenance: list[dict]) -> str:
    """Format provenance into human-readable text."""
    if not provenance:
        return "Based on aggregated signals from your connected tools."

    parts: list[str] = []
    for entry in provenance:
        signal = entry.get("signal", "")
        if signal == SignalType.PR_REVIEW_REQUESTED:
            parts.append("Pull request review was requested via GitHub.")
        elif signal == SignalType.BLOCKING_CHAIN:
            count = entry.get("blocked_count", 0)
            parts.append(f"This item blocks {count} downstream task(s) in the graph.")
        elif signal == SignalType.RECENT_INCIDENT:
            severity = entry.get("severity", "unknown")
            parts.append(f"A {severity}-severity incident was detected on a related service.")
        elif signal == SignalType.BLOCKED_TASKS_PER_FEATURE:
            count = entry.get("blocked_count", 0)
            parts.append(f"{count} task(s) tagged to this feature have blocking dependencies.")
        elif signal == SignalType.OPEN_DECISION:
            parts.append("A decision node was recently linked to your profile.")
        elif signal == SignalType.LOW_ADOPTION:
            rate = entry.get("adoption_rate", 0)
            parts.append(f"Adoption rate is {round(rate * 100, 1)}%, below the threshold.")
        # EM signals
        elif signal == SignalType.IC_BLOCKED:
            parts.append("A direct report's task is blocked by an upstream dependency.")
        elif signal == SignalType.STALLED_PR:
            parts.append("A team member's pull request has had no activity for 48+ hours.")
        elif signal == SignalType.ONE_ON_ONE_PREP:
            parts.append("Summary prepared from your direct reports' workload and top items.")
        elif signal == SignalType.WIP_OVERLOAD:
            count = entry.get("in_progress_count", 0)
            parts.append(f"This person has {count} tasks in progress - may need help prioritizing.")
        # CTO signals
        elif signal == SignalType.ORG_BOTTLENECK:
            count = entry.get("blocked_count", 0)
            parts.append(f"This task is blocking {count} other tasks across the organization.")
        elif signal == SignalType.AT_RISK_GOAL:
            progress = entry.get("progress", 0)
            parts.append(f"Goal is at {progress}% progress with deadline approaching.")
        elif signal == SignalType.CROSS_TEAM_GAP:
            parts.append("A blocking dependency spans across team boundaries.")
        # VP Eng signals
        elif signal == SignalType.TEAM_HEALTH:
            parts.append("Team workload is above healthy thresholds.")
        elif signal == SignalType.SPRINT_STATE:
            parts.append("Organization-wide WIP ratio is elevated.")
        elif signal == SignalType.INCIDENT_RATE:
            count = entry.get("incident_count", 0)
            parts.append(f"{count} incidents detected in the last 7 days.")
        # VP Product signals
        elif signal == SignalType.GOAL_NO_COVERAGE:
            parts.append("This goal has zero tasks or features linked to it.")
        elif signal == SignalType.LAUNCH_BLOCKER:
            count = entry.get("blocked_count", 0)
            parts.append(f"{count} task(s) under this feature have blocking dependencies.")
        elif signal == SignalType.STALE_DECISION:
            days = entry.get("days_old", 0)
            parts.append(f"This decision has been open for {days} days without resolution.")
        # Designer signals
        elif signal == SignalType.CONFLICTING_SPEC:
            parts.append("This document conflicts with one or more other specifications.")
        elif signal == SignalType.OVERDUE_REVIEW:
            parts.append("This item has been waiting for your design review for over 48 hours.")
        elif signal == SignalType.HANDOFF_READY:
            parts.append("Engineering work is complete - ready for design verification.")
        else:
            # Generic fallback
            source = entry.get("source", "")
            desc = signal.replace("_", " ").capitalize()
            if source:
                parts.append(f"{desc} (via {source}).")
            else:
                parts.append(f"{desc}.")

    return " ".join(parts) if parts else "Based on aggregated signals from your connected tools."


def _render_goal_pills_html(goal_tags: list[str]) -> str:
    """Render goal tags as inline pill elements."""
    if not goal_tags:
        return ""

    pills = []
    for tag in goal_tags:
        pills.append(
            f'<span style="display:inline-block;background:{_BRAND_COLOR_LIGHT};'
            f"color:{_BRAND_COLOR};font-size:12px;font-weight:600;"
            f'padding:2px 10px;border-radius:12px;margin:2px 4px 2px 0;">'
            f"{tag}</span>"
        )
    return "".join(pills)


def _render_source_links_html(source_links: list[dict]) -> str:
    """Render source links as inline anchor elements."""
    if not source_links:
        return ""

    links = []
    for link in source_links:
        label = link.get("label", "Link")
        url = link.get("url", "#")
        links.append(
            f'<a href="{url}" style="color:{_BRAND_COLOR};font-size:13px;'
            f'text-decoration:none;margin-right:12px;" target="_blank">'
            f"{label.capitalize()} &rarr;</a>"
        )
    return "".join(links)


def _render_item_card_html(item: BriefingItem) -> str:
    """Render a single BriefingItem as an HTML card."""
    color = _urgency_color(item.urgency_score)
    label = _urgency_label(item.urgency_score)
    goal_pills = _render_goal_pills_html(item.goal_tags)
    source_links = _render_source_links_html(item.source_links)
    provenance_text = _format_provenance(item.provenance)

    suggested_html = ""
    if item.suggested_action:
        suggested_html = (
            f'<tr><td style="padding:8px 0 0 0;">'
            f'<span style="display:inline-block;background:#F0FDF4;color:#166534;'
            f'font-size:13px;font-weight:500;padding:4px 12px;border-radius:6px;">'
            f"Suggested: {item.suggested_action}</span>"
            f"</td></tr>"
        )

    goal_row = ""
    if goal_pills:
        goal_row = f'<tr><td style="padding:6px 0 0 0;">{goal_pills}</td></tr>'

    links_row = ""
    if source_links:
        links_row = f'<tr><td style="padding:8px 0 0 0;">{source_links}</td></tr>'

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="margin-bottom:16px;border:1px solid {_BORDER_COLOR};border-radius:8px;
                  border-left:4px solid {color};overflow:hidden;">
      <tr>
        <td style="padding:16px 20px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td>
                <span style="display:inline-block;background:{color};color:#FFFFFF;
                             font-size:11px;font-weight:700;text-transform:uppercase;
                             padding:2px 8px;border-radius:4px;letter-spacing:0.5px;">
                  {label}
                </span>
                <span style="color:{_TEXT_MUTED};font-size:12px;margin-left:8px;">
                  Score: {item.urgency_score:.2f}
                </span>
              </td>
            </tr>
            <tr>
              <td style="padding:8px 0 4px 0;">
                <span style="font-size:16px;font-weight:600;color:{_TEXT_PRIMARY};">
                  {item.title}
                </span>
              </td>
            </tr>
            <tr>
              <td style="padding:4px 0;">
                <span style="font-size:14px;color:{_TEXT_SECONDARY};line-height:1.5;">
                  {item.why_it_matters}
                </span>
              </td>
            </tr>
            {goal_row}
            {suggested_html}
            {links_row}
            <tr>
              <td style="padding:10px 0 0 0;border-top:1px solid {_BORDER_COLOR};margin-top:8px;">
                <details style="font-size:12px;color:{_TEXT_MUTED};">
                  <summary style="cursor:pointer;font-weight:500;">
                    Why Numen surfaced this
                  </summary>
                  <p style="margin:6px 0 0 0;line-height:1.5;">
                    {provenance_text}
                  </p>
                </details>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
    """


def render_briefing_email(
    member: OrgMember,
    items: list[BriefingItem],
    narrative: str | None = None,
) -> tuple[str, str]:
    """Render a complete briefing email as (html, plain_text).

    Args:
        member: The org member receiving the briefing.
        items: Sorted list of BriefingItems to include.
        narrative: Optional Claude-generated narrative paragraph.

    Returns:
        A tuple of (html_string, plain_text_string).
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%A, %B %-d, %Y")
    display_name = member.display_name or member.email.split("@")[0]

    # Compute stats
    blocking_count = sum(
        1
        for item in items
        if any(p.get("signal") == "blocking_chain" for p in item.provenance)
        or "blocker" in item.title.lower()
        or "blocked" in item.title.lower()
    )
    high_urgency_count = sum(1 for item in items if item.urgency_score >= 0.65)
    review_count = sum(1 for item in items if item.entity_type.value == "commit_pr")

    # Narrative section
    narrative_html = ""
    if narrative:
        narrative_html = f"""
        <tr>
          <td style="padding:0 24px 20px 24px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0"
                   style="background:{_BRAND_COLOR_LIGHT};border-radius:8px;">
              <tr>
                <td style="padding:16px 20px;font-size:14px;color:{_TEXT_PRIMARY};
                           line-height:1.6;">
                  {narrative}
                </td>
              </tr>
            </table>
          </td>
        </tr>
        """

    # Stats row
    stats_html = f"""
    <tr>
      <td style="padding:0 24px 24px 24px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td width="25%" style="text-align:center;padding:12px 4px;
                                    background:{_BG_GRAY};border-radius:8px 0 0 8px;
                                    border:1px solid {_BORDER_COLOR};border-right:none;">
              <span style="display:block;font-size:24px;font-weight:700;color:{_BRAND_COLOR};">
                {len(items)}
              </span>
              <span style="font-size:12px;color:{_TEXT_SECONDARY};text-transform:uppercase;
                           letter-spacing:0.5px;">
                Items
              </span>
            </td>
            <td width="25%" style="text-align:center;padding:12px 4px;
                                    background:{_BG_GRAY};
                                    border:1px solid {_BORDER_COLOR};border-right:none;">
              <span style="display:block;font-size:24px;font-weight:700;color:#DC2626;">
                {high_urgency_count}
              </span>
              <span style="font-size:12px;color:{_TEXT_SECONDARY};text-transform:uppercase;
                           letter-spacing:0.5px;">
                High Priority
              </span>
            </td>
            <td width="25%" style="text-align:center;padding:12px 4px;
                                    background:{_BG_GRAY};
                                    border:1px solid {_BORDER_COLOR};border-right:none;">
              <span style="display:block;font-size:24px;font-weight:700;color:#EA580C;">
                {blocking_count}
              </span>
              <span style="font-size:12px;color:{_TEXT_SECONDARY};text-transform:uppercase;
                           letter-spacing:0.5px;">
                Blockers
              </span>
            </td>
            <td width="25%" style="text-align:center;padding:12px 4px;
                                    background:{_BG_GRAY};border-radius:0 8px 8px 0;
                                    border:1px solid {_BORDER_COLOR};">
              <span style="display:block;font-size:24px;font-weight:700;color:{_BRAND_COLOR};">
                {review_count}
              </span>
              <span style="font-size:12px;color:{_TEXT_SECONDARY};text-transform:uppercase;
                           letter-spacing:0.5px;">
                Reviews
              </span>
            </td>
          </tr>
        </table>
      </td>
    </tr>
    """

    # Item cards
    cards_html = "\n".join(_render_item_card_html(item) for item in items)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Your Numen Briefing</title>
</head>
<body style="margin:0;padding:0;background:{_BG_GRAY};font-family:-apple-system,BlinkMacSystemFont,
             'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background:{_BG_GRAY};padding:24px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" border="0"
               style="background:{_BG_WHITE};border-radius:12px;
                      box-shadow:0 1px 3px rgba(0,0,0,0.1);overflow:hidden;">
          <!-- Header -->
          <tr>
            <td style="background:{_BRAND_COLOR};padding:32px 24px;text-align:center;">
              <span style="font-size:28px;font-weight:800;color:#FFFFFF;
                           letter-spacing:-0.5px;">
                Numen
              </span>
              <br>
              <span style="font-size:14px;color:rgba(255,255,255,0.85);
                           margin-top:4px;display:inline-block;">
                Your daily briefing
              </span>
            </td>
          </tr>

          <!-- Greeting -->
          <tr>
            <td style="padding:24px 24px 8px 24px;">
              <span style="font-size:13px;color:{_TEXT_MUTED};text-transform:uppercase;
                           letter-spacing:0.5px;">
                {date_str}
              </span>
              <br>
              <span style="font-size:20px;font-weight:600;color:{_TEXT_PRIMARY};
                           display:inline-block;margin-top:8px;">
                Good morning, {display_name}
              </span>
            </td>
          </tr>

          <!-- Narrative -->
          {narrative_html}

          <!-- Stats -->
          {stats_html}

          <!-- Items -->
          <tr>
            <td style="padding:0 24px 24px 24px;">
              {cards_html}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:24px;border-top:1px solid {_BORDER_COLOR};text-align:center;">
              <span style="font-size:13px;color:{_TEXT_MUTED};">
                Powered by
                <span style="color:{_BRAND_COLOR};font-weight:600;">Numen</span>
                &mdash; your engineering intelligence layer
              </span>
              <br>
              <a href="#unsubscribe" style="font-size:12px;color:{_TEXT_MUTED};
                                            text-decoration:underline;margin-top:8px;
                                            display:inline-block;">
                Manage notification preferences
              </a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    # ── Plain text version ───────────────────────────────────────────────
    plain_lines: list[str] = [
        "NUMEN -- Your Daily Briefing",
        f"{date_str}",
        "",
        f"Good morning, {display_name}",
        "",
    ]

    if narrative:
        plain_lines.append(narrative)
        plain_lines.append("")

    plain_lines.append(
        f"--- {len(items)} items | {high_urgency_count} high priority | "
        f"{blocking_count} blockers | {review_count} reviews ---"
    )
    plain_lines.append("")

    for i, item in enumerate(items, 1):
        label = _urgency_label(item.urgency_score)
        plain_lines.append(f"{i}. [{label}] {item.title}")
        plain_lines.append(f"   Why: {item.why_it_matters}")
        if item.goal_tags:
            plain_lines.append(f"   Goals: {', '.join(item.goal_tags)}")
        if item.suggested_action:
            plain_lines.append(f"   Action: {item.suggested_action}")
        if item.source_links:
            for link in item.source_links:
                plain_lines.append(f"   {link.get('label', 'Link')}: {link.get('url', '')}")
        provenance_text = _format_provenance(item.provenance)
        plain_lines.append(f"   Surfaced because: {provenance_text}")
        plain_lines.append("")

    plain_lines.extend(
        [
            "---",
            "Powered by Numen -- your engineering intelligence layer",
            "Manage notification preferences: [unsubscribe link]",
        ]
    )

    return html, "\n".join(plain_lines)
