/**
 * EmptyState Component - Fallback UI when API is down or no data available
 *
 * Usage:
 * - When API is unreachable
 * - When no data is available
 * - When user has no permissions
 * - When feature is not configured
 *
 * Example:
 * ```tsx
 * <EmptyState
 *   type="api-down"
 *   title="Unable to connect to server"
 *   description="Please check your connection and try again"
 *   action={{
 *     label: "Retry",
 *     onClick: () => window.location.reload()
 *   }}
 * />
 * ```
 */

import type { ReactNode } from "react";

export type EmptyStateType =
  | "api-down"           // API unreachable
  | "no-data"            // No data available
  | "no-permissions"     // User lacks permissions
  | "not-configured"     // Feature not configured
  | "search-empty"       // Search returned no results
  | "generic";           // Generic empty state

export interface EmptyStateProps {
  /** Type of empty state - determines icon and default messaging */
  type?: EmptyStateType;
  /** Main heading text */
  title?: string;
  /** Supporting description text */
  description?: string;
  /** Optional action button */
  action?: {
    label: string;
    onClick: () => void;
    variant?: "primary" | "secondary";
  };
  /** Optional additional content */
  children?: ReactNode;
  /** Optional custom icon (SVG component) */
  icon?: ReactNode;
  /** Size variant */
  size?: "small" | "medium" | "large";
  /** CSS className */
  className?: string;
}

const defaultConfig: Record<EmptyStateType, { title: string; description: string; icon: string }> = {
  "api-down": {
    title: "Unable to connect to server",
    description: "We couldn't reach the monitoring backend. Please check your connection or try again later.",
    icon: "🔌",
  },
  "no-data": {
    title: "No data available",
    description: "There's no data to display at the moment. This could be due to no active monitoring or a data collection issue.",
    icon: "📊",
  },
  "no-permissions": {
    title: "Access denied",
    description: "You don't have permission to view this data. Contact your administrator if you believe this is an error.",
    icon: "🔒",
  },
  "not-configured": {
    title: "Feature not configured",
    description: "This feature hasn't been set up yet. Please configure the necessary settings to enable it.",
    icon: "⚙️",
  },
  "search-empty": {
    title: "No results found",
    description: "We couldn't find anything matching your search. Try different keywords or filters.",
    icon: "🔍",
  },
  "generic": {
    title: "Nothing to show",
    description: "There's nothing to display right now.",
    icon: "📭",
  },
};

const sizeClasses = {
  small: "py-8 px-4",
  medium: "py-12 px-6",
  large: "py-20 px-8",
};

export function EmptyState({
  type = "generic",
  title,
  description,
  action,
  children,
  icon,
  size = "medium",
  className = "",
}: EmptyStateProps) {
  const config = defaultConfig[type];
  const displayTitle = title ?? config.title;
  const displayDescription = description ?? config.description;
  const displayIcon = icon ?? config.icon;

  return (
    <div
      className={`
        flex flex-col items-center justify-center
        text-center
        bg-slate-900/50
        rounded-lg border border-slate-700
        ${sizeClasses[size]}
        ${className}
      `}
      data-testid="empty-state"
      data-type={type}
    >
      {/* Icon */}
      <div className="text-5xl mb-4 opacity-70">{displayIcon}</div>

      {/* Title */}
      <h3 className="text-lg font-semibold text-slate-100 mb-2">
        {displayTitle}
      </h3>

      {/* Description */}
      <p className="text-sm text-slate-400 max-w-md mb-6">
        {displayDescription}
      </p>

      {/* Action Button */}
      {action && (
        <button
          onClick={action.onClick}
          className={`
            px-4 py-2 rounded-lg font-medium text-sm
            transition-colors duration-200
            ${
              action.variant === "secondary"
                ? "bg-slate-700 text-slate-100 hover:bg-slate-600"
                : "bg-blue-600 text-white hover:bg-blue-700"
            }
          `}
          data-testid="empty-state-action"
        >
          {action.label}
        </button>
      )}

      {/* Additional Content */}
      {children && (
        <div className="mt-6" data-testid="empty-state-children">
          {children}
        </div>
      )}
    </div>
  );
}

/**
 * API Down Empty State - Shortcut for API unreachable scenario
 */
export function ApiDownEmptyState({ onRetry }: { onRetry?: () => void }) {
  return (
    <EmptyState
      type="api-down"
      action={
        onRetry
          ? { label: "Retry Connection", onClick: onRetry, variant: "primary" }
          : undefined
      }
    />
  );
}

/**
 * No Data Empty State - Shortcut for no data scenario
 */
export function NoDataEmptyState({ message }: { message?: string }) {
  return <EmptyState type="no-data" description={message} />;
}

/**
 * No Permissions Empty State - Shortcut for access denied scenario
 */
export function NoPermissionsEmptyState() {
  return <EmptyState type="no-permissions" />;
}

/**
 * Search Empty State - Shortcut for no search results
 */
export function SearchEmptyState({ searchTerm }: { searchTerm?: string }) {
  return (
    <EmptyState
      type="search-empty"
      description={
        searchTerm
          ? `We couldn't find anything matching "${searchTerm}". Try different keywords or filters.`
          : undefined
      }
    />
  );
}
