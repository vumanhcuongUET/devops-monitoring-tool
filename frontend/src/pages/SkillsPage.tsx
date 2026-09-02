import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "react-hot-toast";
import { api } from "../api/client";
import { LoadingSkeleton } from "../components/common/LoadingSkeleton";
import { ErrorState } from "../components/common/ErrorState";

interface Skill {
  id: string;
  name: string;
  description: string;
  category: string;
  priority: string;
  enabled: boolean;
  implemented: boolean;
  version?: string;
}

interface Recommendation {
  title: string;
  description: string;
  priority: string;
  action_type: string;
  estimated_effort?: string;
  risk_level: string;
  commands: string[];
}

interface SkillExecution {
  id: string;
  skill_id: string;
  project: string;
  status: "pending" | "running" | "completed" | "failed";
  timestamp: string;
  duration_seconds?: number;
}

// Priority chips use the shared dark idiom (solid text on 10% tint).
const PRIORITY_COLORS: Record<string, string> = {
  critical: "text-red-500 bg-red-500/10",
  high: "text-orange-500 bg-orange-500/10",
  medium: "text-yellow-500 bg-yellow-500/10",
  low: "text-emerald-500 bg-emerald-500/10",
};

const STATUS_COLORS: Record<string, string> = {
  completed: "bg-[var(--color-healthy)]/10 text-[var(--color-healthy)]",
  failed: "bg-[var(--color-down)]/10 text-[var(--color-down)]",
  running: "bg-[var(--color-degraded)]/10 text-[var(--color-degraded)]",
  pending: "bg-white/10 text-[var(--color-text-secondary)]",
};

export default function SkillsPage() {
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null);
  const [project, setProject] = useState("meinvoice");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [showParameters, setShowParameters] = useState(false);
  const [parameters, setParameters] = useState("{}");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);

  const {
    data: skills = [],
    isLoading: skillsLoading,
    isError: skillsError,
    refetch: refetchSkills,
  } = useQuery({
    queryKey: ["skills"],
    queryFn: async (): Promise<Skill[]> => {
      const response = await api.get("/api/v1/skills/");
      return response.data.skills || [];
    },
    retry: 1,
  });

  const {
    data: executions = [],
    refetch: refetchExecutions,
  } = useQuery({
    queryKey: ["skill-executions"],
    queryFn: async (): Promise<SkillExecution[]> => {
      const response = await api.get("/api/v1/skills/executions?limit=20");
      return response.data.executions || [];
    },
    retry: 1,
  });

  const executeSkill = async (skillId: string) => {
    try {
      let params = {};
      if (parameters) {
        try {
          params = JSON.parse(parameters);
        } catch (jsonError) {
          toast.error("Invalid JSON in parameters: " + (jsonError instanceof SyntaxError ? jsonError.message : "Unknown error"));
          return;
        }
      }
      const response = await api.post(`/api/v1/skills/${skillId}/analyze`, {
        project: project,
        parameters: params,
      });
      refetchExecutions();
      toast.success(`Skill "${skillId}" execution started`);
      return response.data.execution_id;
    } catch (error) {
      console.error("Failed to execute skill:", error);
      toast.error("Failed to execute skill. Please try again.");
      throw error;
    }
  };

  const fetchRecommendations = async (skillId: string, executionId: string) => {
    try {
      const response = await api.get(
        `/api/v1/skills/${skillId}/recommendations/${executionId}?project=${project}`
      );
      setRecommendations(response.data.recommendations || []);
    } catch (error) {
      console.error("Failed to fetch recommendations:", error);
      toast.error("Failed to fetch recommendations");
    }
  };

  const filteredSkills = skills.filter((skill) =>
    categoryFilter === "all" ? true : skill.category === categoryFilter
  );

  const categories = Array.from(new Set(skills.map((s) => s.category))).sort();

  // Esc closes the parameters modal.
  useEffect(() => {
    if (!showParameters) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setShowParameters(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showParameters]);

  if (skillsLoading) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">Skills</h2>
        <LoadingSkeleton />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:justify-between md:items-center gap-4">
        <div>
          <h2 className="text-lg font-semibold">Skills</h2>
          <p className="text-sm text-[var(--color-text-secondary)]">
            Specialized analysis and optimization skills
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-3">
          <select
            aria-label="Filter skills by category"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2 text-sm"
          >
            <option value="all">All Categories</option>
            {categories.map((cat) => (
              <option key={cat} value={cat}>
                {cat.charAt(0).toUpperCase() + cat.slice(1)}
              </option>
            ))}
          </select>
          <input
            type="text"
            aria-label="Project name"
            value={project}
            onChange={(e) => setProject(e.target.value)}
            placeholder="Project name"
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2 text-sm"
          />
        </div>
      </div>

      {skillsError ? (
        <ErrorState message="Failed to load skills" onRetry={() => refetchSkills()} />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredSkills.map((skill) => (
            <div
              key={skill.id}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5 hover:shadow-lg transition-shadow"
            >
              <div className="flex justify-between items-start mb-3 gap-2">
                <h3 className="font-semibold">{skill.name}</h3>
                <div className="flex gap-1 shrink-0">
                  {!skill.implemented && (
                    <span className="px-2 py-1 rounded text-xs bg-[var(--color-degraded)]/10 text-[var(--color-degraded)]">
                      Coming soon
                    </span>
                  )}
                  <span className="px-2 py-1 rounded text-xs bg-[var(--color-accent)]/10 text-[var(--color-accent)]">
                    {skill.category}
                  </span>
                </div>
              </div>
              <p className="text-[var(--color-text-secondary)] text-sm mb-4">{skill.description}</p>
              <div className="flex justify-between items-center">
                <span className={`text-sm font-medium rounded px-2 py-0.5 ${PRIORITY_COLORS[skill.priority] ?? "bg-white/10 text-[var(--color-text-secondary)]"}`}>
                  {skill.priority}
                </span>
                {skill.enabled && skill.implemented ? (
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        setSelectedSkill(skill.id);
                        setShowParameters(true);
                      }}
                      className="px-3 py-2 rounded-lg border border-[var(--color-border)] bg-white/5 hover:bg-white/10 text-[var(--color-text-primary)] text-sm"
                    >
                      Params
                    </button>
                    <button
                      onClick={() => executeSkill(skill.id)}
                      className="px-4 py-2 rounded-lg bg-[var(--color-accent)] hover:opacity-90 text-white text-sm"
                    >
                      Execute
                    </button>
                  </div>
                ) : (
                  <span className="text-[var(--color-unknown)] text-sm">
                    {skill.implemented ? "Disabled" : "Not implemented"}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Parameters Modal */}
      {showParameters && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
          onClick={() => setShowParameters(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Skill parameters"
            className="w-full max-w-lg rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold mb-4">Skill Parameters</h3>
            <textarea
              autoFocus
              value={parameters}
              onChange={(e) => setParameters(e.target.value)}
              placeholder='{"time_range_hours": 1, "metrics": ["http_*"]}'
              className="w-full h-40 p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-primary)] font-mono text-sm text-[var(--color-text-primary)] focus:border-[var(--color-accent)] outline-none"
            />
            <div className="flex justify-end gap-3 mt-4">
              <button
                onClick={() => setShowParameters(false)}
                className="px-4 py-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-white/5 text-sm"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (selectedSkill) {
                    executeSkill(selectedSkill);
                  }
                  setShowParameters(false);
                }}
                className="px-4 py-2 rounded-lg bg-[var(--color-accent)] hover:opacity-90 text-white text-sm"
              >
                Execute
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Recommendations Panel */}
      {recommendations.length > 0 && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)]">
          <div className="px-5 py-4 border-b border-[var(--color-border)] flex justify-between items-center">
            <h3 className="font-semibold">Recommendations</h3>
            <button
              onClick={() => setRecommendations([])}
              className="text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            >
              Close
            </button>
          </div>
          <div className="p-5 space-y-4">
            {recommendations.map((rec, index) => (
              <div key={index} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <h4 className="font-semibold">{rec.title}</h4>
                  <span className={`px-2 py-0.5 rounded text-xs ${PRIORITY_COLORS[rec.priority] ?? "bg-white/10 text-[var(--color-text-secondary)]"}`}>
                    {rec.priority}
                  </span>
                  <span className="text-sm text-[var(--color-text-secondary)]">• {rec.action_type}</span>
                </div>
                <p className="text-[var(--color-text-secondary)] text-sm mb-2">{rec.description}</p>
                {rec.estimated_effort && (
                  <p className="text-sm text-[var(--color-text-secondary)]">Effort: {rec.estimated_effort}</p>
                )}
                {rec.commands.length > 0 && (
                  <div className="mt-2">
                    <p className="text-sm font-medium mb-1">Suggested commands:</p>
                    <ul className="space-y-1 text-sm">
                      {rec.commands.map((cmd, i) => (
                        <li key={i}>
                          <code className="font-mono text-xs bg-[var(--color-bg-primary)] border border-[var(--color-border)] px-1.5 py-0.5 rounded text-[var(--color-text-primary)] break-all">
                            {cmd}
                          </code>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Executions */}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)]">
        <div className="px-5 py-4 border-b border-[var(--color-border)] flex justify-between items-center">
          <h3 className="font-semibold">Recent Executions</h3>
          <span className="text-sm text-[var(--color-text-secondary)]">{filteredSkills.length} skills available</span>
        </div>
        <div className="p-5">
          {executions.length === 0 ? (
            <p className="text-[var(--color-text-secondary)] text-center py-8">No executions yet</p>
          ) : (
            <div className="space-y-3">
              {executions.map((execution) => (
                <div
                  key={execution.id}
                  className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)]"
                >
                  <div>
                    <p className="font-medium">{execution.skill_id}</p>
                    <p className="text-sm text-[var(--color-text-secondary)]">
                      {execution.project} • {new Date(execution.timestamp).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-4 flex-wrap">
                    <span className={`px-2 py-1 rounded text-xs ${STATUS_COLORS[execution.status] ?? STATUS_COLORS.pending}`}>
                      {execution.status}
                    </span>
                    {execution.duration_seconds && (
                      <span className="text-sm text-[var(--color-text-secondary)]">
                        {execution.duration_seconds.toFixed(2)}s
                      </span>
                    )}
                    {execution.status === "completed" && (
                      <button
                        onClick={() => {
                          setSelectedSkill(execution.skill_id);
                          fetchRecommendations(execution.skill_id, execution.id);
                        }}
                        className="px-3 py-1.5 rounded border border-[var(--color-border)] bg-white/5 hover:bg-white/10 text-[var(--color-text-primary)] text-sm"
                      >
                        Recommendations
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
