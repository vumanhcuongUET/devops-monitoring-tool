/**
 * useApiFallback Hook
 *
 * Handles API errors and provides fallback UI state management.
 * Automatically detects API down scenarios and provides appropriate EmptyState components.
 *
 * Usage:
 * ```tsx
 * const { data, error, isLoading, isError, isApiDown } = useQuery({...});
 * const { fallbackComponent, handleRetry } = useApiFallback({
 *   error,
 *   isError,
 *   onRetry: () => refetch(),
 *   fallbackType: 'api-down'
 * });
 *
 * if (fallbackComponent) return fallbackComponent;
 * if (isLoading) return <LoadingSpinner />;
 * // ... render normal content
 * ```
 */

import { useMemo } from "react";
import { useQueryErrorResetBoundary } from "@tanstack/react-query";
import {
  EmptyState,
  ApiDownEmptyState,
  NoDataEmptyState,
  NoPermissionsEmptyState,
  SearchEmptyState,
} from "@/components/common";

interface UseApiFallbackOptions {
  /** Error object from query/mutation */
  error: unknown | null;
  /** Whether the query is in error state */
  isError: boolean;
  /** Whether there's no data (empty array) */
  isEmpty?: boolean;
  /** Optional retry callback */
  onRetry?: () => void;
  /** Override automatic fallback type detection */
  fallbackType?: "api-down" | "no-data" | "no-permissions" | "search-empty" | "generic";
  /** Custom title for empty state */
  title?: string;
  /** Custom description for empty state */
  description?: string;
}

interface UseApiFallbackReturn {
  /** Component to render as fallback, or null if no fallback needed */
  fallbackComponent: React.ReactNode | null;
  /** Whether to show fallback UI */
  shouldShowFallback: boolean;
  /** Detected fallback type */
  detectedType: "api-down" | "no-data" | "no-permissions" | "search-empty" | "generic" | null;
  /** Handle retry action */
  handleRetry: () => void;
}

/**
 * Detect if error is due to API being down/unreachable
 */
function isApiDownError(error: unknown): boolean {
  if (!error) return false;

  const errorObj = error as { message?: string; code?: string; status?: number };

  // Check for network/fetch errors
  const errorMessage = errorObj.message?.toLowerCase() || "";
  const isNetworkError =
    errorMessage.includes("fetch") ||
    errorMessage.includes("network") ||
    errorMessage.includes("connection") ||
    errorMessage.includes("econnrefused") ||
    errorMessage.includes("failed to fetch");

  // Check for specific HTTP status codes
  const isServiceUnavailable =
    errorObj.status === 503 ||
    errorObj.status === 502 ||
    errorObj.code === "SERVICE_UNAVAILABLE";

  // Check for timeout errors
  const isTimeout =
    errorMessage.includes("timeout") ||
    errorObj.code === "TIMEOUT" ||
    errorObj.status === 408;

  return isNetworkError || isServiceUnavailable || isTimeout;
}

/**
 * Detect if error is due to permissions
 */
function isPermissionError(error: unknown): boolean {
  if (!error) return false;

  const errorObj = error as { status?: number; code?: string; message?: string };

  return (
    errorObj.status === 401 ||
    errorObj.status === 403 ||
    errorObj.code === "PERMISSION_DENIED" ||
    errorObj.code === "UNAUTHORIZED" ||
    errorObj.message?.toLowerCase().includes("permission")
  );
}

/**
 * Hook for managing API fallback states
 */
export function useApiFallback({
  error,
  isError,
  isEmpty = false,
  onRetry,
  fallbackType,
  title,
  description,
}: UseApiFallbackOptions): UseApiFallbackReturn {
  const { reset } = useQueryErrorResetBoundary();

  const detectedType = useMemo(() => {
    if (fallbackType) return fallbackType;

    if (isEmpty && !isError) {
      return "no-data";
    }

    if (!isError || !error) {
      return null;
    }

    if (isPermissionError(error)) {
      return "no-permissions";
    }

    if (isApiDownError(error)) {
      return "api-down";
    }

    return "generic";
  }, [error, isError, isEmpty, fallbackType]);

  // Only show fallback if there's an actual error, or if isEmpty is explicitly requested
  // Empty arrays (isEmpty=true) are valid for many APIs (no alerts, etc.) - don't show fallback by default
  const shouldShowFallback = isError || (isEmpty && fallbackType === "no-data");

  const handleRetry = () => {
    reset();
    onRetry?.();
  };

  const fallbackComponent = useMemo(() => {
    if (!shouldShowFallback) {
      return null;
    }

    const type = detectedType || "generic";

    // Use specific components for common cases
    switch (type) {
      case "api-down":
        return <ApiDownEmptyState onRetry={onRetry ? handleRetry : undefined} />;
      case "no-data":
        return <NoDataEmptyState message={description} />;
      case "no-permissions":
        return <NoPermissionsEmptyState />;
      case "search-empty":
        return <SearchEmptyState />;
      default:
        return (
          <EmptyState
            type={type}
            title={title}
            description={description}
            action={
              onRetry
                ? { label: "Retry", onClick: handleRetry, variant: "primary" }
                : undefined
            }
          />
        );
    }
  }, [shouldShowFallback, detectedType, title, description, onRetry, handleRetry]);

  return {
    fallbackComponent,
    shouldShowFallback,
    detectedType,
    handleRetry,
  };
}

/**
 * Simpler hook for just checking if API is down
 */
export function useApiDownStatus(error: unknown | null): boolean {
  return useMemo(() => isApiDownError(error), [error]);
}
