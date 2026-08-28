import { useState, type ReactNode } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { ChatSticky } from "@/components/chat/ChatSticky";

interface ThreeColumnLayoutProps {
  /** Content for the left sidebar */
  sidebar: ReactNode;
  /** Sidebar width in pixels (default 260) */
  sidebarWidth?: number;
  /** Header content rendered in the sidebar header area */
  sidebarHeader?: ReactNode;
  /** Toolbar rendered above the main content area */
  toolbar?: ReactNode;
  /** Main content area */
  children: ReactNode;
  /** Optional right panel */
  rightPanel?: ReactNode;
  /** Right panel width in pixels (default 288) */
  rightPanelWidth?: number;
  /** Context hint passed to sticky chat */
  chatContextHint?: string;
  /** Whether to show the sticky chat (default true) */
  showChat?: boolean;
}

export function ThreeColumnLayout({
  sidebar,
  sidebarWidth = 260,
  sidebarHeader,
  toolbar,
  children,
  rightPanel,
  rightPanelWidth = 288,
  chatContextHint,
  showChat = true,
}: ThreeColumnLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Left sidebar */}
      <aside
        className="flex shrink-0 flex-col border-r border-surface-200 bg-white transition-all duration-200 overflow-hidden"
        style={{ width: sidebarOpen ? `${sidebarWidth}px` : "0px" }}
      >
        {sidebarHeader && (
          <div className="border-b border-surface-200 px-3 py-3">
            {sidebarHeader}
          </div>
        )}
        <div className="flex flex-1 flex-col overflow-hidden">
          {sidebar}
        </div>
      </aside>

      {/* Main area (toolbar + content + chat) */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Toolbar */}
        {toolbar && (
          <div className="flex shrink-0 items-center gap-2 border-b border-surface-200 bg-white px-4 py-2">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="flex items-center justify-center rounded-md p-1.5 text-surface-400 hover:bg-surface-100 hover:text-surface-600 transition-colors"
              title={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
            >
              {sidebarOpen ? <PanelLeftClose size={16} /> : <PanelLeftOpen size={16} />}
            </button>
            <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto">
              {toolbar}
            </div>
          </div>
        )}

        {/* Content + right panel */}
        <div className="flex min-w-0 flex-1 overflow-hidden">
          {/* Main content */}
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
            <div className="flex-1 overflow-y-auto">
              {children}
            </div>

            {/* Sticky chat at bottom */}
            {showChat && <ChatSticky contextHint={chatContextHint} />}
          </div>

          {/* Right panel */}
          {rightPanel && (
            <aside
              className="hidden shrink-0 border-l border-surface-200 bg-white overflow-y-auto lg:block"
              style={{ width: `${rightPanelWidth}px`, maxWidth: `${rightPanelWidth}px` }}
            >
              {rightPanel}
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}
