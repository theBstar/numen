import { analytics } from "./index";

export const trackLoginStarted = (method: "google" = "google") =>
  analytics.track("auth.login_started", { method });

export const trackLoggedIn = (params: { memberId: string; orgId: string; isNewMember: boolean }) =>
  analytics.track("auth.logged_in", {
    member_id: params.memberId,
    org_id: params.orgId,
    is_new_member: params.isNewMember,
  });

export const trackLoggedOut = () => analytics.track("auth.logged_out");

export const trackBriefingViewed = (params: { briefingId: string; itemCount: number }) =>
  analytics.track("briefing.viewed", {
    briefing_id: params.briefingId,
    item_count: params.itemCount,
  });

export const trackTaskCreatedFE = (params: { taskId: string; projectId?: string | null }) =>
  analytics.track("task.created", {
    task_id: params.taskId,
    project_id: params.projectId ?? null,
    origin: "web",
  });

export const trackTaskStatusChangedFE = (params: {
  taskId: string;
  fromStatus: string;
  toStatus: string;
}) =>
  analytics.track("task.status_changed", {
    task_id: params.taskId,
    from_status: params.fromStatus,
    to_status: params.toStatus,
  });

export const trackChatMessageSent = (params: { messageLength: number; hasAttachments: boolean }) =>
  analytics.track("chat.message_sent", {
    message_length: params.messageLength,
    has_attachments: params.hasAttachments,
  });

export const trackApiRequestFailed = (params: { path: string; status: number; method: string }) =>
  analytics.track("error.api_request_failed", {
    path: params.path,
    status: params.status,
    method: params.method,
  });
