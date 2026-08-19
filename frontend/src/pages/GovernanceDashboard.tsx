import { useState, useEffect } from "react";
import api from "../api/client";

interface Permission {
  permission: string;
  allowed: boolean;
  environments: string[];
}

interface PolicyViolation {
  policy_id: string;
  description: string;
  severity: string;
  timestamp: string;
}

interface ComplianceStatus {
  overall_score: number;
  by_category: Record<string, number>;
  violations_count: number;
}

export default function GovernanceDashboard() {
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [violations, setViolations] = useState<PolicyViolation[]>([]);
  const [compliance, setCompliance] = useState<ComplianceStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchGovernanceData();
  }, []);

  const fetchGovernanceData = async () => {
    setLoading(true);
    try {
      const [permResp, violResp, compResp] = await Promise.all([
        api.get("/api/v1/governance/permissions"),
        api.get("/api/v1/governance/policy-violations"),
        api.get("/api/v1/governance/compliance"),
      ]);
      setPermissions(permResp.data.permissions || []);
      setViolations(violRespResp.data.violations || []);
      setCompliance(compResp.data);
    } catch (error) {
      console.error("Failed to fetch governance data:", error);
    } finally {
      setLoading(false);
    }
  };

  const getSeverityColor = (severity: string) => {
    const colors: Record<string, string> = {
      critical: "bg-red-100 text-red-800 border-red-300",
      high: "bg-orange-100 text-orange-800 border-orange-300",
      medium: "bg-yellow-100 text-yellow-800 border-yellow-300",
      low: "bg-blue-100 text-blue-800 border-blue-300",
    };
    return colors[severity] || "bg-gray-100 text-gray-800 border-gray-300";
  };

  const getComplianceColor = (score: number) => {
    if (score >= 90) return "text-green-600";
    if (score >= 70) return "text-yellow-600";
    return "text-red-600";
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
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Governance Dashboard</h1>
        <p className="text-gray-600 mt-1">
          Monitor RBAC policies, compliance status, and security violations
        </p>
      </div>

      {/* Compliance Overview */}
      {compliance && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold mb-2">Overall Compliance</h3>
            <div className="flex items-baseline">
              <span className={`text-4xl font-bold ${getComplianceColor(compliance.overall_score)}`}>
                {compliance.overall_score}%
              </span>
            </div>
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold mb-2">Active Violations</h3>
            <span className="text-4xl font-bold text-red-600">
              {compliance.violations_count}
            </span>
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold mb-2">Compliance Categories</h3>
            <div className="space-y-2">
              {Object.entries(compliance.by_category || {}).map(([cat, score]) => (
                <div key={cat} className="flex justify-between">
                  <span className="capitalize text-gray-600">{cat}</span>
                  <span className={`font-medium ${getComplianceColor(score as number)}`}>
                    {score}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* RBAC Permission Matrix */}
      <div className="bg-white rounded-lg shadow mb-8">
        <div className="px-6 py-4 border-b">
          <h2 className="text-xl font-semibold">Permission Matrix</h2>
        </div>
        <div className="p-6">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Permission
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                    Development
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                    Staging
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                    Production
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {permissions.map((perm, idx) => (
                  <tr key={idx}>
                    <td className="px-4 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {perm.permission}
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap text-center">
                      {perm.environments.includes("development") ? (
                        <span className="text-green-600">✓</span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap text-center">
                      {perm.environments.includes("staging") ? (
                        <span className="text-green-600">✓</span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap text-center">
                      {perm.environments.includes("production") ? (
                        <span className="text-green-600">✓</span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Policy Violations */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b">
          <h2 className="text-xl font-semibold">Recent Policy Violations</h2>
        </div>
        <div className="p-6">
          {violations.length === 0 ? (
            <p className="text-gray-500 text-center py-8">No recent violations</p>
          ) : (
            <div className="space-y-3">
              {violations.map((violation) => (
                <div
                  key={violation.policy_id}
                  className={`p-4 rounded-lg border ${getSeverityColor(violation.severity)}`}
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="font-medium">{violation.description}</p>
                      <p className="text-sm opacity-75 mt-1">
                        Policy: {violation.policy_id}
                      </p>
                    </div>
                    <span className="text-sm opacity-75">
                      {new Date(violation.timestamp).toLocaleString()}
                    </span>
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
