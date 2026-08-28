import { useEffect, useState } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, Plus } from "lucide-react";
import { useOrgContext } from "@/contexts/OrgContext";
import { listOrgs, listMembers, createOrg } from "@/services/api";
import type { Organization } from "@/types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
}

export function OrgSwitcher() {
  const { orgId, orgName, setOrg, isAdmin } = useOrgContext();
  const [orgs, setOrgs] = useState<Organization[]>(() => {
    try {
      return JSON.parse(localStorage.getItem("numen_orgs") || "[]");
    } catch { return []; }
  });
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [newOrgSlug, setNewOrgSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    listOrgs()
      .then((data) => {
        setOrgs(data);
        localStorage.setItem("numen_orgs", JSON.stringify(data));
        const first = data[0];
        if (!orgId && first) {
          selectOrg(first);
        }
      })
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function selectOrg(org: Organization) {
    let userEmail = "";
    try {
      userEmail = JSON.parse(localStorage.getItem("numen_user") || "{}").email || "";
    } catch { /* ignore */ }
    try {
      const members = await listMembers(org.id);
      const currentUserMember = members.find((m) => m.email === userEmail);
      setOrg(org.id, currentUserMember?.email || userEmail || members[0]?.email || "", org.name, org.is_demo);
    } catch {
      setOrg(org.id, userEmail, org.name, org.is_demo);
    }
  }

  function handleNameChange(name: string) {
    setNewOrgName(name);
    if (!slugEdited) {
      setNewOrgSlug(slugify(name));
    }
  }

  function handleSlugChange(slug: string) {
    setNewOrgSlug(slug);
    setSlugEdited(true);
  }

  async function handleCreateOrg(e: React.FormEvent) {
    e.preventDefault();
    if (!newOrgName.trim() || !newOrgSlug.trim()) return;

    setCreating(true);
    setCreateError(null);
    try {
      const result = await createOrg(newOrgName.trim(), newOrgSlug.trim());
      const newOrg: Organization = {
        id: result.id,
        name: newOrgName.trim(),
        slug: newOrgSlug.trim(),
        created_at: new Date().toISOString(),
      };
      setOrgs((prev) => [newOrg, ...prev]);
      setOrg(newOrg.id, "", newOrg.name);
      setShowCreateDialog(false);
      setNewOrgName("");
      setNewOrgSlug("");
      setSlugEdited(false);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create organization");
    } finally {
      setCreating(false);
    }
  }

  const currentOrg = orgs.find((o) => o.id === orgId);
  const displayName = currentOrg?.name || orgName || "Select Org";
  const initial = displayName[0]?.toUpperCase() || "N";

  // Non-admin: static org display (no dropdown, no chevron)
  if (!isAdmin) {
    return (
      <div className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-600 text-sm font-bold text-white">
          {initial}
        </div>
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-surface-900">
          {displayName}
        </span>
      </div>
    );
  }

  // Admin: full dropdown with org switching and create option
  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-surface-100 focus:outline-none">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-600 text-sm font-bold text-white">
              {initial}
            </div>
            <span className="min-w-0 flex-1 truncate text-sm font-semibold text-surface-900">
              {displayName}
            </span>
            <ChevronDown size={14} className="shrink-0 text-surface-400" />
          </button>
        </DropdownMenu.Trigger>

        <DropdownMenu.Portal>
          <DropdownMenu.Content
            className="z-50 min-w-[220px] rounded-lg border border-surface-200 bg-white p-1 shadow-lg"
            sideOffset={4}
            align="start"
          >
            <DropdownMenu.Label className="px-2 py-1.5 text-xs font-medium text-surface-500">
              Organizations
            </DropdownMenu.Label>
            {orgs.map((org) => (
              <DropdownMenu.Item
                key={org.id}
                className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm text-surface-700 outline-none hover:bg-surface-100 focus:bg-surface-100 data-[highlighted]:bg-surface-100"
                onSelect={() => selectOrg(org)}
              >
                <div className="flex h-6 w-6 items-center justify-center rounded bg-primary-100 text-xs font-bold text-primary-700">
                  {org.name[0]?.toUpperCase()}
                </div>
                <span className="flex-1 truncate">{org.name}</span>
                {org.is_demo && (
                  <span className="shrink-0 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                    Demo
                  </span>
                )}
                {org.id === orgId && (
                  <span className="h-2 w-2 rounded-full bg-primary-600" />
                )}
              </DropdownMenu.Item>
            ))}
            <DropdownMenu.Separator className="my-1 h-px bg-surface-200" />
            <DropdownMenu.Item
              className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm text-surface-600 outline-none hover:bg-surface-100 focus:bg-surface-100 data-[highlighted]:bg-surface-100"
              onSelect={() => setShowCreateDialog(true)}
            >
              <div className="flex h-6 w-6 items-center justify-center rounded border border-dashed border-surface-300 text-surface-400">
                <Plus size={14} />
              </div>
              <span>Create Organization</span>
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Organization</DialogTitle>
            <DialogDescription>
              Set up a new organization to start tracking your team's work.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleCreateOrg} className="space-y-4 mt-4">
            <div className="space-y-2">
              <Label htmlFor="org-name">Organization name</Label>
              <Input
                id="org-name"
                placeholder="Acme Inc"
                value={newOrgName}
                onChange={(e) => handleNameChange(e.target.value)}
                autoFocus
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="org-slug">Slug</Label>
              <Input
                id="org-slug"
                placeholder="acme-inc"
                value={newOrgSlug}
                onChange={(e) => handleSlugChange(e.target.value)}
                required
              />
              <p className="text-xs text-surface-400">
                Used in URLs. Lowercase letters, numbers, and hyphens only.
              </p>
            </div>

            {createError && (
              <p className="text-sm text-red-600">{createError}</p>
            )}

            <DialogFooter className="pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setShowCreateDialog(false)}
                disabled={creating}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={creating || !newOrgName.trim() || !newOrgSlug.trim()}>
                {creating ? "Creating..." : "Create Organization"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
