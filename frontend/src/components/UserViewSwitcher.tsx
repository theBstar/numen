import { useEffect, useState } from "react";
import { ChevronUp, ChevronDown, LogOut } from "lucide-react";
import { useOrgContext } from "@/contexts/OrgContext";
import { listMembers, logout } from "@/services/api";
import { useDemoFeatures } from "@/hooks/useDemoFeatures";
import type { OrgMember } from "@/types";
import { cn } from "@/lib/utils";

const ROLE_LABELS: Record<string, string> = {
  engineer: "Engineer",
  pm: "PM",
  em: "EM",
  cto: "CTO",
  vp_eng: "VP Eng",
  vp_product: "VP Product",
  designer: "Designer",
};

const ROLE_COLORS: Record<string, string> = {
  engineer: "bg-blue-100 text-blue-700",
  pm: "bg-purple-100 text-purple-700",
  em: "bg-amber-100 text-amber-700",
  cto: "bg-red-100 text-red-700",
  vp_eng: "bg-red-50 text-red-600",
  vp_product: "bg-purple-50 text-purple-600",
  designer: "bg-pink-100 text-pink-700",
};

const ROLE_ORDER = ["cto", "vp_eng", "vp_product", "em", "pm", "engineer", "designer"];

function getInitials(name: string | null): string {
  if (!name) return "?";
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

function getStoredUser(): { display_name?: string; email?: string; avatar_url?: string } {
  try { return JSON.parse(localStorage.getItem("numen_user") || "{}"); }
  catch { return {}; }
}

export function UserViewSwitcher() {
  const { orgId, memberEmail, setOrg, setMemberInfo, orgName, isDemo } = useOrgContext();
  const showSwitcher = useDemoFeatures("userViewSwitcher");
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!showSwitcher || !orgId) return;
    listMembers(orgId)
      .then((m) => {
        setMembers(m);
        // Auto-populate role from current member
        const current = m.find((mem) => mem.email === memberEmail);
        if (current) {
          setMemberInfo(current.role, current.id);
        }
      })
      .catch(() => {});
  }, [orgId, showSwitcher, memberEmail, setMemberInfo]);

  // For non-demo users, fetch their member info for role
  useEffect(() => {
    if (showSwitcher || !orgId || !memberEmail) return;
    listMembers(orgId)
      .then((m) => {
        const current = m.find((mem) => mem.email === memberEmail);
        if (current) {
          setMemberInfo(current.role, current.id);
        }
      })
      .catch(() => {});
  }, [orgId, showSwitcher, memberEmail, setMemberInfo]);

  // If not demo, show user details footer with logout
  if (!showSwitcher) {
    const storedUser = getStoredUser();
    const displayName = storedUser.display_name || memberEmail || "User";
    const email = storedUser.email || memberEmail || "";
    return (
      <div className="border-t border-surface-200">
        <div className="flex items-center">
          <div className="flex flex-1 items-center gap-2.5 px-4 py-3">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-100 text-xs font-bold text-primary-700">
              {getInitials(displayName)}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-surface-900">{displayName}</p>
              <p className="truncate text-[10px] text-surface-500">{email}</p>
            </div>
          </div>
          <button
            onClick={logout}
            className="mr-3 flex shrink-0 items-center rounded-md p-1.5 text-surface-400 transition-colors hover:bg-surface-100 hover:text-surface-600"
            title="Sign out"
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    );
  }

  const currentMember = members.find((m) => m.email === memberEmail);

  const grouped = ROLE_ORDER.reduce<Record<string, OrgMember[]>>((acc, role) => {
    const roleMembers = members.filter((m) => m.role === role);
    if (roleMembers.length > 0) acc[role] = roleMembers;
    return acc;
  }, {});

  return (
    <div className="border-t border-surface-200">
      {/* Expandable member list */}
      {open && (
        <div className="max-h-64 overflow-y-auto border-b border-surface-100 px-2 py-2">
          <p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-surface-400">
            View as different role
          </p>
          {Object.entries(grouped).map(([role, roleMembers]) => (
            <div key={role} className="mb-1">
              <p className="px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-surface-400">
                {ROLE_LABELS[role] || role}
              </p>
              {roleMembers.map((member) => (
                <button
                  key={member.id}
                  onClick={() => {
                    setOrg(orgId, member.email, orgName, isDemo);
                    setMemberInfo(member.role, member.id);
                    setOpen(false);
                  }}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors",
                    member.email === memberEmail
                      ? "bg-primary-50"
                      : "hover:bg-surface-50",
                  )}
                >
                  <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-100 text-[10px] font-bold text-surface-600">
                    {getInitials(member.display_name)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-surface-900">
                      {member.display_name || member.email}
                    </p>
                  </div>
                  <span
                    className={cn(
                      "shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-medium",
                      ROLE_COLORS[member.role] || "bg-surface-100 text-surface-600",
                    )}
                  >
                    {ROLE_LABELS[member.role] || member.role}
                  </span>
                  {member.email === memberEmail && (
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary-600" />
                  )}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Trigger button in sidebar footer */}
      <div className="flex items-center">
        <button
          onClick={() => setOpen(!open)}
          className="flex flex-1 items-center gap-2.5 px-4 py-3 text-left transition-colors hover:bg-surface-50"
        >
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-100 text-xs font-bold text-primary-700">
            {currentMember ? getInitials(currentMember.display_name) : "?"}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium text-surface-900">
              {currentMember?.display_name || "Select user"}
            </p>
            <p className="truncate text-[10px] text-surface-500">
              {currentMember ? ROLE_LABELS[currentMember.role] || currentMember.role : "Demo mode"}
            </p>
          </div>
          {open ? (
            <ChevronDown size={14} className="shrink-0 text-surface-400" />
          ) : (
            <ChevronUp size={14} className="shrink-0 text-surface-400" />
          )}
        </button>
        <button
          onClick={logout}
          className="mr-3 flex shrink-0 items-center rounded-md p-1.5 text-surface-400 transition-colors hover:bg-surface-100 hover:text-surface-600"
          title="Sign out"
        >
          <LogOut size={14} />
        </button>
      </div>
    </div>
  );
}
