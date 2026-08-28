import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Search, FolderKanban } from "lucide-react";
import { useProjects } from "@/hooks/queries";
import { useCreateProject } from "@/hooks/mutations";
import { ProjectCard } from "@/components/ProjectCard";
import { ProjectForm } from "@/components/ProjectForm";
import { EmptyState } from "@/components/EmptyState";
import type { ProjectCreateRequest, ProjectUpdateRequest } from "@/types";
import { cn } from "@/lib/utils";

type StatusFilter = "all" | "planning" | "active" | "paused" | "completed";

const statusTabs: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "planning", label: "Planning" },
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "completed", label: "Completed" },
];

export function Projects() {
  const navigate = useNavigate();
  const { data: projects, isPending: loading } = useProjects();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [search, setSearch] = useState("");
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  const createMutation = useCreateProject();

  // Filter logic
  const filtered = (projects ?? []).filter((p) => {
    const matchesStatus = statusFilter === "all" || p.status === statusFilter;
    const matchesSearch = p.name.toLowerCase().includes(search.toLowerCase());
    return matchesStatus && matchesSearch;
  });

  // Create handler - mutation invalidates ["projects"] on success, so no manual refetch.
  const handleCreate = async (data: ProjectCreateRequest | ProjectUpdateRequest) => {
    const result = await createMutation.mutateAsync(data as ProjectCreateRequest);
    if (result) {
      setShowCreateDialog(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-surface-900">Projects</h1>
          <p className="mt-1 text-sm text-surface-500">
            {(projects ?? []).length} project{(projects ?? []).length !== 1 ? "s" : ""}
          </p>
        </div>
        <button
          onClick={() => setShowCreateDialog(true)}
          className="flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 transition-colors"
        >
          <Plus size={16} />
          Create Project
        </button>
      </div>

      {/* Status filter tabs */}
      <div className="flex gap-2">
        {statusTabs.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setStatusFilter(tab.value)}
            className={cn(
              "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors border",
              statusFilter === tab.value
                ? "bg-primary-50 text-primary-700 border-primary-200"
                : "text-surface-600 hover:bg-surface-100 border-transparent",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Search bar */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" size={16} />
        <input
          type="text"
          placeholder="Search projects..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-lg border border-surface-200 bg-white py-2 pl-9 pr-4 text-sm placeholder:text-surface-400 focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100"
        />
      </div>

      {/* Content */}
      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-40 animate-pulse rounded-xl bg-surface-100" />
          ))}
        </div>
      ) : (projects ?? []).length === 0 ? (
        <EmptyState
          icon={FolderKanban}
          title="No projects yet"
          description="Create a project to organize work or connect Linear to import projects automatically."
          action={{ label: "Create Project", onClick: () => setShowCreateDialog(true) }}
          secondaryAction={{ label: "Connect your tools first", onClick: () => navigate("/connections") }}
        />
      ) : filtered.length === 0 ? (
        /* No projects match filters */
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <h3 className="text-lg font-semibold text-surface-900">No matching projects</h3>
          <p className="mt-1 text-sm text-surface-500">
            Try adjusting your filters or search term.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {filtered.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}

      {/* Create dialog */}
      <ProjectForm
        open={showCreateDialog}
        onClose={() => setShowCreateDialog(false)}
        onSubmit={handleCreate}
        loading={createMutation.isPending}
      />
    </div>
  );
}
