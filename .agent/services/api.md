# API Layer

> `src/api/`

## Dependency Injection Chain (`dependencies.py`)

```
get_db()                    -> AsyncSession (yielded, auto-closed)
get_org(org_id)             -> Organization (or 404)
get_current_user(Authorization) -> User | None (JWT decode)
get_current_user_required() -> User (401 if not authenticated)
get_current_member(org_id, X-Member-Email, user) -> OrgMember
  -> Path 1: JWT Bearer -> lookup by user_id, fallback to email, auto-link
  -> Path 2: X-Member-Email header (dev/demo fallback)
  -> Auto-creates Person entity via ensure_person_entity_for_member()
verify_webhook_signature(connector) -> factory returning async dependency
  -> Slack: HMAC-SHA256 with v0 timestamp
  -> GitHub: HMAC-SHA256 (X-Hub-Signature-256)
  -> Linear: signature logging (stub)
```

## Route File Organization

| File | Prefix | Endpoints |
|------|--------|-----------|
| `routes.py` | `/api/orgs/{id}/` | entities, briefings, urgency, graph, connectors, demo, dispatch, activity |
| `routes_goals.py` | `/api/orgs/{id}/goals` | CRUD, tree, progress, link entity to goal |
| `routes_projects.py` | `/api/orgs/{id}/projects` | CRUD, tasks, stats |
| `routes_tasks.py` | `/api/orgs/{id}/tasks` | CRUD with filtering (status, priority, assignee, project, goal) |
| `routes_edges.py` | `/api/edges` | Create, delete, get edges for entity |
| `auth.py` | `/auth/{connector}/` | Connector OAuth flows (connect, callback) |
| `user_auth.py` | `/api/auth/` | Google OAuth, JWT tokens, refresh, logout |

## Endpoint Reference

### Authentication
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/google/auth-url` | Get Google OAuth consent URL |
| POST | `/api/auth/google/login` | Exchange Google code for JWT tokens |
| POST | `/api/auth/refresh` | Refresh JWT access token |
| POST | `/api/auth/logout` | Invalidate refresh token |
| POST | `/api/onboarding` | Complete new user onboarding |

### Organizations
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/orgs` | List orgs (filtered by user membership) |
| POST | `/api/orgs` | Create organization |
| POST | `/api/orgs/{id}/members` | Add org member |

### Entities & Graph
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/orgs/{id}/entities` | List entities (filter by type, search) |
| GET | `/api/orgs/{id}/entities/{eid}` | Entity detail + edges |
| GET | `/api/orgs/{id}/graph/{eid}` | Graph neighborhood |

### Urgency
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/orgs/{id}/urgency` | Top urgent items for current user |
| GET | `/api/orgs/{id}/urgency/{eid}/trace` | Urgency scoring trace for entity |

### Briefings
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/orgs/{id}/briefings` | List past briefings |
| GET | `/api/orgs/{id}/briefings/latest` | Latest briefing |
| POST | `/api/orgs/{id}/briefings/generate` | Trigger on-demand briefing |

### Goals
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/orgs/{id}/goals` | List goals |
| POST | `/api/orgs/{id}/goals` | Create goal |
| GET | `/api/orgs/{id}/goals/{gid}` | Goal detail with progress |
| PUT | `/api/orgs/{id}/goals/{gid}` | Update goal |
| DELETE | `/api/orgs/{id}/goals/{gid}` | Delete goal |
| GET | `/api/orgs/{id}/goals/tree` | Goal hierarchy tree |

### Projects
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/orgs/{id}/projects` | List projects |
| POST | `/api/orgs/{id}/projects` | Create project |
| GET | `/api/orgs/{id}/projects/{pid}` | Project detail with stats |
| PUT | `/api/orgs/{id}/projects/{pid}` | Update project |
| DELETE | `/api/orgs/{id}/projects/{pid}` | Delete project |

### Tasks
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/orgs/{id}/tasks` | List tasks (filter: status, priority, assignee, project, goal) |
| POST | `/api/orgs/{id}/tasks` | Create task |
| GET | `/api/orgs/{id}/tasks/{tid}` | Task detail |
| PUT | `/api/orgs/{id}/tasks/{tid}` | Update task |
| DELETE | `/api/orgs/{id}/tasks/{tid}` | Delete task |

### Connectors
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/orgs/{id}/connectors` | Connector status |
| GET | `/auth/{connector}/connect` | Start connector OAuth flow |
| GET | `/auth/{connector}/callback` | Connector OAuth callback |
| POST | `/api/webhooks/{connector}` | Webhook receiver |

### Other
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/orgs/{id}/dispatch` | Claude dispatch (summarize_pr_diff) |
| POST | `/api/orgs/{id}/demo/regenerate` | Re-trigger demo data variance |

Auth: JWT Bearer token via `Authorization` header. Fallback to `X-Member-Email` header in dev mode.

## Response Contracts

- **List endpoints**: `{ items: T[] }` - never bare arrays
- **Paginated lists**: `{ items: T[], total: number, page: number, page_size: number }`
- **Single item by ID**: `T` directly. 404 with `{ detail: "Not found" }`
- **Latest queries**: `T | null` with 200, not 404
- **Create/Update**: Return the created/updated object `T`
- **Delete**: `{ status: "ok" }` or 204
- **Errors**: `{ detail: "Human-readable message" }` with appropriate HTTP status

## Schemas (`schemas.py`)

Pydantic request/response models with `model_config = {"from_attributes": True}` for ORM serialization.

Key schemas: `EntityResponse`, `EdgeResponse`, `UrgencyScoreResponse`, `PaginatedResponse`, `GoalCreateRequest`, `ProjectCreateRequest`, `TaskCreateRequest`.

## Webhook Verification

| Connector | Mechanism | Header |
|-----------|-----------|--------|
| Slack | HMAC-SHA256, v0 timestamp prefix | `X-Slack-Signature` + `X-Slack-Request-Timestamp` |
| GitHub | HMAC-SHA256 | `X-Hub-Signature-256` |
| Linear | Signature logging (stub) | `Linear-Signature` |

Graceful degradation: if signing secret not configured, logs warning and skips verification.
