import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

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

export default function SkillsPage() {
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null);
  const [project, setProject] = useState("meinvoice");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [showParameters, setShowParameters] = useState(false);
  const [parameters, setParameters] = useState("{}");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);

  const { data: skills = [], isLoading: skillsLoading } = useQuery({
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
          alert("Invalid JSON in parameters: " + (jsonError instanceof SyntaxError ? jsonError.message : "Unknown error"));
          return;
        }
      }
      const response = await api.post(`/api/v1/skills/${skillId}/analyze`, {
        project: project,
        parameters: params,
      });
      refetchExecutions();
      return response.data.execution_id;
    } catch (error) {
      console.error("Failed to execute skill:", error);
      alert("Failed to execute skill. Please try again.");
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
    }
  };

  const filteredSkills = skills.filter((skill) =>
    categoryFilter === "all" ? true : skill.category === categoryFilter
  );

  const categories = Array.from(new Set(skills.map((s) => s.category))).sort();

  const getCategoryColor = (category: string) =>
    category === "security"
      ? "bg-red-100 text-red-800"
      : "bg-blue-100 text-blue-800";

  const getPriorityColor = (priority: string) => {
    const colors: Record<string, string> = {
      critical: "text-red-600",
      high: "text-orange-600",
      medium: "text-yellow-600",
      low: "text-green-600",
    };
    return colors[priority] || "text-gray-600";
  };

  if (skillsLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Skills Library</h1>
          <p className="text-gray-600 mt-1">
            Execute specialized skills for analysis and optimization
          </p>
        </div>
        <div className="flex gap-4">
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="px-4 py-2 border rounded-lg"
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
            value={project}
            onChange={(e) => setProject(e.target.value)}
            placeholder="Project name"
            className="px-4 py-2 border rounded-lg"
          />
        </div>
      </div>

      {/* Skills Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        {filteredSkills.map((skill) => (
          <div
            key={skill.id}
            className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow"
          >
            <div className="flex justify-between items-start mb-4">
              <h3 className="text-lg font-semibold">{skill.name}</h3>
              <div className="flex gap-1">
                {!skill.implemented && (
                  <span className="px-2 py-1 rounded text-xs bg-amber-100 text-amber-700">
                    Coming soon
                  </span>
                )}
                <span className={`px-2 py-1 rounded text-xs ${getCategoryColor(skill.category)}`}>
                  {skill.category}
                </span>
              </div>
            </div>
            <p className="text-gray-600 text-sm mb-4">{skill.description}</p>
            <div className="flex justify-between items-center">
              <span className={`text-sm font-medium ${getPriorityColor(skill.priority)}`}>
                {skill.priority}
              </span>
              {skill.enabled && skill.implemented ? (
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      setSelectedSkill(skill.id);
                      setShowParameters(true);
                    }}
                    className="px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm"
                  >
                    Params
                  </button>
                  <button
                    onClick={() => executeSkill(skill.id)}
                    className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                  >
                    Execute
                  </button>
                </div>
              ) : (
                <span className="text-gray-400 text-sm">
                  {skill.implemented ? "Disabled" : "Not implemented"}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Parameters Modal */}
      {showParameters && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-lg w-full">
            <h3 className="text-xl font-semibold mb-4">Skill Parameters</h3>
            <textarea
              value={parameters}
              onChange={(e) => setParameters(e.target.value)}
              placeholder='{"time_range_hours": 1, "metrics": ["http_*"]}'
              className="w-full h-40 p-3 border rounded-lg font-mono text-sm"
            />
            <div className="flex justify-end gap-4 mt-4">
              <button
                onClick={() => setShowParameters(false)}
                className="px-4 py-2 border rounded-lg hover:bg-gray-50"
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
                className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
              >
                Execute
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Recommendations Panel */}
      {recommendations.length > 0 && (
        <div className="bg-white rounded-lg shadow mb-8">
          <div className="px-6 py-4 border-b flex justify-between items-center">
            <h2 className="text-xl font-semibold">Recommendations</h2>
            <button
              onClick={() => setRecommendations([])}
              className="text-gray-500 hover:text-gray-700"
            >
              Close
            </button>
          </div>
          <div className="p-6 space-y-4">
            {recommendations.map((rec, index) => (
              <div key={index} className="border-l-4 border-blue-500 pl-4">
                <div className="flex items-center gap-2 mb-2">
                  <h4 className="font-semibold">{rec.title}</h4>
                  <span className={`px-2 py-1 rounded text-xs ${getPriorityColor(rec.priority)} bg-gray-100`}>
                    {rec.priority}
                  </span>
                  <span className="text-sm text-gray-500">• {rec.action_type}</span>
                </div>
                <p className="text-gray-600 text-sm mb-2">{rec.description}</p>
                {rec.estimated_effort && (
                  <p className="text-sm text-gray-500">Effort: {rec.estimated_effort}</p>
                )}
                {rec.commands.length > 0 && (
                  <div className="mt-2">
                    <p className="text-sm font-medium mb-1">Suggested commands:</p>
                    <ul className="list-disc list-inside text-sm text-gray-600">
                      {rec.commands.map((cmd, i) => (
                        <li key={i}><code className="bg-gray-100 px-1 rounded">{cmd}</code></li>
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
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b flex justify-between items-center">
          <h2 className="text-xl font-semibold">Recent Executions</h2>
          <span className="text-sm text-gray-500">{filteredSkills.length} skills available</span>
        </div>
        <div className="p-6">
          {executions.length === 0 ? (
            <p className="text-gray-500 text-center py-8">No executions yet</p>
          ) : (
            <div className="space-y-3">
              {executions.map((execution) => (
                <div
                  key={execution.id}
                  className="flex items-center justify-between p-4 bg-gray-50 rounded-lg"
                >
                  <div>
                    <p className="font-medium">{execution.skill_id}</p>
                    <p className="text-sm text-gray-600">
                      {execution.project} • {new Date(execution.timestamp).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-4">
                    <span
                      className={`px-2 py-1 rounded text-xs ${
                        execution.status === "completed"
                          ? "bg-green-100 text-green-800"
                          : execution.status === "failed"
                          ? "bg-red-100 text-red-800"
                          : "bg-yellow-100 text-yellow-800"
                      }`}
                    >
                      {execution.status}
                    </span>
                    {execution.duration_seconds && (
                      <span className="text-sm text-gray-600">
                        {execution.duration_seconds.toFixed(2)}s
                      </span>
                    )}
                    {execution.status === "completed" && (
                      <button
                        onClick={() => {
                          setSelectedSkill(execution.skill_id);
                          fetchRecommendations(execution.skill_id, execution.id);
                        }}
                        className="px-3 py-1 bg-blue-100 text-blue-700 rounded hover:bg-blue-200 text-sm"
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
