# Frontend

> `frontend/src/`

## Tech Stack

- React 19, Vite 6, TypeScript (strict mode)
- Tailwind CSS with custom CSS variables (`--color-primary`, `--color-surface-*`)
- Radix UI + Class Variance Authority (CVA) for component variants
- TanStack React Query for server state
- React Router v7 for routing
- @xyflow/react for graph visualization
- Lucide React for icons

## Routing (`App.tsx`)

### Public Routes
- `/login` - Login page
- `/auth/google/callback` - Google OAuth callback
- `/connections/:connector/callback` - Connector OAuth callback

### Protected Routes (inside AuthGuard + Layout)
- `/` - Dashboard (briefings, urgency, activity)
- `/people`, `/people/:id`, `/people/resolutions` - People management
- `/goals`, `/goals/:id` - Goals hierarchy
- `/projects`, `/projects/:id` - Projects
- `/tasks`, `/tasks/:id` - Tasks
- `/connections`, `/connections/:connector` - Connector setup
- `/entities/:id` - Generic entity detail
- `/settings` - User settings

### AuthGuard
- Checks `localStorage.numen_access_token`
- Redirects to `/login` if missing, saves current path for post-login redirect
- Shows `OnboardingModal` if `numen_needs_onboarding` is set

## Data Fetching (Dual System - Migration in Progress)

### Preferred: TanStack React Query (`hooks/queries.ts`, `hooks/mutations.ts`)

```typescript
// Reads
const { data: goals } = useGoals();
const { data: entity } = useEntity(id);

// Writes
const { mutate } = useMutation(apiFunction);
await mutate(data);
queryClient.invalidateQueries({ queryKey: ["goals", orgId] });
```

- Query keys always include `orgId` for cache isolation
- `enabled` flag gates queries until orgId is set
- Mutations invalidate related query keys on success
- Stale time: 30 seconds, retry: 2

### Legacy: Custom Hook (`hooks/useApi.ts`)

```typescript
const { data, loading, error, refetch } = useApiCall(apiFn, [dependency]);
```

- Manual state management with useState
- Still used by some older pages
- **Do not use for new code** - use React Query instead

## API Client (`services/api.ts`)

### Module-Level Auth State
```typescript
let _orgId: string = "";
let _memberEmail: string = "";
let _accessToken: string = "";
```

Set via `setAccessToken()` and `setOrgContext()`.

### `fetchApi<T>(path, options)` Wrapper
- Sets auth headers: `Authorization: Bearer {token}` or `X-Member-Email` fallback
- Auto-refreshes JWT on 401 (single retry with `_isRefreshing` guard)
- Clears auth and redirects to `/login` on refresh failure
- Throws `ApiError` on non-2xx responses

### Token Refresh
- `tryRefreshToken()` uses stored refresh_token from localStorage
- One-time retry guard prevents cascading refresh attempts
- 30-day refresh token expiry - no re-login needed within 30 days

## State Management

### OrgContext (`contexts/OrgContext.tsx`)
- Provides: `orgId`, `orgName`, `memberEmail`, `isDemo`, `isAdmin`, `setOrg()`
- Initialized from localStorage
- Syncs `isDemo` flag from API on org load
- Gates all API calls via useApiCall/React Query `enabled` flag

### Local State
- Component-level `useState` for UI concerns (filters, view modes, form data)
- No Redux/Zustand - minimal global state by design

## Component Patterns

### UI Primitives (`components/ui/`)
Radix UI + CVA pattern:
- `button.tsx` - variants: default, destructive, outline, secondary, ghost, link + sizes
- `card.tsx`, `badge.tsx`, `dialog.tsx`, `tabs.tsx`, etc.
- All wrapped with `React.forwardRef`
- `cn()` utility merges Tailwind classes safely (clsx + twMerge)

### Feature Components
- `GoalCard`, `TaskCard`, `ProjectCard`, `BriefingCard` - domain-specific cards
- `StatusBadge`, `PriorityBadge` - consistent visual indicators
- `GraphView` - ReactFlow-based entity graph with typed node/edge colors
- `TracePanel` - urgency score provenance display

### InlineEdit System (`components/InlineEdit.tsx`)
Click-to-edit with optimistic updates:
- `InlineEditText` - single-line text
- `InlineEditTextarea` - multi-line text
- `InlineEditSelect` - dropdown
- `InlineEditDate` - date picker
- `InlineEditLabels` - tag management
- `InlineEditAssignee` - user selection with search
- `InlineEditMultiSelect` - multi-select for goals

Pattern: local state on edit, async `onSave` callback, rollback on error.

### Chat (`ChatPanel`)
- SSE-based streaming with line-by-line JSON parsing
- Token callbacks: `onToken`, `onToolStart`, `onToolEnd`, `onDone`, `onError`
- AbortController for cancellation

## LocalStorage Keys

| Key | Value |
|-----|-------|
| `numen_access_token` | JWT access token |
| `numen_refresh_token` | JWT refresh token |
| `numen_org_id` | Current org UUID |
| `numen_org_name` | Current org name |
| `numen_email` | Member email |
| `numen_user` | Full user JSON |
| `numen_is_demo` | Boolean string |
| `numen_is_admin` | Boolean string |
| `numen_needs_onboarding` | Boolean string |
| `numen_orgs` | Org list JSON |

## How to Add a New Page

1. Create page component in `pages/NewPage.tsx`
2. Add route in `App.tsx` inside the AuthGuard/Layout block
3. Add sidebar link in `Layout.tsx` (NavLink with icon)
4. Create read hooks in `hooks/queries.ts` using `useQuery`
5. Create mutation hooks in `hooks/mutations.ts` using `useMutation` + query invalidation
6. Add API functions in `services/api.ts`
7. Add TypeScript types in `types/index.ts` (mirror backend Pydantic models)
