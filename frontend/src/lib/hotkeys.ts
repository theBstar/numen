/**
 * Centralized shortcut registry for all pages.
 * Each page defines its shortcuts as data. The KeyboardShortcutHelp
 * overlay reads from useHotkeyRegistrations() + these definitions.
 */

export interface ShortcutDef {
  hotkey: string;
  label: string;
  description?: string;
  section: string;
}

export const GLOBAL_SHORTCUTS: ShortcutDef[] = [
  { hotkey: "?", label: "Show keyboard shortcuts", section: "General" },
  { hotkey: "Escape", label: "Close dialog / deselect", section: "General" },
];

export const TASKS_SHORTCUTS: ShortcutDef[] = [
  { hotkey: "c", label: "Create task", section: "Actions" },
  { hotkey: "1", label: "Switch to list view", section: "Navigation" },
  { hotkey: "2", label: "Switch to board view", section: "Navigation" },
  { hotkey: "/", label: "Focus search", section: "Navigation" },
  { hotkey: "Mod+a", label: "Select all tasks", section: "Actions" },
];

export const BOARD_SHORTCUTS: ShortcutDef[] = [
  { hotkey: "ArrowLeft", label: "Previous column", section: "Board" },
  { hotkey: "ArrowRight", label: "Next column", section: "Board" },
  { hotkey: "ArrowUp", label: "Previous card", section: "Board" },
  { hotkey: "ArrowDown", label: "Next card", section: "Board" },
  { hotkey: "Shift+ArrowLeft", label: "Move card left", section: "Board" },
  { hotkey: "Shift+ArrowRight", label: "Move card right", section: "Board" },
  { hotkey: "Enter", label: "Open task detail", section: "Board" },
];

/** Group shortcut definitions by section for display. */
export function groupShortcutsBySection(shortcuts: ShortcutDef[]): Record<string, ShortcutDef[]> {
  const groups: Record<string, ShortcutDef[]> = {};
  for (const s of shortcuts) {
    if (!groups[s.section]) groups[s.section] = [];
    groups[s.section]!.push(s);
  }
  return groups;
}
