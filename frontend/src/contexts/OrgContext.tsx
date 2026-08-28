import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { setOrgContext, getOrg } from "@/services/api";

interface OrgContextValue {
  orgId: string;
  orgName: string;
  memberEmail: string;
  isDemo: boolean;
  isAdmin: boolean;
  role: string;
  memberId: string;
  setOrg: (orgId: string, email: string, orgName?: string, isDemo?: boolean) => void;
  setMemberInfo: (role: string, memberId: string) => void;
}

const OrgContext = createContext<OrgContextValue | null>(null);

export function OrgProvider({ children }: { children: ReactNode }) {
  const [orgId, setOrgId] = useState(() => localStorage.getItem("numen_org_id") || "");
  const [orgName, setOrgName] = useState(() => localStorage.getItem("numen_org_name") || "");
  const [memberEmail, setMemberEmail] = useState(() => {
    const stored = localStorage.getItem("numen_email");
    if (stored) return stored;
    try {
      const user = JSON.parse(localStorage.getItem("numen_user") || "{}");
      return user.email || "";
    } catch { return ""; }
  });
  const [isDemo, setIsDemo] = useState(() => localStorage.getItem("numen_is_demo") === "true");
  const [isAdmin] = useState(() => localStorage.getItem("numen_is_admin") === "true");
  const [role, setRole] = useState(() => localStorage.getItem("numen_role") || "engineer");
  const [memberId, setMemberId] = useState(() => localStorage.getItem("numen_member_id") || "");

  useEffect(() => {
    if (orgId && memberEmail) {
      setOrgContext(orgId, memberEmail);
    }
  }, [orgId, memberEmail]);

  // Sync isDemo from API on load (in case localStorage is stale)
  useEffect(() => {
    if (!orgId) return;
    getOrg(orgId)
      .then((org) => {
        const demo = !!(org as Record<string, unknown>).is_demo;
        setIsDemo(demo);
        localStorage.setItem("numen_is_demo", String(demo));
      })
      .catch(() => {});
  }, [orgId]);

  const setOrg = useCallback((id: string, email: string, name?: string, demo?: boolean) => {
    const effectiveEmail = email || (() => {
      try { return JSON.parse(localStorage.getItem("numen_user") || "{}").email || ""; }
      catch { return ""; }
    })();
    setOrgId(id);
    setMemberEmail(effectiveEmail);
    localStorage.setItem("numen_org_id", id);
    localStorage.setItem("numen_email", effectiveEmail);
    if (name) {
      setOrgName(name);
      localStorage.setItem("numen_org_name", name);
    }
    const demoValue = demo ?? false;
    setIsDemo(demoValue);
    localStorage.setItem("numen_is_demo", String(demoValue));
    setOrgContext(id, email);
  }, []);

  const setMemberInfo = useCallback((newRole: string, newMemberId: string) => {
    setRole(newRole);
    setMemberId(newMemberId);
    localStorage.setItem("numen_role", newRole);
    localStorage.setItem("numen_member_id", newMemberId);
  }, []);

  return (
    <OrgContext.Provider value={{ orgId, orgName, memberEmail, isDemo, isAdmin, role, memberId, setOrg, setMemberInfo }}>
      {children}
    </OrgContext.Provider>
  );
}

export function useOrgContext() {
  const ctx = useContext(OrgContext);
  if (!ctx) throw new Error("useOrgContext must be used within OrgProvider");
  return ctx;
}
