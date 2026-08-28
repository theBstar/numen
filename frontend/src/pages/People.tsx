import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge as FlowEdge,
  Position,
  MarkerType,
  Handle,
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Users, Plus, X, LayoutList, GitBranch, AlertTriangle, GitMerge } from "lucide-react";
import { Link } from "react-router-dom";
import { useOrgContext } from "@/contexts/OrgContext";
import { getOrgGraph, createPerson, getPersonResolutionCount, mergePeople } from "@/services/api";
import { EmptyState } from "@/components/EmptyState";
import type { Entity, Edge } from "@/types";
import { cn } from "@/lib/utils";

// ── Constants ──

const ROLE_COLORS: Record<string, string> = {
  engineer: "bg-blue-500",
  pm: "bg-purple-500",
  em: "bg-amber-500",
  cto: "bg-red-500",
  designer: "bg-pink-500",
  vp_eng: "bg-red-400",
  vp_product: "bg-purple-400",
};

const ROLE_LABELS: Record<string, string> = {
  engineer: "Engineer",
  pm: "PM",
  em: "EM",
  cto: "CTO",
  designer: "Designer",
  vp_eng: "VP Eng",
  vp_product: "VP Product",
};

const ROLE_BG: Record<string, string> = {
  engineer: "bg-blue-50 text-blue-700",
  pm: "bg-purple-50 text-purple-700",
  em: "bg-amber-50 text-amber-700",
  cto: "bg-red-50 text-red-700",
  designer: "bg-pink-50 text-pink-700",
  vp_eng: "bg-red-50 text-red-600",
  vp_product: "bg-purple-50 text-purple-600",
};

function getInitials(name: string): string {
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

// ── Custom Node ──

function PersonNode({ data }: { data: { person: Entity; onAddReport: (id: string) => void } }) {
  const { person, onAddReport } = data;
  const props = person.properties as Record<string, unknown>;
  const role = (props?.role as string) || "";
  const title = (props?.title as string) || "";

  return (
    <div className="group relative">
      <Handle type="target" position={Position.Top} className="!bg-surface-300 !w-2 !h-2" />

      <div className="flex w-56 flex-col items-center rounded-xl border border-surface-200 bg-white px-4 py-4 shadow-sm transition-shadow hover:shadow-md">
        <div
          className={cn(
            "flex h-12 w-12 items-center justify-center rounded-full text-sm font-bold text-white",
            ROLE_COLORS[role] || "bg-surface-400",
          )}
        >
          {getInitials(person.canonical_name)}
        </div>
        <div className="mt-2 text-center">
          <p className="text-sm font-semibold text-surface-900">{person.canonical_name}</p>
          {title && <p className="text-xs text-surface-500">{title}</p>}
          {role && (
            <span className="mt-1 inline-block rounded-full bg-surface-100 px-2 py-0.5 text-[10px] font-medium text-surface-600">
              {ROLE_LABELS[role] || role}
            </span>
          )}
        </div>

        <button
          onClick={(e) => {
            e.stopPropagation();
            onAddReport(person.id);
          }}
          className="mt-2 flex items-center gap-1 rounded-md border border-dashed border-surface-300 px-2 py-1 text-[10px] text-surface-400 opacity-0 transition-opacity hover:border-primary-400 hover:text-primary-600 group-hover:opacity-100"
          title="Add direct report"
        >
          <Plus size={10} />
          Add report
        </button>
      </div>

      <Handle type="source" position={Position.Bottom} className="!bg-surface-300 !w-2 !h-2" />
    </div>
  );
}

const nodeTypes = { person: PersonNode };

// ── Layout helpers ──

interface TreeNode {
  id: string;
  children: TreeNode[];
}

function buildTree(people: Entity[], edges: Edge[]): { roots: TreeNode[]; parentMap: Map<string, string> } {
  const parentMap = new Map<string, string>(); // child -> parent
  for (const edge of edges) {
    if (edge.type === "reports_to") {
      parentMap.set(edge.from_entity_id, edge.to_entity_id);
    }
  }

  const childrenMap = new Map<string, string[]>();
  for (const [child, parent] of parentMap) {
    if (!childrenMap.has(parent)) childrenMap.set(parent, []);
    childrenMap.get(parent)!.push(child);
  }

  const buildNode = (id: string): TreeNode => ({
    id,
    children: (childrenMap.get(id) || []).map(buildNode),
  });

  const childIds = new Set(parentMap.keys());
  const roots = people.filter((p) => !childIds.has(p.id)).map((p) => buildNode(p.id));

  return { roots, parentMap };
}

function layoutTree(
  roots: TreeNode[],
  people: Entity[],
  onAddReport: (id: string) => void,
): { nodes: Node[]; edges: FlowEdge[] } {
  const nodes: Node[] = [];
  const flowEdges: FlowEdge[] = [];
  const personMap = new Map(people.map((p) => [p.id, p]));

  const X_GAP = 280;
  const Y_GAP = 140;

  function subtreeWidth(node: TreeNode): number {
    if (node.children.length === 0) return 1;
    return node.children.reduce((sum, c) => sum + subtreeWidth(c), 0);
  }

  function layoutNode(node: TreeNode, x: number, y: number, parentId?: string) {
    const person = personMap.get(node.id);
    if (!person) return;

    nodes.push({
      id: node.id,
      type: "person",
      position: { x, y },
      data: { person, onAddReport },
    });

    if (parentId) {
      flowEdges.push({
        id: `${parentId}-${node.id}`,
        source: parentId,
        target: node.id,
        type: "smoothstep",
        style: { stroke: "#94a3b8", strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8", width: 12, height: 12 },
      });
    }

    if (node.children.length > 0) {
      const totalWidth = subtreeWidth(node);
      let currentX = x - ((totalWidth - 1) * X_GAP) / 2;

      for (const child of node.children) {
        const childWidth = subtreeWidth(child);
        const childX = currentX + ((childWidth - 1) * X_GAP) / 2;
        layoutNode(child, childX, y + Y_GAP, node.id);
        currentX += childWidth * X_GAP;
      }
    }
  }

  let rootX = 0;
  for (const root of roots) {
    const width = subtreeWidth(root);
    const centerX = rootX + ((width - 1) * X_GAP) / 2;
    layoutNode(root, centerX, 0);
    rootX += width * X_GAP + X_GAP;
  }

  return { nodes, edges: flowEdges };
}

// ── People List View ──

function PeopleListView({
  people,
  reportingEdges,
  onAddPerson: _onAddPerson,
}: {
  people: Entity[];
  reportingEdges: Edge[];
  onAddPerson: (managerId: string | null) => void;
}) {
  const navigate = useNavigate();
  const { parentMap } = useMemo(() => buildTree(people, reportingEdges), [people, reportingEdges]);
  const personMap = useMemo(() => new Map(people.map((p) => [p.id, p])), [people]);

  const sorted = useMemo(() => {
    const roleOrder = ["cto", "vp_eng", "vp_product", "em", "pm", "designer", "engineer"];
    return [...people].sort((a, b) => {
      const ra = roleOrder.indexOf((a.properties as Record<string, unknown>)?.role as string || "");
      const rb = roleOrder.indexOf((b.properties as Record<string, unknown>)?.role as string || "");
      return (ra === -1 ? 99 : ra) - (rb === -1 ? 99 : rb);
    });
  }, [people]);

  return (
    <div className="rounded-xl border border-surface-200 bg-white overflow-hidden">
      <table className="w-full">
        <thead>
          <tr className="border-b border-surface-100 bg-surface-50 text-left">
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-surface-500">Name</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-surface-500">Role</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-surface-500">Title</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-surface-500">Team</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-surface-500">Email</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-surface-500">Reports To</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((person) => {
            const props = person.properties as Record<string, unknown>;
            const role = (props?.role as string) || "";
            const title = (props?.title as string) || "";
            const team = (props?.team as string) || "";
            const email = (props?.email as string) || "";
            const managerId = parentMap.get(person.id);
            const manager = managerId ? personMap.get(managerId) : null;

            return (
              <tr
                key={person.id}
                className="border-b border-surface-50 transition-colors hover:bg-surface-50 cursor-pointer"
                onClick={() => navigate(`/people/${person.id}`)}
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div
                      className={cn(
                        "flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold text-white",
                        ROLE_COLORS[role] || "bg-surface-400",
                      )}
                    >
                      {getInitials(person.canonical_name)}
                    </div>
                    <span className="text-sm font-medium text-surface-900">{person.canonical_name}</span>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", ROLE_BG[role] || "bg-surface-100 text-surface-600")}>
                    {ROLE_LABELS[role] || role}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm text-surface-600">{title}</td>
                <td className="px-4 py-3 text-sm text-surface-600">{team}</td>
                <td className="px-4 py-3 text-sm text-surface-500">{email}</td>
                <td className="px-4 py-3 text-sm text-surface-600">{manager?.canonical_name || "-"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Add Person Dialog ──

function AddPersonDialog({
  people,
  managerId,
  onClose,
  onCreated,
}: {
  people: Entity[];
  managerId: string | null;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("engineer");
  const [title, setTitle] = useState("");
  const [selectedManagerId, setSelectedManagerId] = useState(managerId || "");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      await createPerson({
        name: name.trim(),
        email: email.trim() || undefined,
        role,
        title: title.trim() || undefined,
        manager_id: selectedManagerId || undefined,
      });
      onCreated();
      onClose();
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-surface-900">Add Person</h2>
          <button onClick={onClose} className="text-surface-400 hover:text-surface-600">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-surface-700">Name *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Jane Smith"
              className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm outline-none focus:border-primary-300 focus:ring-1 focus:ring-primary-300"
              autoFocus
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-surface-700">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="jane@company.com"
              className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm outline-none focus:border-primary-300 focus:ring-1 focus:ring-primary-300"
            />
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-sm font-medium text-surface-700">Role</label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm outline-none focus:border-primary-300 focus:ring-1 focus:ring-primary-300"
              >
                <option value="engineer">Engineer</option>
                <option value="pm">PM</option>
                <option value="em">EM</option>
                <option value="designer">Designer</option>
                <option value="cto">CTO</option>
                <option value="vp_eng">VP Eng</option>
                <option value="vp_product">VP Product</option>
              </select>
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-sm font-medium text-surface-700">Job Title</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Sr. Engineer"
                className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm outline-none focus:border-primary-300 focus:ring-1 focus:ring-primary-300"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-surface-700">Reports To</label>
            <select
              value={selectedManagerId}
              onChange={(e) => setSelectedManagerId(e.target.value)}
              className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm outline-none focus:border-primary-300 focus:ring-1 focus:ring-primary-300"
            >
              <option value="">None (top-level)</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.canonical_name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-surface-200 px-4 py-2 text-sm text-surface-600 hover:bg-surface-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!name.trim() || saving}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-40"
            >
              {saving ? "Adding..." : "Add Person"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Main Page ──

export function People() {
  const navigate = useNavigate();
  const { orgId } = useOrgContext();
  const [people, setPeople] = useState<Entity[]>([]);
  const [reportingEdges, setReportingEdges] = useState<Edge[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogManagerId, setDialogManagerId] = useState<string | null>(null);
  const [showDialog, setShowDialog] = useState(false);
  const [view, setView] = useState<"org" | "list">("list");

  const [pendingResolutions, setPendingResolutions] = useState(0);
  const [showMergeDialog, setShowMergeDialog] = useState(false);
  const [mergePrimary, setMergePrimary] = useState<string>("");
  const [mergeDuplicate, setMergeDuplicate] = useState<string>("");
  const [merging, setMerging] = useState(false);

  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<any>([]);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState<any>([]);

  const loadGraph = useCallback(async () => {
    if (!orgId) return;
    try {
      const [graph, resCount] = await Promise.all([
        getOrgGraph(),
        getPersonResolutionCount().catch(() => ({ pending: 0 })),
      ]);
      setPeople(graph.people);
      setReportingEdges(graph.edges);
      setPendingResolutions(resCount.pending);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  const handleAddReport = useCallback((managerId: string) => {
    setDialogManagerId(managerId);
    setShowDialog(true);
  }, []);

  // Compute layout whenever data changes
  useEffect(() => {
    if (people.length === 0) return;
    const { roots } = buildTree(people, reportingEdges);
    const { nodes, edges } = layoutTree(roots, people, handleAddReport);
    setFlowNodes(nodes);
    setFlowEdges(edges);
  }, [people, reportingEdges, handleAddReport, setFlowNodes, setFlowEdges]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-surface-900">People</h1>
          <p className="mt-1 text-surface-500">
            {people.length} team member{people.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* View toggle */}
          <div className="flex rounded-lg border border-surface-200 bg-white p-0.5">
            <button
              onClick={() => setView("list")}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                view === "list"
                  ? "bg-primary-50 text-primary-700"
                  : "text-surface-500 hover:text-surface-700",
              )}
            >
              <LayoutList size={14} />
              List
            </button>
            <button
              onClick={() => setView("org")}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                view === "org"
                  ? "bg-primary-50 text-primary-700"
                  : "text-surface-500 hover:text-surface-700",
              )}
            >
              <GitBranch size={14} />
              Org Chart
            </button>
          </div>

          <button
            onClick={() => setShowMergeDialog(true)}
            className="flex items-center gap-2 rounded-lg border border-surface-300 bg-white px-4 py-2 text-sm font-medium text-surface-700 hover:bg-surface-50"
          >
            <GitMerge size={16} />
            Merge People
          </button>
          <button
            onClick={() => {
              setDialogManagerId(null);
              setShowDialog(true);
            }}
            className="flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
          >
            <Plus size={16} />
            Add Person
          </button>
        </div>
      </div>

      {pendingResolutions > 0 && (
        <Link
          to="/people/resolutions"
          className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 hover:bg-amber-100 transition-colors"
        >
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <span>
            <strong>{pendingResolutions}</strong> potential duplicate{" "}
            {pendingResolutions === 1 ? "person" : "people"} detected after sync.
          </span>
          <span className="ml-auto text-amber-600 font-medium whitespace-nowrap">
            Review and resolve &rarr;
          </span>
        </Link>
      )}

      {loading ? (
        <div className="flex h-[500px] items-center justify-center rounded-xl border border-surface-200 bg-white">
          <p className="text-sm text-surface-400">Loading...</p>
        </div>
      ) : people.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No team members yet"
          description="Connect an integration to automatically import your team, or add people manually."
          action={{ label: "Go to Connections", onClick: () => navigate("/connections") }}
        />
      ) : view === "list" ? (
        <PeopleListView
          people={people}
          reportingEdges={reportingEdges}
          onAddPerson={(managerId) => {
            setDialogManagerId(managerId);
            setShowDialog(true);
          }}
        />
      ) : (
        <div className="h-[600px] overflow-hidden rounded-xl border border-surface-200 bg-white">
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            minZoom={0.3}
            maxZoom={1.5}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={24} size={1} color="#e2e8f0" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
      )}

      {showDialog && (
        <AddPersonDialog
          people={people}
          managerId={dialogManagerId}
          onClose={() => setShowDialog(false)}
          onCreated={loadGraph}
        />
      )}

      {showMergeDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-surface-900">Merge People</h2>
              <button onClick={() => setShowMergeDialog(false)} className="text-surface-400 hover:text-surface-600">
                <X size={18} />
              </button>
            </div>
            <p className="text-sm text-surface-500 mb-4">
              Select the person to keep (primary) and the duplicate to merge into them. The duplicate's connections will transfer to the primary.
            </p>
            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium text-surface-700 block mb-1">Keep this person (primary)</label>
                <select
                  value={mergePrimary}
                  onChange={(e) => setMergePrimary(e.target.value)}
                  className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
                >
                  <option value="">Select person...</option>
                  {people
                    .filter((p) => p.id !== mergeDuplicate)
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.canonical_name} ({p.source})
                      </option>
                    ))}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium text-surface-700 block mb-1">Merge this person (duplicate)</label>
                <select
                  value={mergeDuplicate}
                  onChange={(e) => setMergeDuplicate(e.target.value)}
                  className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
                >
                  <option value="">Select person...</option>
                  {people
                    .filter((p) => p.id !== mergePrimary)
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.canonical_name} ({p.source})
                      </option>
                    ))}
                </select>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setShowMergeDialog(false)}
                className="btn-secondary text-sm"
              >
                Cancel
              </button>
              <button
                disabled={!mergePrimary || !mergeDuplicate || merging}
                onClick={async () => {
                  setMerging(true);
                  try {
                    await mergePeople(mergePrimary, mergeDuplicate);
                    setShowMergeDialog(false);
                    setMergePrimary("");
                    setMergeDuplicate("");
                    loadGraph();
                  } catch (err) {
                    console.error("Merge failed:", err);
                  } finally {
                    setMerging(false);
                  }
                }}
                className="flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
              >
                <GitMerge size={14} />
                {merging ? "Merging..." : "Merge"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
