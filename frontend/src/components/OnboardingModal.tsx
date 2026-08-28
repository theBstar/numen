import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { completeOnboarding, setOrgContext } from "@/services/api";
import { useOrgContext } from "@/contexts/OrgContext";

const ROLE_OPTIONS = [
  { value: "engineer", label: "Engineer" },
  { value: "pm", label: "Product Manager" },
  { value: "em", label: "Engineering Manager" },
  { value: "designer", label: "Designer" },
  { value: "cto", label: "CTO" },
  { value: "vp_eng", label: "VP of Engineering" },
  { value: "vp_product", label: "VP of Product" },
];

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
}

function getStoredUser(): { display_name?: string; email?: string } {
  try {
    return JSON.parse(localStorage.getItem("numen_user") || "{}");
  } catch {
    return {};
  }
}

export function OnboardingModal() {
  const { setOrg } = useOrgContext();
  const storedUser = getStoredUser();
  const [step, setStep] = useState<1 | 2>(1);
  const [displayName, setDisplayName] = useState(storedUser.display_name || "");
  const [role, setRole] = useState("engineer");
  const [orgName, setOrgName] = useState("");
  const [orgSlug, setOrgSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleOrgNameChange(name: string) {
    setOrgName(name);
    if (!slugEdited) {
      setOrgSlug(slugify(name));
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!displayName.trim() || !orgName.trim() || !orgSlug.trim()) return;

    setSubmitting(true);
    setError(null);

    try {
      const result = await completeOnboarding({
        display_name: displayName.trim(),
        role,
        org_name: orgName.trim(),
        org_slug: orgSlug.trim(),
      });

      // Clear onboarding flag
      localStorage.removeItem("numen_needs_onboarding");

      // Set the new org context
      localStorage.setItem("numen_org_id", result.id);
      localStorage.setItem("numen_org_name", result.name);
      setOrgContext(result.id, "");
      setOrg(result.id, "", result.name, false);

      // Update stored orgs list
      const existingOrgs = JSON.parse(localStorage.getItem("numen_orgs") || "[]");
      existingOrgs.push({ id: result.id, name: result.name, slug: result.slug });
      localStorage.setItem("numen_orgs", JSON.stringify(existingOrgs));

      // Force reload to clear the modal
      window.location.href = "/dashboard";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to complete setup");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md px-4">
        {/* Logo */}
        <div className="mb-6 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary-600 text-lg font-bold text-white">
            N
          </div>
        </div>

        <Card className="shadow-2xl">
          <CardHeader>
            <CardTitle>{step === 1 ? "Welcome to Numen" : "Set up your organization"}</CardTitle>
            <CardDescription>
              {step === 1
                ? "Tell us a bit about yourself to get started."
                : "Create your organization to start connecting your tools."}
            </CardDescription>
            {/* Step indicator */}
            <div className="flex gap-2 pt-2">
              <div className={`h-1 flex-1 rounded-full ${step >= 1 ? "bg-primary-600" : "bg-surface-200"}`} />
              <div className={`h-1 flex-1 rounded-full ${step >= 2 ? "bg-primary-600" : "bg-surface-200"}`} />
            </div>
          </CardHeader>

          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-5">
              {step === 1 && (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="display-name">Your Name</Label>
                    <Input
                      id="display-name"
                      placeholder="Jane Smith"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      autoFocus
                      required
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="role">Your Role</Label>
                    <select
                      id="role"
                      value={role}
                      onChange={(e) => setRole(e.target.value)}
                      className="flex h-10 w-full rounded-md border border-surface-200 bg-white px-3 py-2 text-sm ring-offset-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
                      required
                    >
                      {ROLE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <Button
                    type="button"
                    className="w-full"
                    disabled={!displayName.trim()}
                    onClick={() => setStep(2)}
                  >
                    Continue
                  </Button>
                </>
              )}

              {step === 2 && (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="org-name">Organization Name</Label>
                    <Input
                      id="org-name"
                      placeholder="Acme Inc"
                      value={orgName}
                      onChange={(e) => handleOrgNameChange(e.target.value)}
                      autoFocus
                      required
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="org-slug">URL Slug</Label>
                    <Input
                      id="org-slug"
                      placeholder="acme-inc"
                      value={orgSlug}
                      onChange={(e) => {
                        setOrgSlug(e.target.value);
                        setSlugEdited(true);
                      }}
                      required
                    />
                    <p className="text-xs text-surface-400">
                      Lowercase letters, numbers, and hyphens only.
                    </p>
                  </div>

                  {error && (
                    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                      {error}
                    </div>
                  )}

                  <div className="flex gap-3">
                    <Button
                      type="button"
                      variant="outline"
                      className="flex-1"
                      onClick={() => setStep(1)}
                      disabled={submitting}
                    >
                      Back
                    </Button>
                    <Button
                      type="submit"
                      className="flex-1"
                      disabled={submitting || !orgName.trim() || !orgSlug.trim()}
                    >
                      {submitting ? "Creating..." : "Get Started"}
                    </Button>
                  </div>
                </>
              )}
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
