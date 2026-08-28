# L4: Briefings

> `src/briefing/`

## Assembly (`assembler.py`)

Briefings are personalized per OrgMember based on their role:

### Engineer Signals
- Top urgent owned tasks (TASK entities with OWNS edge from person)
- PRs awaiting review (COMMIT_PR with MENTIONED_IN + status=open)
- Blocking chains from owned tasks
- Recent incidents on owned services

### PM Signals
- Top urgent features
- Blocked task counts per feature
- Open decisions (MENTIONED_IN edges)
- Low-adoption features (adoption_rate < 20%)

### Constants
- Recent window: 7 days
- Low adoption threshold: 20%
- Max briefing items: 10
- Items sorted by urgency descending

### BriefingItem Structure

Each item contains:
- `entity_id`, `entity_type`, `title`
- `why_it_matters` - human-readable explanation
- `urgency_score` - the computed score
- `goal_tags` - linked goal names
- `source_links` - both internal app links and external URLs from entity properties
- `suggested_action` - what the person should do
- `provenance` - full tracing data

## Delivery Pipeline (`delivery.py`)

1. **Narrative generation** (optional) - `claude/actions.generate_briefing_narrative()` wraps structured items in a Claude-generated narrative
2. **HTML rendering** - `templates.py` renders email with HTML + plain text
3. **Send** - via Resend API, with 3 retries and exponential backoff (1s base)
4. **Record** - `Briefing` row in DB with `delivery_status` (PENDING/SENT/FAILED)

The Resend API is synchronous - runs in executor via `asyncio.to_thread`.

## Scheduling (`workers/briefing_scheduler.py`)

- Runs daily at `settings.briefing_hour_utc` (default: 13 = 8am ET)
- Iterates all OrgMembers, calls assemble + deliver for each
- Skips members without `person_entity_id`
