# Workers (Background Schedulers)

> `src/workers/`

## SyncScheduler (`sync_scheduler.py`)

Module-level singleton: `sync_scheduler = SyncScheduler()`

### Loop

```
while _running:
    _sync_all_orgs()
    sleep(settings.sync_interval_seconds)  # default: 300s = 5 min
```

### Per-Org Sync (`_sync_one`)

1. Get connector via `_get_connector(source)` - lazy singleton factory
2. Check `SyncState.status` - skip if already `SYNCING` (overlap guard)
3. Mark `SyncState.status = SYNCING`
4. Call `connector.sync_delta(db, org_id, token, since=last_sync_at)`
5. On success:
   - Update `SyncState` (IDLE, new `last_sync_at`)
   - Run `detect_person_duplicates()` for cross-source resolution
   - Run `suggest_pr_task_links()` for GitHub connectors (AI link suggestions)
6. On failure:
   - Set `SyncState.status = ERROR`, store error message
   - Log and continue (don't crash the loop)

### Skipped Orgs

- Demo orgs (`Organization.is_demo = True`) - they have fake tokens
- Orgs with no OAuth tokens

### Lazy Connector Loading

Connectors are imported on first use inside `_get_connector()` to avoid circular imports and keep startup fast:

```python
if source == SourceType.LINEAR:
    from src.connectors.linear import LinearConnector
    connector = LinearConnector()
```

Cached in `_connector_cache` dict after first instantiation.

## BriefingScheduler (`briefing_scheduler.py`)

- Runs daily at `settings.briefing_hour_utc` (default: 13 UTC = 8am ET)
- Iterates all OrgMembers
- Calls assemble + deliver pipeline per member
- Same loop pattern: `while _running`, sleep until next scheduled hour

## Lifespan Management (`main.py`)

Both schedulers are started as `asyncio.create_task()` in FastAPI's lifespan context manager:

```python
async def lifespan(app):
    tasks = [
        asyncio.create_task(sync_scheduler.run()),
        asyncio.create_task(briefing_scheduler.run()),
    ]
    yield
    for task in tasks:
        task.cancel()
```

Graceful shutdown via `.stop()` method which sets `_running = False`.
