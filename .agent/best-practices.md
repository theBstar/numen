# Best Practices

## Backend

### Async
- `async/await` everywhere - never block the event loop
- Use `httpx.AsyncClient` (not `requests`) for HTTP calls
- External API calls need timeout and retry patterns (see `claude/client.py`)
- Resend email API is sync - wrap with `asyncio.to_thread`

### Database
- Always scope queries by `org_id` - it's the tenant boundary
- Use `await db.flush()` after ORM mutations within a transaction
- Use `await db.commit()` only at the top-level boundary (route handler or scheduler loop)
- Never commit inside a nested function - let the caller manage transaction boundaries
- `expire_on_commit=False` is set globally - no automatic refresh after commits

### Entity & Edge
- `source_ids` are additive-only - never remove keys during upsert
- JSONB properties: always use `.get()` with defaults when reading
- `merged_into` chain is max 5 hops - if longer, something is broken
- Always filter `merged_into IS NULL` when querying canonical entities
- Edge unique constraint is `(from_entity_id, to_entity_id, type)` - handle conflicts on merge
- Task status is forward-only: `todo -> in_progress -> in_review -> merged -> done`

### Naming & Style
- Use `RoleType.ENGINEER` (uppercase member name) for SQLAlchemy enums
- In raw SQL queries, never hardcode enum strings - use parameterized values from the Python enum's `.name` (e.g., `EdgeType.BLOCKS.name` yields `"BLOCKS"`) since Postgres stores the uppercase member name, not the lowercase `.value`
- Use hyphens (-) not em dashes in all content
- `from __future__ import annotations` at top of every module
- `logger = logging.getLogger(__name__)` per module
- Line length: 100 characters (ruff config)
- Lint rules: E, F, I, N, W

### Connector Patterns
- Connectors are stateless singletons, lazily loaded
- Schemas go in `connectors/schemas/` as Pydantic models
- Always return `ConnectorSyncResult` from sync methods
- Handle API pagination with cursor-based approach

## Frontend

### Data Fetching
- Use TanStack React Query for all new data fetching (not legacy `useApi` hooks)
- Query keys must include `orgId` for cache isolation
- Gate queries with `enabled: !!orgId`
- Mutations must invalidate related queries on success
- Stale time: 30 seconds default

### TypeScript
- Strict mode - no `any` types
- Mirror backend Pydantic models in `types/index.ts`
- Use enum values matching backend exactly (lowercase string values)

### Styling
- Tailwind CSS only - no CSS modules or styled-components
- Use `cn()` utility from `lib/utils.ts` for class merging
- Custom CSS variables defined in `index.css` for theming
- Radix UI + CVA for component variants

### Components
- UI primitives in `components/ui/` (Radix + CVA)
- Feature components use props-based composition
- InlineEdit pattern: local state on edit, async onSave, rollback on error
- Wrap with `React.forwardRef` for ref forwarding

## API Design

### Route Rules
- All backend routes under `/api/` prefix - no exceptions
- Never create a backend route that conflicts with a frontend route
- Vite proxy forwards `/api/*` to backend only

### Response Format
- Lists: `{ items: T[] }` - never bare arrays
- Paginated: `{ items, total, page, page_size }`
- Single by ID: `T` directly, 404 with `{ detail: "Not found" }`
- Latest: `T | null` with 200, not 404
- Errors: `{ detail: "Human-readable message" }`

### Security
- Never read `.env` files directly - use `.env.example` for structure reference
- Google OAuth secrets: backend only, frontend never sees them
- JWT: memory + localStorage, never cookies
- Webhook signatures verified per-connector

## Testing

### Structure
- Test files mirror `src/` structure: `tests/test_graph/test_repository.py` tests `src/graph/repository.py`
- Use `conftest.py` fixtures for shared test objects

### Fixtures (`tests/conftest.py`)
- `mock_db` - AsyncMock session
- `mock_entity`, `mock_person`, `mock_goal`, `mock_pr_entity` - pre-built entity objects
- `mock_member` - OrgMember with test data
- Well-known UUIDs: `TEST_ORG_ID`, `TEST_PERSON_ID`, etc.

### Patterns
- `@pytest.mark.asyncio` + `async def test_...()` for async tests (auto mode configured)
- `pytest-httpx` for HTTP mocking in connector tests
- `fakeredis` for Redis stubbing in cache tests
- `aiosqlite` for in-memory SQLite when needed
- Mock `AsyncSession`, never hit real DB in unit tests

### What to Test
- Edge cases: empty results, merged entities, missing properties
- Unique constraint handling on concurrent operations
- Forward-only status transitions (never backward)
- Merge chain following (including merged stubs)

## Anti-Patterns

- **Never** create entities without `org_id`
- **Never** hard-delete entities - use `merged_into` for Person dedup
- **Never** skip the merge chain in upsert - always call `_resolve_merged_chain`
- **Never** move task status backward
- **Never** commit inside nested functions
- **Never** add routes outside `/api/` prefix
- **Never** modify the `website/` directory
- **Never** store OAuth secrets on the frontend
- **Never** use em dashes - use hyphens
- **Never** return bare arrays from list endpoints
- **Never** read `.env` files - reference `.env.example` for structure
- **Never** use `requests` library - use `httpx.AsyncClient`
- **Never** use legacy `useApi` hooks for new frontend code
- **Never** use `any` type in TypeScript
- **Never** hardcode enum strings in raw SQL - pass `EnumClass.MEMBER.name` as a parameter (DB stores uppercase names)
