import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { LoadingSkeleton } from "../components/common/LoadingSkeleton";
import { ErrorState } from "../components/common/ErrorState";

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

// Risk chips use the shared dark idiom (solid text on 10% tint) — same as ActionCard.
const RISK_COLORS: Record<string, string> = {
  critical: "text-red-500 bg-red-500/10 border-red-500/30",
  high: "text-orange-500 bg-orange-500/10 border-orange-500/30",
  medium: "text-yellow-500 bg-yellow-500/10 border-yellow-500/30",
  low: "text-blue-500 bg-blue-500/10 border-blue-500/30",
  safe: "text-emerald-500 bg-emerald-500/10 border-emerald-500/30",
};

function complianceColor(score: number): string {
  if (score >= 90) return "text-[var(--color-healthy)]";
  if (score >= 70) return "text-[var(--color-degraded)]";
  return "text-[var(--color-down)]";
}

export default function GovernanceDashboard() {
  const {
    data: permissions = {},
    isLoading: permLoading,
    isError: permError,
    refetch: refetchPermissions,
  } = useQuery({
    queryKey: ["governance-permissions"],
    queryFn: fetchPermissions,
    retry: 1,
  });
  const {
    data: compliance,
    isLoading: compLoading,
    isError: compError,
    refetch: refetchCompliance,
  } = useQuery({
    queryKey: ["governance-compliance"],
    queryFn: fetchCompliance,
    retry: 1,
  });
  const {
    data: audit = [],
    isLoading: auditLoading,
    isError: auditError,
    refetch: refetchAudit,
  } = useQuery({
    queryKey: ["governance-audit"],
    queryFn: fetchAudit,
    retry: 1,
  });

  const loading = permLoading || compLoading || auditLoading;

  // Permission matrix rows: union of permission names across environments
  const allPermissions = Array.from(
    new Set(Object.values(permissions).flatMap((p) => p.permissions || []))
  ).sort();

  if (loading) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">Governance</h2>
        <LoadingSkeleton />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Governance</h2>
        <p className="text-sm text-[var(--color-text-secondary)]">
          RBAC policies, compliance status, and audit events
        </p>
      </div>

      {/* Compliance Overview */}
      {compError ? (
        <ErrorState message="Failed to load compliance status" onRetry={() => refetchCompliance()} />
      ) : compliance && !compliance.error ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
            <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">Overall Compliance</h3>
            <span className={`text-4xl font-bold ${complianceColor(compliance.overall_score ?? 0)}`}>
              {compliance.overall_score ?? "—"}%
            </span>
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
            <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">Active Violations</h3>
            <span className={`text-4xl font-bold ${(compliance.violations_count ?? 0) > 0 ? "text-[var(--color-down)]" : "text-[var(--color-text-primary)]"}`}>
              {compliance.violations_count ?? 0}
            </span>
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
            <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">Compliance Categories</h3>
            <div className="space-y-2">
              {Object.entries(compliance.by_category || {}).map(([cat, score]) => (
                <div key={cat} className="flex justify-between text-sm">
                  <span className="capitalize text-[var(--color-text-secondary)]">{cat}</span>
                  <span className={`font-medium ${complianceColor(score as number)}`}>
                    {score}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      {/* RBAC Permission Matrix */}
      {permError ? (
        <ErrorState message="Failed to load permission matrix" onRetry={() => refetchPermissions()} />
      ) : (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)]">
          <div className="px-5 py-4 border-b border-[var(--color-border)]">
            <h3 className="font-semibold">Permission Matrix</h3>
          </div>
          <div className="p-5">
            <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
                    <th scope="col" className="px-4 py-3 text-left font-medium text-[var(--color-text-secondary)] uppercase text-xs">
                      Permission
                    </th>
                    {ENVIRONMENTS.map((env) => (
                      <th
                        key={env}
                        scope="col"
                        className="px-4 py-3 text-center font-medium text-[var(--color-text-secondary)] uppercase text-xs"
                      >
                        {env.charAt(0).toUpperCase() + env.slice(1)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {allPermissions.length === 0 ? (
                    <tr>
                      <td colSpan={ENVIRONMENTS.length + 1} className="px-4 py-8 text-center text-[var(--color-text-secondary)]">
                        No permissions configured
                      </td>
                    </tr>
                  ) : (
                    allPermissions.map((perm) => (
                      <tr key={perm} className="border-b border-[var(--color-border)] last:border-0 hover:bg-white/5">
                        <td className="px-4 py-3 whitespace-nowrap font-medium">{perm}</td>
                        {ENVIRONMENTS.map((env) => (
                          <td key={env} className="px-4 py-3 whitespace-nowrap text-center">
                            {permissions[env]?.permissions?.includes(perm) ? (
                              <span className="text-[var(--color-healthy)]" aria-label={`${perm} allowed in ${env}`}>✓</span>
                            ) : (
                              <span className="text-[var(--color-unknown)]" aria-label={`${perm} not allowed in ${env}`}>—</span>
                            )}
                          </td>
                        ))}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Recent Audit Events */}
      {auditError ? (
        <ErrorState message="Failed to load audit events" onRetry={() => refetchAudit()} />
      ) : (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)]">
          <div className="px-5 py-4 border-b border-[var(--color-border)]">
            <h3 className="font-semibold">Recent Audit Events</h3>
          </div>
          <div className="p-5">
            {audit.length === 0 ? (
              <p className="text-[var(--color-text-secondary)] text-center py-8">No audit events yet</p>
            ) : (
              <div className="space-y-3">
                {audit.map((entry, idx) => {
                  const riskClass = RISK_COLORS[entry.risk_level] ?? "text-[var(--color-text-secondary)] bg-white/5 border-[var(--color-border)]";
                  return (
                    <div
                      key={idx}
                      className={`p-4 rounded-lg border ${
                        entry.allowed
                          ? "border-[var(--color-healthy)]/30 bg-[var(--color-healthy)]/10"
                          : "border-[var(--color-down)]/30 bg-[var(--color-down)]/5"
                      }`}
                    >
                      <div className="flex justify-between items-start gap-4">
                        <div>
                          <p className="font-medium text-[var(--color-text-primary)]">
                            <span className={entry.allowed ? "text-[var(--color-healthy)]" : "text-[var(--color-down)]"}>
                              {entry.allowed ? "✓" : "✗"}
                            </span>{" "}
                            {entry.action}
                            {!entry.allowed && (
                              <span className="ml-2 text-sm font-normal text-[var(--color-text-secondary)]">
                                (denied — needs {entry.required_permission})
                              </span>
                            )}
                          </p>
                          <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                            {entry.environment}
                            {entry.project ? ` • ${entry.project}` : ""}
                            {` • risk: `}
                            <span className={`inline-block rounded border px-1.5 py-0.5 text-xs ${riskClass}`}>
                              {entry.risk_level}
                            </span>
                          </p>
                        </div>
                        <span className="text-sm text-[var(--color-text-secondary)] whitespace-nowrap">
                          {new Date(entry.timestamp).toLocaleString()}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
