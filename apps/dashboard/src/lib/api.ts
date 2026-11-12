import { z } from "zod";

import {
  ApproveResponseSchema,
  CaseResponseSchema,
  GeneratedScriptSchema,
  OutcomeResponseSchema,
  ReviewPageSchema,
  VoiceOptionsSchema,
  issuesToText,
  type ApproveRequest,
  type ApproveResponse,
  type CaseResponse,
  type GeneratedScript,
  type OutcomeRequest,
  type RecordedOutcome,
  type ReviewPage,
  type VoiceOptions,
} from "./schemas";

/** The API answered with a non-2xx status, or could not be reached (status 0). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly serverMessage?: string,
  ) {
    super(`api_error ${status} ${code}`);
    this.name = "ApiError";
  }
}

/** The API answered, but the body does not match the agreed contract. */
export class ContractError extends Error {
  constructor(
    readonly where: string,
    readonly issues: string[],
  ) {
    super(`contract_error ${where}`);
    this.name = "ContractError";
  }
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface CreateCaseResult {
  data: CaseResponse;
  /** false when the API replayed an identical existing case (HTTP 200). */
  created: boolean;
}

export function isAbortError(error: unknown): boolean {
  // Checked by name: DOMException can come from different realms (browser, Node, jsdom).
  return typeof error === "object" && error !== null && (error as { name?: unknown }).name === "AbortError";
}

/**
 * The only module that talks to Hawlak's API. The bearer token lives in this
 * object (in memory) and is never written to storage or logged.
 */
export class ApiClient {
  readonly origin: string;
  readonly #token: string;
  readonly #fetch: FetchLike;

  constructor(origin: string, token: string, fetchImpl?: FetchLike) {
    this.origin = origin.replace(/\/+$/, "");
    this.#token = token;
    this.#fetch = fetchImpl ?? ((input, init) => fetch(input, init));
  }

  async getVoiceOptions(signal?: AbortSignal): Promise<VoiceOptions> {
    const res = await this.#send("/internal/voice-options", { signal });
    return this.#parse(res, VoiceOptionsSchema, "voice-options");
  }

  async createCase(body: unknown): Promise<CreateCaseResult> {
    const res = await this.#send("/internal/cases", { method: "POST", body: JSON.stringify(body) });
    const data = await this.#parse(res, CaseResponseSchema, "cases");
    return { data, created: res.status === 201 };
  }

  async generateScript(caseId: string): Promise<GeneratedScript> {
    const res = await this.#send(`/internal/cases/${encodeURIComponent(caseId)}/generate-script`, {
      method: "POST",
    });
    return this.#parse(res, GeneratedScriptSchema, "generate-script");
  }

  async approveAndSend(
    caseId: string,
    body: ApproveRequest,
    idempotencyKey: string,
  ): Promise<ApproveResponse> {
    const res = await this.#send(
      `/internal/cases/${encodeURIComponent(caseId)}/approve-and-send`,
      { method: "POST", body: JSON.stringify(body) },
      { "Idempotency-Key": idempotencyKey },
    );
    return this.#parse(res, ApproveResponseSchema, "approve-and-send");
  }

  async listReviewEvents(after: string | null, limit = 20, signal?: AbortSignal): Promise<ReviewPage> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (after !== null) params.set("after", after);
    const res = await this.#send(`/internal/review-events?${params.toString()}`, { signal });
    return this.#parse(res, ReviewPageSchema, "review-events");
  }

  async getMedia(mediaId: string, signal?: AbortSignal): Promise<Blob> {
    const res = await this.#send(`/internal/media/${encodeURIComponent(mediaId)}`, { signal });
    return res.blob();
  }

  async recordOutcome(
    eventId: string,
    body: OutcomeRequest,
    idempotencyKey: string,
  ): Promise<RecordedOutcome> {
    const res = await this.#send(
      `/internal/review-events/${encodeURIComponent(eventId)}/outcomes`,
      { method: "POST", body: JSON.stringify(body) },
      { "Idempotency-Key": idempotencyKey },
    );
    const parsed = await this.#parse(res, OutcomeResponseSchema, "review-outcomes");
    return parsed.data;
  }

  async #send(path: string, init: RequestInit = {}, extra: Record<string, string> = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${this.#token}`);
    if (init.body !== undefined) headers.set("Content-Type", "application/json");
    for (const [name, value] of Object.entries(extra)) headers.set(name, value);

    let res: Response;
    try {
      res = await this.#fetch(`${this.origin}${path}`, { ...init, headers });
    } catch (error) {
      if (isAbortError(error)) throw error;
      throw new ApiError(0, "network");
    }
    if (!res.ok) {
      let code = `http_${res.status}`;
      let message: string | undefined;
      try {
        const body: unknown = await res.json();
        if (body && typeof body === "object") {
          const record = body as Record<string, unknown>;
          if (typeof record.error === "string") code = record.error;
          if (typeof record.message === "string") message = record.message;
          else if (typeof record.detail === "string") message = record.detail;
        }
      } catch {
        // Non-JSON error bodies keep the generic code.
      }
      throw new ApiError(res.status, code, message);
    }
    return res;
  }

  async #parse<T>(res: Response, schema: z.ZodType<T>, where: string): Promise<T> {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      throw new ContractError(where, ["الاستجابة ليست JSON صالحًا"]);
    }
    const result = schema.safeParse(body);
    if (!result.success) throw new ContractError(where, issuesToText(result.error));
    return result.data;
  }
}
