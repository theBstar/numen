import {
  useState,
  useEffect,
  useCallback,
  useRef,
  forwardRef,
  useImperativeHandle,
} from "react";
import type { SuggestionKeyDownProps } from "@tiptap/suggestion";
import { User, CheckSquare, Target, FolderKanban } from "lucide-react";
import { cn } from "@/lib/utils";
import { listMembers, getTasks, getGoals, getProjects } from "@/services/api";
import type { OrgMember } from "@/types";

// -- Types --

export type EntityMentionType = "person" | "task" | "goal" | "project";

export interface EntityMentionItem {
  entityId: string;
  entityType: EntityMentionType;
  entityName: string;
}

export interface EntityMentionListRef {
  onKeyDown: (props: SuggestionKeyDownProps) => boolean;
}

interface EntityMentionListProps {
  items: EntityMentionItem[];
  command: (item: EntityMentionItem) => void;
}

const ENTITY_ICONS: Record<EntityMentionType, typeof User> = {
  person: User,
  task: CheckSquare,
  goal: Target,
  project: FolderKanban,
};

const ENTITY_COLORS: Record<EntityMentionType, { selected: string; icon: string }> = {
  person: { selected: "bg-purple-50 text-purple-700", icon: "border-purple-200 bg-purple-50" },
  task: { selected: "bg-green-50 text-green-700", icon: "border-green-200 bg-green-50" },
  goal: { selected: "bg-amber-50 text-amber-700", icon: "border-amber-200 bg-amber-50" },
  project: { selected: "bg-blue-50 text-blue-700", icon: "border-blue-200 bg-blue-50" },
};

const ENTITY_LABELS: Record<EntityMentionType, string> = {
  person: "People",
  task: "Tasks",
  goal: "Goals",
  project: "Projects",
};

// -- Component --

export const EntityMentionList = forwardRef<EntityMentionListRef, EntityMentionListProps>(
  ({ items, command }, ref) => {
    const [selectedIndex, setSelectedIndex] = useState(0);
    const containerRef = useRef<HTMLDivElement>(null);

    const selectItem = useCallback(
      (index: number) => {
        const item = items[index];
        if (item) {
          command(item);
        }
      },
      [items, command],
    );

    useImperativeHandle(ref, () => ({
      onKeyDown: ({ event }: SuggestionKeyDownProps) => {
        if (event.key === "ArrowUp") {
          setSelectedIndex((prev) => (prev + items.length - 1) % items.length);
          return true;
        }
        if (event.key === "ArrowDown") {
          setSelectedIndex((prev) => (prev + 1) % items.length);
          return true;
        }
        if (event.key === "Enter") {
          selectItem(selectedIndex);
          return true;
        }
        return false;
      },
    }));

    useEffect(() => {
      setSelectedIndex(0);
    }, [items]);

    // Scroll selected item into view
    useEffect(() => {
      const container = containerRef.current;
      if (!container) return;
      const selected = container.querySelector(`[data-index="${selectedIndex}"]`);
      if (selected) {
        selected.scrollIntoView({ block: "nearest" });
      }
    }, [selectedIndex]);

    if (items.length === 0) {
      return (
        <div className="rounded-lg border border-surface-200 bg-white p-3 shadow-lg">
          <p className="text-sm text-surface-400">No results found</p>
        </div>
      );
    }

    // Group items by type for section headers
    const groups: { type: EntityMentionType; items: { item: EntityMentionItem; globalIndex: number }[] }[] = [];
    const typeOrder: EntityMentionType[] = ["person", "task", "goal", "project"];

    for (const type of typeOrder) {
      const typeItems = items
        .map((item, idx) => ({ item, globalIndex: idx }))
        .filter(({ item }) => item.entityType === type);
      if (typeItems.length > 0) {
        groups.push({ type, items: typeItems });
      }
    }

    return (
      <div
        ref={containerRef}
        className="max-h-80 min-w-[280px] overflow-y-auto rounded-lg border border-surface-200 bg-white py-1 shadow-lg"
      >
        {groups.map((group) => {
          const Icon = ENTITY_ICONS[group.type];
          const colors = ENTITY_COLORS[group.type];
          return (
            <div key={group.type}>
              <div className="px-3 pt-2 pb-1">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-surface-400">
                  {ENTITY_LABELS[group.type]}
                </span>
              </div>
              {group.items.map(({ item, globalIndex: idx }) => (
                <button
                  key={`${item.entityType}-${item.entityId}`}
                  type="button"
                  data-index={idx}
                  onClick={() => selectItem(idx)}
                  className={cn(
                    "flex w-full items-center gap-3 px-3 py-1.5 text-left transition-colors",
                    idx === selectedIndex
                      ? `${colors.selected}`
                      : "text-surface-700 hover:bg-surface-50",
                  )}
                >
                  <div
                    className={cn(
                      "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border",
                      idx === selectedIndex ? colors.icon : "border-surface-200 bg-surface-50",
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{item.entityName}</p>
                  </div>
                </button>
              ))}
            </div>
          );
        })}
      </div>
    );
  },
);
EntityMentionList.displayName = "EntityMentionList";

// -- Search helpers --

// Cache members list to avoid refetching on every keystroke
let membersCache: OrgMember[] | null = null;
let membersCacheTime = 0;
const CACHE_TTL_MS = 30_000; // 30 seconds

async function getOrgMembers(): Promise<OrgMember[]> {
  const now = Date.now();
  if (membersCache && now - membersCacheTime < CACHE_TTL_MS) {
    return membersCache;
  }
  try {
    membersCache = await listMembers();
    membersCacheTime = now;
    return membersCache;
  } catch {
    return membersCache ?? [];
  }
}

/**
 * Search across all entity types: people, tasks, goals, projects.
 * Results are returned grouped by type for the suggestion dropdown.
 */
export async function searchEntities(query: string): Promise<EntityMentionItem[]> {
  const lowerQuery = query.toLowerCase();
  const results: EntityMentionItem[] = [];

  // Search members (always fast - cached)
  try {
    const members = await getOrgMembers();
    const matchedMembers = members
      .filter((m) => {
        const name = (m.display_name ?? m.email).toLowerCase();
        const email = m.email.toLowerCase();
        return name.includes(lowerQuery) || email.includes(lowerQuery);
      })
      .slice(0, 5)
      .map((m) => ({
        entityId: m.person_entity_id ?? m.id,
        entityType: "person" as const,
        entityName: m.display_name ?? m.email,
      }));
    results.push(...matchedMembers);
  } catch {
    // Ignore member search errors
  }

  // Only search other entities if query is at least 2 chars
  if (lowerQuery.length >= 2) {
    // Search tasks, goals, projects in parallel
    const [tasks, goals, projects] = await Promise.allSettled([
      getTasks(),
      getGoals(),
      getProjects(),
    ]);

    if (tasks.status === "fulfilled") {
      const matchedTasks = tasks.value
        .filter((t) => t.title.toLowerCase().includes(lowerQuery))
        .slice(0, 5)
        .map((t) => ({
          entityId: t.id,
          entityType: "task" as const,
          entityName: t.title,
        }));
      results.push(...matchedTasks);
    }

    if (goals.status === "fulfilled") {
      const matchedGoals = goals.value
        .filter((g) => g.title.toLowerCase().includes(lowerQuery))
        .slice(0, 5)
        .map((g) => ({
          entityId: g.id,
          entityType: "goal" as const,
          entityName: g.title,
        }));
      results.push(...matchedGoals);
    }

    if (projects.status === "fulfilled") {
      const matchedProjects = projects.value
        .filter((p) => p.name.toLowerCase().includes(lowerQuery))
        .slice(0, 5)
        .map((p) => ({
          entityId: p.id,
          entityType: "project" as const,
          entityName: p.name,
        }));
      results.push(...matchedProjects);
    }
  }

  return results;
}

// Keep backward compat export
export const searchMembers = searchEntities;
