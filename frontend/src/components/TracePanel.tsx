import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Database,
  GitBranch,
  BarChart3,
  Brain,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ---- Types ----

interface SourceInfo {
  name: string;
  type: "linear" | "github" | "slack" | "manual" | string;
  entityCount: number;
  lastSynced?: string;
}

interface GraphConnection {
  fromEntity: string;
  toEntity: string;
  edgeType: string;
  confidence: number;
}

interface ScoringFactor {
  name: string;
  weight: number;
  rawValue: number;
  contribution: number;
  explanation: string;
}

interface AIReasoning {
  model: string;
  promptTokens: number;
  completionTokens: number;
  summary: string;
}

interface TracePanelProps {
  sources?: SourceInfo[];
  connections?: GraphConnection[];
  scoringFactors?: ScoringFactor[];
  aiReasoning?: AIReasoning;
  className?: string;
}

// ---- Helpers ----

const sourceTypeColors: Record<string, string> = {
  linear: "bg-violet-100 text-violet-700",
  github: "bg-gray-100 text-gray-700",
  slack: "bg-emerald-100 text-emerald-700",
  manual: "bg-surface-100 text-surface-600",
};

function formatConfidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}

// ---- Component ----

export function TracePanel({
  sources = [],
  connections = [],
  scoringFactors = [],
  aiReasoning,
  className,
}: TracePanelProps) {
  const totalScore = scoringFactors.reduce((sum, f) => sum + f.contribution, 0);

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold text-surface-700">
          Recommendation Trace
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Accordion type="multiple" defaultValue={["sources"]}>
          {/* Sources Section */}
          {sources.length > 0 && (
            <AccordionItem value="sources">
              <div className="px-6">
                <AccordionTrigger>
                  <span className="flex items-center gap-2 text-sm">
                    <Database size={14} className="text-surface-500" />
                    Sources ({sources.length})
                  </span>
                </AccordionTrigger>
              </div>
              <AccordionContent>
                <div className="space-y-2 px-6">
                  {sources.map((source, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between rounded-lg border border-surface-100 px-3 py-2"
                    >
                      <div className="flex items-center gap-2">
                        <Badge
                          className={cn(
                            "text-[10px]",
                            sourceTypeColors[source.type] ?? sourceTypeColors.manual,
                          )}
                        >
                          {source.type}
                        </Badge>
                        <span className="text-sm text-surface-700">
                          {source.name}
                        </span>
                      </div>
                      <span className="text-xs text-surface-400">
                        {source.entityCount} entities
                      </span>
                    </div>
                  ))}
                </div>
              </AccordionContent>
            </AccordionItem>
          )}

          {/* Graph Connections Section */}
          {connections.length > 0 && (
            <AccordionItem value="connections">
              <div className="px-6">
                <AccordionTrigger>
                  <span className="flex items-center gap-2 text-sm">
                    <GitBranch size={14} className="text-surface-500" />
                    Graph Connections ({connections.length})
                  </span>
                </AccordionTrigger>
              </div>
              <AccordionContent>
                <div className="space-y-2 px-6">
                  {connections.map((conn, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 rounded-lg border border-surface-100 px-3 py-2 text-sm"
                    >
                      <span className="font-medium text-surface-700 truncate max-w-[120px]">
                        {conn.fromEntity}
                      </span>
                      <span className="shrink-0 rounded bg-surface-100 px-1.5 py-0.5 text-[10px] font-medium text-surface-500">
                        {conn.edgeType.replace(/_/g, " ")}
                      </span>
                      <span className="font-medium text-surface-700 truncate max-w-[120px]">
                        {conn.toEntity}
                      </span>
                      <span className="ml-auto shrink-0 text-xs text-surface-400">
                        {formatConfidence(conn.confidence)}
                      </span>
                    </div>
                  ))}
                </div>
              </AccordionContent>
            </AccordionItem>
          )}

          {/* Scoring Breakdown Section */}
          {scoringFactors.length > 0 && (
            <AccordionItem value="scoring">
              <div className="px-6">
                <AccordionTrigger>
                  <span className="flex items-center gap-2 text-sm">
                    <BarChart3 size={14} className="text-surface-500" />
                    Scoring Breakdown (total: {totalScore.toFixed(2)})
                  </span>
                </AccordionTrigger>
              </div>
              <AccordionContent>
                <div className="space-y-3 px-6">
                  {scoringFactors.map((factor, i) => (
                    <div key={i} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium text-surface-700">
                          {factor.name}
                        </span>
                        <span className="text-xs text-surface-500">
                          {factor.rawValue.toFixed(2)} x {factor.weight} = {factor.contribution.toFixed(2)}
                        </span>
                      </div>
                      <Progress
                        value={factor.contribution}
                        max={Math.max(totalScore, 1)}
                        className="h-1.5"
                      />
                      <p className="text-xs text-surface-400">
                        {factor.explanation}
                      </p>
                    </div>
                  ))}
                </div>
              </AccordionContent>
            </AccordionItem>
          )}

          {/* AI Reasoning Section */}
          {aiReasoning && (
            <AccordionItem value="ai">
              <div className="px-6">
                <AccordionTrigger>
                  <span className="flex items-center gap-2 text-sm">
                    <Brain size={14} className="text-surface-500" />
                    AI Reasoning
                  </span>
                </AccordionTrigger>
              </div>
              <AccordionContent>
                <div className="space-y-3 px-6">
                  <div className="flex items-center gap-3">
                    <Badge variant="secondary" className="text-[10px]">
                      {aiReasoning.model}
                    </Badge>
                    <span className="text-xs text-surface-400">
                      {aiReasoning.promptTokens} prompt / {aiReasoning.completionTokens} completion tokens
                    </span>
                  </div>
                  <p className="text-sm text-surface-600 leading-relaxed">
                    {aiReasoning.summary}
                  </p>
                </div>
              </AccordionContent>
            </AccordionItem>
          )}
        </Accordion>
      </CardContent>
    </Card>
  );
}
