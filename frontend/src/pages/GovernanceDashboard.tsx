import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

interface PermissionSummary {
  environment: string;
  total_permissions: number;
  permissions: string[];
  risk_breakdown: Record<string, number>;
}

interface AuditEntry {
  timestamp: string;
  action: string;
  allowed: boolean;
  required_permission: string;
  risk_level: string;
  requires_approval?: boolean;
  environment: string;
  project?: string | null;
  user?: string | null;
}

interface ComplianceStatus {
  overall_score?: number;
  by_category?: Record<string, number>;
  violations_count?: number;
  status?: string;
  error?: string;
}

const ENVIRONMENTS = ["development", "staging", "production"] as const;

async function fetchPermissions(): Promise<Record<string, PermissionSummary>> {
  const resp = await api.get("/api/v1/governance/permissions");
  return resp.data.environments || {};
}

async function fetchCompliance(): Promise<ComplianceStatus> {
  const resp = await api.get("/api/v1/governance/compliance");
  return resp.data;
}

async function fetchAudit(): Promise<AuditEntry[]> {
  const resp = await api.get("/api/v1/governance/audit?limit=50");
  return resp.data.audit_log || [];
}

export default function GovernanceDashboard() {
  const { data: permissions = {}, isLoading: permLoading } = useQuery({
    queryKey: ["governance-permissions"],
    queryFn: fetchPermissions,
    retry: 1,
  });
  const { data: compliance, isLoading: compLoading } = useQuery({
    queryKey: ["governance-compliance"],
    queryFn: fetchCompliance,
    retry: 1,
  });
  const { data: audit = [], isLoading: auditLoading } = useQuery({
    queryKey: ["governance-audit"],
    queryFn: fetchAudit,
    retry: 1,
  });

  const loading = permLoading || compLoading || auditLoading;

  // Permission matrix rows: union of permission names across environments
  const allPermissions = Array.from(
    new Set(Object.values(permissions).flatMap((p) => p.permissions || []))
  ).sort();

  const getRiskColor = (risk: string) => {
    const colors: Record<string, string> = {
      critical: "bg-red-100 text-red-800 border-red-300",
      high: "bg-orange-100 text-orange-800 border-orange-300",
      medium: "bg-yellow-100 text-yellow-800 border-yellow-300",
      low: "bg-blue-100 text-blue-800 border-blue-300",
      safe: "bg-green-100 text-green-800 border-green-300",
    };
    return colors[risk] || "bg-gray-100 text-gray-800 border-gray-300";
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
          Monitor RBAC policies, compliance status, and audit events
        </p>
      </div>

      {/* Compliance Overview */}
      {compliance && !compliance.error && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold mb-2">Overall Compliance</h3>
            <div className="flex items-baseline">
              <span className={`text-4xl font-bold ${getComplianceColor(compliance.overall_score ?? 0)}`}>
                {compliance.overall_score ?? "—"}%
              </span>
            </div>
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold mb-2">Active Violations</h3>
            <span className="text-4xl font-bold text-red-600">
              {compliance.violations_count ?? 0}
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
                  {ENVIRONMENTS.map((env) => (
                    <th
                      key={env}
                      className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase"
                    >
                      {env.charAt(0).toUpperCase() + env.slice(1)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {allPermissions.map((perm) => (
                  <tr key={perm}>
                    <td className="px-4 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {perm}
                    </td>
                    {ENVIRONMENTS.map((env) => (
                      <td key={env} className="px-4 py-4 whitespace-nowrap text-center">
                        {permissions[env]?.permissions?.includes(perm) ? (
                          <span className="text-green-600">✓</span>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Recent Audit Events */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b">
          <h2 className="text-xl font-semibold">Recent Audit Events</h2>
        </div>
        <div className="p-6">
          {audit.length === 0 ? (
            <p className="text-gray-500 text-center py-8">No audit events yet</p>
          ) : (
            <div className="space-y-3">
              {audit.map((entry, idx) => (
                <div
                  key={idx}
                  className={`p-4 rounded-lg border ${
                    entry.allowed
                      ? "bg-green-50 text-green-800 border-green-300"
                      : getRiskColor(entry.risk_level)
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="font-medium">
                        {entry.allowed ? "✓" : "✗"} {entry.action}
                        {!entry.allowed && (
                          <span className="ml-2 text-sm font-normal opacity-75">
                            (denied — needs {entry.required_permission})
                          </span>
                        )}
                      </p>
                      <p className="text-sm opacity-75 mt-1">
                        {entry.environment}
                        {entry.project ? ` • ${entry.project}` : ""}
                        {` • risk: ${entry.risk_level}`}
                      </p>
                    </div>
                    <span className="text-sm opacity-75">
                      {new Date(entry.timestamp).toLocaleString()}
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
