import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  Link2,
  Target,
  FolderKanban,
  CheckSquare,
  Network,
  Cpu,
  Settings,
  FileText,
  BookOpen,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { useHotkey } from "@tanstack/react-hotkeys";
import { cn } from "@/lib/utils";
import { OrgSwitcher } from "@/components/OrgSwitcher";
import { UserViewSwitcher } from "@/components/UserViewSwitcher";
import { ChatPanel } from "@/components/ChatPanel";
import { NotificationBell } from "@/components/NotificationBell";
import { KeyboardShortcutHelp } from "@/components/KeyboardShortcutHelp";

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/people", label: "People", icon: Users },
  { to: "/goals", label: "Goals", icon: Target },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/prds", label: "PRDs", icon: FileText },
  { to: "/wiki", label: "Wiki", icon: BookOpen },
  { to: "/tasks", label: "Tasks", icon: CheckSquare },
  { to: "/graph", label: "Graph", icon: Network },
  { to: "/connections", label: "Connections", icon: Link2 },
  { to: "/mcp-setup", label: "MCP Setup", icon: Cpu },
  { to: "/settings", label: "Settings", icon: Settings },
];

/** Pages that use their own full-width layout + sticky chat */
const FULL_WIDTH_ROUTES = ["/prds", "/wiki"];

export function Layout() {
  const [showShortcutHelp, setShowShortcutHelp] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const location = useLocation();
  const isFullWidth = FULL_WIDTH_ROUTES.some((r) => location.pathname.startsWith(r));

  useHotkey({ key: "?", shift: true } as any, () => setShowShortcutHelp(true));

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r border-surface-200 bg-white transition-all duration-200",
          sidebarOpen ? "w-[260px]" : "w-[64px]",
        )}
      >
        {sidebarOpen && (
          <div className="px-4 pt-4 pb-2">
            <OrgSwitcher />
          </div>
        )}

        <nav
          className={cn(
            "flex-1 space-y-1 py-4",
            sidebarOpen ? "px-3" : "px-2",
          )}
        >
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/dashboard"}
              title={sidebarOpen ? undefined : item.label}
              className={({ isActive }) =>
                cn(
                  "flex items-center rounded-lg text-sm font-medium transition-colors",
                  sidebarOpen
                    ? "gap-3 px-3 py-2.5"
                    : "justify-center px-2 py-2.5",
                  isActive
                    ? "bg-primary-50 text-primary-700"
                    : "text-surface-600 hover:bg-surface-100 hover:text-surface-900",
                )
              }
            >
              <item.icon size={18} />
              {sidebarOpen && item.label}
            </NavLink>
          ))}
        </nav>

        {/* Notifications + footer (when sidebar open) */}
        {sidebarOpen && (
          <div className="border-t border-surface-100 px-4 py-3">
            <div className="flex items-center justify-between mb-2">
              <NotificationBell />
              <button
                onClick={() => setShowShortcutHelp(true)}
                className="rounded p-1.5 text-xs text-surface-400 hover:bg-surface-100 hover:text-surface-600"
                title="Keyboard shortcuts (?)"
              >
                <kbd className="rounded border border-surface-200 bg-surface-50 px-1.5 py-0.5 font-mono text-[10px]">
                  ?
                </kbd>
              </button>
            </div>
            <UserViewSwitcher />
          </div>
        )}

        {/* Collapse/expand toggle */}
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="flex items-center justify-center border-t border-surface-200 py-3 text-surface-400 hover:text-surface-600 transition-colors"
        >
          {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
        </button>
      </aside>

      {/* Main content */}
      <main className={cn(
        "flex-1 bg-surface-50",
        isFullWidth ? "overflow-hidden" : "overflow-y-auto",
      )}>
        {isFullWidth ? (
          <Outlet />
        ) : (
          <div className="mx-auto max-w-4xl px-6 py-8">
            <Outlet />
          </div>
        )}
      </main>

      {/* AI Chat - hidden on pages with their own sticky chat */}
      {!isFullWidth && <ChatPanel />}

      {/* Keyboard shortcut help */}
      <KeyboardShortcutHelp
        open={showShortcutHelp}
        onOpenChange={setShowShortcutHelp}
      />
    </div>
  );
}
