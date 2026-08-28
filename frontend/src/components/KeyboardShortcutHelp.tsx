import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { GLOBAL_SHORTCUTS, TASKS_SHORTCUTS, BOARD_SHORTCUTS, groupShortcutsBySection } from "@/lib/hotkeys";
import type { ShortcutDef } from "@/lib/hotkeys";

interface KeyboardShortcutHelpProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  extraShortcuts?: ShortcutDef[];
}

function KeyDisplay({ hotkey }: { hotkey: string }) {
  const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
  const parts = hotkey.split("+").map((part) => {
    switch (part) {
      case "Mod": return isMac ? "\u2318" : "Ctrl";
      case "Shift": return isMac ? "\u21E7" : "Shift";
      case "Alt": return isMac ? "\u2325" : "Alt";
      case "ArrowLeft": return "\u2190";
      case "ArrowRight": return "\u2192";
      case "ArrowUp": return "\u2191";
      case "ArrowDown": return "\u2193";
      case "Escape": return "Esc";
      case "Enter": return "\u21B5";
      default: return part.toUpperCase();
    }
  });
  return (
    <span className="flex items-center gap-0.5">
      {parts.map((part, i) => (
        <kbd key={i} className="inline-flex h-5 min-w-[20px] items-center justify-center rounded border border-surface-200 bg-surface-50 px-1.5 font-mono text-[11px] font-medium text-surface-600">
          {part}
        </kbd>
      ))}
    </span>
  );
}

export function KeyboardShortcutHelp({ open, onOpenChange, extraShortcuts = [] }: KeyboardShortcutHelpProps) {
  const allShortcuts = [...GLOBAL_SHORTCUTS, ...TASKS_SHORTCUTS, ...BOARD_SHORTCUTS, ...extraShortcuts];
  const grouped = groupShortcutsBySection(allShortcuts);
  const sectionOrder = ["General", "Navigation", "Actions", "Board"];
  const sections = sectionOrder.filter((s) => grouped[s]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Keyboard Shortcuts</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 max-h-[60vh] overflow-y-auto">
          {sections.map((section) => (
            <div key={section}>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-surface-400">
                {section}
              </h3>
              <div className="space-y-1.5">
                {grouped[section]!.map((shortcut) => (
                  <div key={shortcut.hotkey} className="flex items-center justify-between py-1">
                    <span className="text-sm text-surface-700">{shortcut.label}</span>
                    <KeyDisplay hotkey={shortcut.hotkey} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
