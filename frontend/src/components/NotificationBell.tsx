import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, CheckCheck, Loader2 } from "lucide-react";
import { useNotifications, useUnreadNotificationCount } from "@/hooks/queries";
import { useMarkNotificationRead, useMarkAllNotificationsRead } from "@/hooks/mutations";
import { formatRelativeTime } from "@/lib/utils";

export function NotificationBell() {
  const navigate = useNavigate();
  const { data: countData } = useUnreadNotificationCount();
  const { data: notifData, isLoading } = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();
  const [isOpen, setIsOpen] = useState(false);

  const unreadCount = countData?.count ?? 0;
  const notifications = notifData?.items ?? [];

  function handleNotificationClick(notif: { id: string; entity_id: string | null; read_at: string | null }) {
    if (!notif.read_at) {
      markRead.mutate(notif.id);
    }
    if (notif.entity_id) {
      navigate(`/tasks/${notif.entity_id}`);
    }
    setIsOpen(false);
  }

  const notificationTypeIcons: Record<string, string> = {
    task_assigned: "Assigned to you",
    status_changed: "Status changed",
    comment_added: "New comment",
    mentioned: "You were mentioned",
    subtask_completed: "Subtask completed",
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative rounded-lg p-2 text-surface-500 hover:bg-surface-100 hover:text-surface-700"
      >
        <Bell size={18} />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute left-0 bottom-full z-50 mb-1 w-80 rounded-lg border border-surface-200 bg-white shadow-lg">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-surface-100 px-4 py-2.5">
              <h3 className="text-sm font-semibold text-surface-800">
                Notifications
              </h3>
              {unreadCount > 0 && (
                <button
                  onClick={() => markAllRead.mutate()}
                  className="flex items-center gap-1 rounded px-2 py-1 text-xs text-surface-500 hover:bg-surface-100 hover:text-surface-700"
                >
                  <CheckCheck size={12} />
                  Mark all read
                </button>
              )}
            </div>

            {/* Notification list */}
            <div className="max-h-[400px] overflow-y-auto">
              {isLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 size={20} className="animate-spin text-surface-400" />
                </div>
              ) : notifications.length === 0 ? (
                <div className="px-4 py-8 text-center">
                  <Bell size={24} className="mx-auto text-surface-300" />
                  <p className="mt-2 text-sm text-surface-400">
                    No notifications yet
                  </p>
                </div>
              ) : (
                <div>
                  {notifications.map((notif) => (
                    <button
                      key={notif.id}
                      onClick={() => handleNotificationClick(notif)}
                      className={`flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-surface-50 ${
                        !notif.read_at ? "bg-primary-50/30" : ""
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-surface-700 line-clamp-2">
                          {notif.title}
                        </p>
                        <div className="mt-0.5 flex items-center gap-2 text-xs text-surface-400">
                          <span>
                            {notificationTypeIcons[notif.type] ?? notif.type.replace(/_/g, " ")}
                          </span>
                          <span>{formatRelativeTime(notif.created_at)}</span>
                        </div>
                      </div>
                      {!notif.read_at && (
                        <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary-500" />
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
