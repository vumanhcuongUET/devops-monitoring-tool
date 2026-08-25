/**
 * LLM Streaming Hook
 *
 * Phase 9 - Sprint 2 - Day 8
 * Purpose: Handle streaming responses from the LLM analyze endpoint
 *
 * Features:
 * - Token-by-token streaming display
 * - Error handling
 * - Abort capability for long-running requests
 * - Auto-retry on connection failure
 */

import { useState, useCallback, useRef } from 'react';

export interface LLMStreamOptions {
  /** Maximum time to wait for first token (ms) */
  firstTokenTimeout?: number;
  /** Maximum total request time (ms) */
  maxDuration?: number;
  /** Whether to retry on failure */
  retryOnError?: boolean;
  /** Number of retries */
  maxRetries?: number;
}

export interface LLMStreamState {
  response: string;
  isStreaming: boolean;
  error: string | null;
  progress: number;
}

export interface LLMStreamResult extends LLMStreamState {
  streamQuery: (project: string, question: string, options?: LLMStreamOptions) => Promise<void>;
  abort: () => void;
  reset: () => void;
}

/**
 * Hook for streaming LLM responses.
 *
 * @example
 * ```tsx
 * const { response, isStreaming, error, streamQuery, abort } = useLLMStream();
 *
 * <button onClick={() => streamQuery('meinvoice', 'Tình trạng hệ thống?')}>
 *   Analyze
 * </button>
 *
 * {isStreaming && <button onClick={abort}>Cancel</button>}
 *
 * <div>{response}</div>
 * {error && <div className="error">{error}</div>}
 * ```
 */
export function useLLMStream(): LLMStreamResult {
  const [state, setState] = useState<LLMStreamState>({
    response: '',
    isStreaming: false,
    error: null,
    progress: 0,
  });

  const abortControllerRef = useRef<AbortController | null>(null);
  const retryCountRef = useRef(0);

  const reset = useCallback(() => {
    setState({
      response: '',
      isStreaming: false,
      error: null,
      progress: 0,
    });
    retryCountRef.current = 0;
  }, []);

  const abort = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setState((prev) => ({
      ...prev,
      isStreaming: false,
      error: 'Request aborted by user',
    }));
  }, []);

  const streamQuery = useCallback(async (
    project: string,
    question: string,
    options: LLMStreamOptions = {}
  ): Promise<void> => {
    const {
      firstTokenTimeout = 10000,
      maxDuration = 120000,
      retryOnError = true,
      maxRetries = 3,
    } = options;

    // Reset state
    setState({
      response: '',
      isStreaming: true,
      error: null,
      progress: 0,
    });

    // Create abort controller
    abortControllerRef.current = new AbortController();

    // Track first token timeout
    let firstTokenReceived = false;
    const firstTokenTimer = setTimeout(() => {
      if (!firstTokenReceived && abortControllerRef.current?.signal.aborted === false) {
        abort();
        setState((prev) => ({
          ...prev,
          error: 'Timeout: No response received within ' + (firstTokenTimeout / 1000) + 's',
        }));
      }
    }, firstTokenTimeout);

    // Track max duration
    const maxDurationTimer = setTimeout(() => {
      if (abortControllerRef.current?.signal.aborted === false) {
        abort();
        setState((prev) => ({
          ...prev,
          error: 'Timeout: Request exceeded maximum duration',
        }));
      }
    }, maxDuration);

    try {
      const response = await fetch('/api/v1/analyze/simple-stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ project, question }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          break;
        }

        // Decode and split by newlines
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (!line.trim()) continue;

          try {
            const data = JSON.parse(line);

            if (data.type === 'token') {
              if (!firstTokenReceived) {
                firstTokenReceived = true;
                clearTimeout(firstTokenTimer);
              }

              setState((prev) => ({
                ...prev,
                response: prev.response + data.text,
                progress: prev.progress + 1,
              }));
            } else if (data.type === 'complete') {
              setState((prev) => ({
                ...prev,
                isStreaming: false,
              }));
              retryCountRef.current = 0; // Reset retry count on success
            } else if (data.type === 'error') {
              throw new Error(data.error || 'Unknown error');
            }
          } catch (parseError) {
            console.error('Failed to parse stream chunk:', line, parseError);
          }
        }
      }

      clearTimeout(maxDurationTimer);
    } catch (err) {
      clearTimeout(firstTokenTimer);
      clearTimeout(maxDurationTimer);

      const error = err as Error;

      // Check if aborted
      if (error.name === 'AbortError') {
        setState((prev) => ({
          ...prev,
          isStreaming: false,
          error: prev.error || 'Request aborted',
        }));
        return;
      }

      // Retry logic
      if (retryOnError && retryCountRef.current < maxRetries) {
        retryCountRef.current++;
        console.log(`Retrying stream query (attempt ${retryCountRef.current}/${maxRetries})...`);

        // Exponential backoff
        await new Promise((resolve) => setTimeout(resolve, Math.pow(2, retryCountRef.current) * 1000));

        return streamQuery(project, question, options);
      }

      setState((prev) => ({
        ...prev,
        isStreaming: false,
        error: error.message || 'Unknown error occurred',
      }));
    }
  }, []);

  return {
    ...state,
    streamQuery,
    abort,
    reset,
  };
}

/**
 * Hook for streaming full triage card analysis.
 */
export function useTriageStream() {
  const [state, setState] = useState<{
    triageCard: any;
    isStreaming: boolean;
    error: string | null;
  }>({
    triageCard: null,
    isStreaming: false,
    error: null,
  });

  const abortControllerRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setState((prev) => ({
      ...prev,
      isStreaming: false,
      error: 'Request aborted',
    }));
  }, []);

  const streamTriage = useCallback(async (request: {
    project: string;
    incident_id?: string;
    alert_message?: string;
    time_range_minutes?: number;
    include_recommendations?: boolean;
    severity_threshold?: string;
  }) => {
    setState({
      triageCard: null,
      isStreaming: true,
      error: null,
    });

    abortControllerRef.current = new AbortController();

    let fullResponse = '';

    try {
      const response = await fetch('/api/v1/analyze/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;

          try {
            const data = JSON.parse(line);

            if (data.type === 'token' && data.text) {
              fullResponse += data.text;
            } else if (data.type === 'complete') {
              // Try to parse as triage card
              try {
                const triageData = JSON.parse(fullResponse);
                setState({
                  triageCard: triageData,
                  isStreaming: false,
                  error: null,
                });
              } catch {
                // Not valid JSON, keep as text
                setState({
                  triageCard: { raw_response: fullResponse },
                  isStreaming: false,
                  error: null,
                });
              }
            } else if (data.type === 'error') {
              throw new Error(data.error || 'Unknown error');
            }
          } catch (parseError) {
            console.error('Failed to parse stream chunk:', line);
          }
        }
      }
    } catch (err) {
      const error = err as Error;
      if (error.name !== 'AbortError') {
        setState((prev) => ({
          ...prev,
          isStreaming: false,
          error: error.message,
        }));
      }
    }
  }, []);

  return {
    triageCard: state.triageCard,
    isStreaming: state.isStreaming,
    error: state.error,
    streamTriage,
    abort,
  };
}
