import { useState, useEffect } from "react";
import api from "../api/client";

interface Skill {
  id: string;
  name: string;
  description: string;
  category: string;
  priority: string;
  enabled: boolean;
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
  const [skills, setSkills] = useState<Skill[]>([]);
  const [executions, setExecutions] = useState<SkillExecution[]>([]);
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null);
  const [project, setProject] = useState("meinvoice");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSkills();
    fetchExecutions();
  }, []);

  const fetchSkills = async () => {
    setLoading(true);
    try {
      const response = await api.get("/api/v1/skills");
      setSkills(response.data.skills || []);
    } catch (error) {
      console.error("Failed to fetch skills:", error);
    } finally {
      setLoading(false);
    }
  };

  const fetchExecutions = async () => {
    try {
      const response = await api.get("/api/v1/skills/executions?limit=20");
      setExecutions(response.data.executions || []);
    } catch (error) {
      console.error("Failed to fetch executions:", error);
    }
  };

  const executeSkill = async (skillId: string) => {
    try {
      await api.post(`/api/v1/skills/${skillId}/analyze`, {
        project: project,
        parameters: {},
      });
      fetchExecutions();
    } catch (error) {
      console.error("Failed to execute skill:", error);
    }
  };

  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      finops: "bg-green-100 text-green-800",
      security: "bg-red-100 text-red-800",
      capacity: "bg-blue-100 text-blue-800",
      devops: "bg-purple-100 text-purple-800",
      monitoring: "bg-yellow-100 text-yellow-800",
      reliability: "bg-indigo-100 text-indigo-800",
      compliance: "bg-pink-100 text-pink-800",
    };
    return colors[category] || "bg-gray-100 text-gray-800";
  };

  const getPriorityColor = (priority: string) => {
    const colors: Record<string, string> = {
      critical: "text-red-600",
      high: "text-orange-600",
      medium: "text-yellow-600",
      low: "text-green-600",
    };
    return colors[priority] || "text-gray-600";
  };

  if (loading) {
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
        {skills.map((skill) => (
          <div
            key={skill.id}
            className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow"
          >
            <div className="flex justify-between items-start mb-4">
              <h3 className="text-lg font-semibold">{skill.name}</h3>
              <span className={`px-2 py-1 rounded text-xs ${getCategoryColor(skill.category)}`}>
                {skill.category}
              </span>
            </div>
            <p className="text-gray-600 text-sm mb-4">{skill.description}</p>
            <div className="flex justify-between items-center">
              <span className={`text-sm font-medium ${getPriorityColor(skill.priority)}`}>
                {skill.priority}
              </span>
              {skill.enabled ? (
                <button
                  onClick={() => executeSkill(skill.id)}
                  className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                >
                  Execute
                </button>
              ) : (
                <span className="text-gray-400 text-sm">Disabled</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Recent Executions */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b">
          <h2 className="text-xl font-semibold">Recent Executions</h2>
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
