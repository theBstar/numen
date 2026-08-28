import { useState, useEffect } from "react";
import { useOrgContext } from "@/contexts/OrgContext";
import { useConnectors } from "@/hooks/queries";
import { getOrg, listMembers, sendTestBriefing, updateMember } from "@/services/api";
import { RoleType } from "@/types";
import type { OrgMember } from "@/types";

const roles = [
  { value: RoleType.ENGINEER, label: "Engineer" },
  { value: RoleType.PM, label: "Product Manager" },
  { value: RoleType.EM, label: "Engineering Manager" },
  { value: RoleType.CTO, label: "CTO" },
  { value: RoleType.VP_ENG, label: "VP Engineering" },
  { value: RoleType.VP_PRODUCT, label: "VP Product" },
  { value: RoleType.DESIGNER, label: "Designer" },
];

const timezones = [
  "America/Los_Angeles",
  "America/Denver",
  "America/Chicago",
  "America/New_York",
  "Europe/London",
  "Europe/Berlin",
  "Asia/Kolkata",
  "Asia/Tokyo",
];

function formatHourLabel(hour: number): string {
  if (hour === 0) return "12:00 AM";
  if (hour === 12) return "12:00 PM";
  if (hour < 12) return `${hour}:00 AM`;
  return `${hour - 12}:00 PM`;
}

const hourOptions = Array.from({ length: 24 }, (_, h) => ({
  value: h,
  label: formatHourLabel(h),
}));

function getStoredUser(): { display_name?: string; email?: string } {
  try { return JSON.parse(localStorage.getItem("numen_user") || "{}"); }
  catch { return {}; }
}

export function Settings() {
  const { orgId, orgName } = useOrgContext();
  const storedUser = getStoredUser();
  const { data: connectors } = useConnectors();
  const slackStatus = connectors?.find((c) => c.connector === "slack");
  const slackConnected = !!slackStatus?.connected;
  const slackNeedsReauth = !!slackStatus?.needs_reauth;
  const [orgSlug, setOrgSlug] = useState("");
  const [currentMember, setCurrentMember] = useState<OrgMember | null>(null);
  const [role, setRole] = useState<RoleType>(RoleType.ENGINEER);
  const [timezone, setTimezone] = useState("America/Los_Angeles");
  const [briefingHour, setBriefingHour] = useState<number>(8);
  const [briefingChannel, setBriefingChannel] = useState<"email" | "slack">(
    "email",
  );
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => {
    if (!orgId) return;
    getOrg(orgId)
      .then((org) => setOrgSlug((org as { slug?: string }).slug || ""))
      .catch(() => {});

    // Load current member to get their actual role and timezone
    const email = storedUser.email || localStorage.getItem("numen_email") || "";
    listMembers(orgId)
      .then((members) => {
        const me = members.find((m) => m.email === email);
        if (me) {
          setCurrentMember(me);
          setRole(me.role);
          setTimezone(me.timezone);
          setBriefingHour(me.briefing_hour ?? 8);
          setBriefingChannel(me.briefing_channel ?? "email");
        }
      })
      .catch(() => {});
  }, [orgId]); // eslint-disable-line react-hooks/exhaustive-deps

  // If Slack disconnects after the user picked it, fall back to email so
  // the next save doesn't get rejected by the backend.
  useEffect(() => {
    if (!slackConnected && briefingChannel === "slack") {
      setBriefingChannel("email");
    }
  }, [slackConnected, briefingChannel]);

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await sendTestBriefing();
      setTestResult({ ok: result.delivered, message: result.message });
    } catch (err: unknown) {
      setTestResult({
        ok: false,
        message: err instanceof Error ? err.message : "Test send failed",
      });
    } finally {
      setTesting(false);
      setTimeout(() => setTestResult(null), 8000);
    }
  }

  async function handleSave() {
    if (!currentMember) {
      setError("Could not find your member record");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const updated = await updateMember(currentMember.id, {
        role,
        timezone,
        briefing_hour: briefingHour,
        briefing_channel: briefingChannel,
      });
      setCurrentMember(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-surface-900">Settings</h1>
        <p className="mt-1 text-surface-500">
          Customize how Numen generates your briefings.
        </p>
      </div>

      <div className="max-w-xl space-y-6">
        {/* Profile */}
        <div className="card space-y-4">
          <h2 className="font-semibold text-surface-900">Profile</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-xs text-surface-500 mb-1">Name</p>
              <p className="text-sm font-medium text-surface-900">
                {storedUser.display_name || "Not set"}
              </p>
            </div>
            <div>
              <p className="text-xs text-surface-500 mb-1">Email</p>
              <p className="text-sm font-medium text-surface-900">
                {storedUser.email || "Not set"}
              </p>
            </div>
          </div>
        </div>

        {/* Organization */}
        <div className="card space-y-4">
          <h2 className="font-semibold text-surface-900">Organization</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-xs text-surface-500 mb-1">Name</p>
              <p className="text-sm font-medium text-surface-900">
                {orgName || "Not set"}
              </p>
            </div>
            <div>
              <p className="text-xs text-surface-500 mb-1">Slug</p>
              <p className="text-sm font-medium text-surface-900">
                {orgSlug || "..."}
              </p>
            </div>
          </div>
        </div>

        {/* Role */}
        <div className="card space-y-4">
          <h2 className="font-semibold text-surface-900">Role</h2>
          <p className="text-sm text-surface-500">
            Your role determines how briefings are prioritized and which
            insights are surfaced first.
          </p>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as typeof role)}
            className="w-full rounded-lg border border-surface-200 bg-white px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
          >
            {roles.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </div>

        {/* Timezone */}
        <div className="card space-y-4">
          <h2 className="font-semibold text-surface-900">Timezone</h2>
          <p className="text-sm text-surface-500">
            Controls when your daily briefing is generated.
          </p>
          <select
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            className="w-full rounded-lg border border-surface-200 bg-white px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
          >
            {timezones.map((tz) => (
              <option key={tz} value={tz}>
                {tz.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>

        {/* Briefing delivery */}
        <div className="card space-y-4">
          <h2 className="font-semibold text-surface-900">Briefing delivery</h2>
          <p className="text-sm text-surface-500">
            Choose how and when your daily briefing arrives. Slack delivery
            requires the Slack connector.
          </p>

          <div className="space-y-2">
            <p className="text-xs font-medium text-surface-700">Channel</p>
            <div className="space-y-2">
              <label className="flex items-center gap-3">
                <input
                  type="radio"
                  name="briefing-channel"
                  value="email"
                  checked={briefingChannel === "email"}
                  onChange={() => setBriefingChannel("email")}
                  className="h-4 w-4 border-surface-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-surface-700">Email</span>
              </label>
              <label
                className={`flex items-center gap-3 ${
                  slackConnected ? "" : "opacity-60"
                }`}
              >
                <input
                  type="radio"
                  name="briefing-channel"
                  value="slack"
                  checked={briefingChannel === "slack"}
                  onChange={() => setBriefingChannel("slack")}
                  disabled={!slackConnected}
                  className="h-4 w-4 border-surface-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-surface-700">
                  Slack direct message
                </span>
              </label>
            </div>
            {!slackConnected && (
              <p className="text-xs text-surface-500">
                Connect Slack on the Connections page to enable Slack delivery.
              </p>
            )}
            {slackConnected && slackNeedsReauth && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                Your Slack connection is missing the permissions needed to send
                briefing DMs. Reconnect Slack on the{" "}
                <a
                  href="/connections/slack"
                  className="font-medium underline hover:text-amber-900"
                >
                  Connections page
                </a>{" "}
                to fix this.
              </div>
            )}
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium text-surface-700">
              Delivery time
            </p>
            <select
              value={briefingHour}
              onChange={(e) => setBriefingHour(parseInt(e.target.value, 10))}
              className="w-full rounded-lg border border-surface-200 bg-white px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
            >
              {hourOptions.map((h) => (
                <option key={h.value} value={h.value}>
                  {h.label}
                </option>
              ))}
            </select>
            <p className="text-xs text-surface-500">
              Your local time ({timezone.replace(/_/g, " ")}).
            </p>
          </div>

          {currentMember && (
            <div className="space-y-2 border-t border-surface-100 pt-4">
              {(() => {
                const savedChannel = currentMember.briefing_channel ?? "email";
                const channelChanged = briefingChannel !== savedChannel;
                const buttonLabel = testing
                  ? "Sending test..."
                  : `Send test briefing via ${
                      savedChannel === "slack" ? "Slack" : "Email"
                    }`;
                return (
                  <>
                    <button
                      onClick={handleTest}
                      disabled={testing || channelChanged}
                      title={
                        channelChanged
                          ? "Save your channel choice first"
                          : undefined
                      }
                      className="btn-secondary w-full disabled:opacity-50"
                    >
                      {buttonLabel}
                    </button>
                    {channelChanged && (
                      <p className="text-xs text-surface-500">
                        Save your channel choice first to enable the test send.
                      </p>
                    )}
                    {testResult && (
                      <p
                        className={`text-xs ${
                          testResult.ok ? "text-green-700" : "text-red-600"
                        }`}
                      >
                        {testResult.message}
                      </p>
                    )}
                  </>
                );
              })()}
            </div>
          )}
        </div>

        {/* Save */}
        <div className="flex items-center gap-3">
          <button onClick={handleSave} disabled={saving} className="btn-primary disabled:opacity-50">
            {saving ? "Saving..." : "Save Settings"}
          </button>
          {saved && (
            <span className="text-sm text-green-600">Settings saved!</span>
          )}
          {error && (
            <span className="text-sm text-red-600">{error}</span>
          )}
        </div>
      </div>
    </div>
  );
}
