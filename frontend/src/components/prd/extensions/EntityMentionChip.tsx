import { type NodeViewProps, NodeViewWrapper } from "@tiptap/react";
import { User, CheckSquare, Target, FolderKanban } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";

interface EntityStyle {
  bg: string;
  text: string;
  icon: typeof User;
  prefix: string;
  route: string;
}

const PERSON_STYLE: EntityStyle = { bg: "bg-purple-50", text: "text-purple-700", icon: User, prefix: "@", route: "" };

const ENTITY_STYLES: Record<string, EntityStyle> = {
  person: PERSON_STYLE,
  task: { bg: "bg-green-50", text: "text-green-700", icon: CheckSquare, prefix: "", route: "/tasks" },
  goal: { bg: "bg-amber-50", text: "text-amber-700", icon: Target, prefix: "", route: "/goals" },
  project: { bg: "bg-blue-50", text: "text-blue-700", icon: FolderKanban, prefix: "", route: "/projects" },
};

/**
 * Inline chip rendered for entityMention nodes in the TipTap editor.
 * Supports person, task, goal, and project mentions with type-specific
 * colors and icons. Non-person mentions are clickable and navigate to
 * the entity's detail page.
 */
export function EntityMentionChip({ node }: NodeViewProps) {
  const { entityId, entityName, entityType } = node.attrs as {
    entityId: string;
    entityType: string;
    entityName: string;
  };

  const navigate = useNavigate();
  const style = ENTITY_STYLES[entityType] ?? PERSON_STYLE;
  const Icon = style.icon;
  const isClickable = entityType !== "person" && !!style.route;

  const handleClick = () => {
    if (isClickable) {
      navigate(`${style.route}/${entityId}`);
    }
  };

  return (
    <NodeViewWrapper as="span" className="inline">
      <span
        onClick={handleClick}
        className={cn(
          "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5",
          style.bg, style.text, "text-sm font-medium",
          "select-none",
          isClickable ? "cursor-pointer hover:opacity-80" : "cursor-default",
        )}
      >
        <Icon className="h-3.5 w-3.5 shrink-0" />
        <span>{style.prefix}{entityName}</span>
      </span>
    </NodeViewWrapper>
  );
}
