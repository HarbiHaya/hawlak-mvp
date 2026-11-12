import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import { ApiError, isAbortError, type ApiClient } from "../lib/api";
import { DEMO_REVIEW_EVENT } from "../lib/demoCase";
import { describeError } from "../lib/errors";
import {
  initialQueueState,
  queueReducer,
  sortedTasks,
  type QueueState,
  type RecordedReview,
  type ReviewTask,
} from "../lib/queue";
import type { ReviewPage } from "../lib/schemas";

export type QueueSource = { kind: "api"; client: ApiClient } | { kind: "fixture" };

export interface SyncStatus {
  phase: "idle" | "loading" | "ok" | "error";
  error: string | null;
  unauthorized: boolean;
}

export interface ReviewQueueHandle {
  state: QueueState;
  tasks: ReviewTask[];
  sync: SyncStatus;
  refresh: () => void;
  markReviewed: (eventId: string, review: RecordedReview) => void;
}

export const POLL_INTERVAL_MS = 5000;
const PAGE_LIMIT = 20;
const MAX_PAGES_PER_POLL = 10;

/**
 * Polls GET /internal/review-events after the last opaque cursor and upserts
 * by eventId. Only one request runs at a time. Polling stops after a 401
 * until the operator refreshes manually.
 */
export function useReviewQueue(source: QueueSource, intervalMs = POLL_INTERVAL_MS): ReviewQueueHandle {
  const [state, dispatch] = useReducer(queueReducer, initialQueueState);
  const [sync, setSync] = useState<SyncStatus>({ phase: "idle", error: null, unauthorized: false });
  const cursorRef = useRef<string | null>(null);
  const stopped = useRef(false);
  // Non-null while a poll is running; doubles as the "in flight" lock.
  const controller = useRef<AbortController | null>(null);

  const poll = useCallback(async () => {
    if (controller.current) return;
    const ctrl = new AbortController();
    controller.current = ctrl;
    setSync((s) => ({ ...s, phase: "loading" }));
    try {
      if (source.kind === "fixture") {
        const page: ReviewPage = { data: [DEMO_REVIEW_EVENT], nextCursor: null };
        dispatch({ type: "page", page, now: new Date().toISOString() });
      } else {
        for (let i = 0; i < MAX_PAGES_PER_POLL; i += 1) {
          const page = await source.client.listReviewEvents(cursorRef.current, PAGE_LIMIT, ctrl.signal);
          if (page.nextCursor !== null) cursorRef.current = page.nextCursor;
          dispatch({ type: "page", page, now: new Date().toISOString() });
          if (page.data.length < PAGE_LIMIT) break;
        }
      }
      stopped.current = false;
      setSync({ phase: "ok", error: null, unauthorized: false });
    } catch (error) {
      if (isAbortError(error)) return;
      const unauthorized = error instanceof ApiError && error.status === 401;
      if (unauthorized) stopped.current = true;
      setSync({ phase: "error", error: describeError(error), unauthorized });
    } finally {
      if (controller.current === ctrl) controller.current = null;
    }
  }, [source]);

  useEffect(() => {
    const cancel = () => {
      controller.current?.abort();
      controller.current = null;
    };
    void poll();
    if (source.kind === "fixture") return cancel;
    const timer = window.setInterval(() => {
      if (!stopped.current) void poll();
    }, intervalMs);
    return () => {
      window.clearInterval(timer);
      cancel();
    };
  }, [poll, source.kind, intervalMs]);

  const refresh = useCallback(() => {
    stopped.current = false;
    void poll();
  }, [poll]);

  const markReviewed = useCallback((eventId: string, review: RecordedReview) => {
    dispatch({ type: "review", eventId, review });
  }, []);

  const tasks = useMemo(() => sortedTasks(state), [state]);

  return { state, tasks, sync, refresh, markReviewed };
}
