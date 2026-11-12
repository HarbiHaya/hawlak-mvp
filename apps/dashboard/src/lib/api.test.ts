import { describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError, ContractError } from "./api";
import { DEMO_REVIEW_EVENT } from "./demoCase";

const TOKEN = "local-demo-token-0123456789";
const CHECKSUM = `sha256:${"a".repeat(64)}`;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function client(respond: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => respond(url, init ?? {}));
  return { api: new ApiClient("http://localhost:3000/", TOKEN, fetchImpl), fetchImpl };
}

function headersOf(init: RequestInit): Headers {
  return new Headers(init.headers);
}

describe("ApiClient", () => {
  it("polls review events with the bearer token, cursor and limit", async () => {
    const { api, fetchImpl } = client(() => json({ data: [DEMO_REVIEW_EVENT], nextCursor: "event-sequence:1" }));
    const page = await api.listReviewEvents("event-sequence:0", 20);

    expect(page.nextCursor).toBe("event-sequence:1");
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("http://localhost:3000/internal/review-events?limit=20&after=event-sequence%3A0");
    expect(headersOf(init as RequestInit).get("Authorization")).toBe(`Bearer ${TOKEN}`);
  });

  it("omits the cursor on the first poll", async () => {
    const { api, fetchImpl } = client(() => json({ data: [], nextCursor: null }));
    await api.listReviewEvents(null);
    expect(fetchImpl.mock.calls[0][0]).toBe("http://localhost:3000/internal/review-events?limit=20");
  });

  it("records an outcome with the exact body and the given Idempotency-Key", async () => {
    const recorded = {
      outcomeId: "outcome_01",
      eventId: "evt_01",
      eventVersion: 1,
      outcome: "matched",
      reviewerId: "demo-pharmacist-01",
      note: null,
      recordedAt: "2026-11-04T12:00:00Z",
    };
    const { api, fetchImpl } = client(() => json({ data: recorded }, 201));
    const body = { eventVersion: 1 as const, outcome: "matched" as const, reviewerId: "demo-pharmacist-01", note: null };
    const result = await api.recordOutcome("evt_01", body, "review-key-1");

    expect(result).toEqual(recorded);
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("http://localhost:3000/internal/review-events/evt_01/outcomes");
    const sent = init as RequestInit;
    expect(sent.method).toBe("POST");
    expect(JSON.parse(String(sent.body))).toEqual(body);
    expect(headersOf(sent).get("Idempotency-Key")).toBe("review-key-1");
    expect(headersOf(sent).get("Content-Type")).toBe("application/json");
  });

  it("approves with the unchanged checksum and an Idempotency-Key", async () => {
    const { api, fetchImpl } = client(() =>
      json({ artifactId: "art_1", caseId: "case_01-najdi", scriptChecksum: CHECKSUM, audioChecksum: CHECKSUM, messageIds: ["m1", "m2", "m3"] }),
    );
    await api.approveAndSend("case_01-najdi", { artifactId: "art_1", scriptChecksum: CHECKSUM, approvedBy: "demo-operator-01" }, "approve-key");

    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("http://localhost:3000/internal/cases/case_01-najdi/approve-and-send");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({
      artifactId: "art_1",
      scriptChecksum: CHECKSUM,
      approvedBy: "demo-operator-01",
    });
    expect(headersOf(init as RequestInit).get("Idempotency-Key")).toBe("approve-key");
  });

  it("reports 201 as created and 200 as a replayed case", async () => {
    const body = { caseId: "case_01-najdi", planId: "plan_01-najdi", version: 1, status: "active" };
    const created = await client(() => json(body, 201)).api.createCase({});
    const replayed = await client(() => json(body, 200)).api.createCase({});
    expect(created.created).toBe(true);
    expect(replayed.created).toBe(false);
  });

  it("turns error responses into ApiError with the server's code", async () => {
    const { api } = client(() => json({ error: "case_conflict" }, 409));
    const error = await api.createCase({}).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(409);
    expect((error as ApiError).code).toBe("case_conflict");
  });

  it("maps 401 and network failures without exposing the token", async () => {
    const unauthorized = await client(() => json({ detail: "Unauthorized" }, 401))
      .api.listReviewEvents(null)
      .catch((e: unknown) => e);
    expect((unauthorized as ApiError).status).toBe(401);
    expect(String((unauthorized as Error).message)).not.toContain(TOKEN);

    const offline = await client(() => {
      throw new TypeError("Failed to fetch");
    })
      .api.listReviewEvents(null)
      .catch((e: unknown) => e);
    expect((offline as ApiError).status).toBe(0);
    expect((offline as ApiError).code).toBe("network");
  });

  it("rejects responses that break the contract with a readable ContractError", async () => {
    const { api } = client(() => json({ dialects: [], voice: {} }));
    const error = await api.getVoiceOptions().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ContractError);
    expect((error as ContractError).issues.length).toBeGreaterThan(0);

    const badPage = await client(() => json({ items: [] })).api.listReviewEvents(null).catch((e: unknown) => e);
    expect(badPage).toBeInstanceOf(ContractError);
  });

  it("fetches photo bytes with the token", async () => {
    const { api, fetchImpl } = client(() => new Response("jpeg-bytes", { headers: { "Content-Type": "image/jpeg" } }));
    const blob = await api.getMedia("media_01");
    expect(blob.size).toBe(10);
    expect(blob.type).toBe("image/jpeg");
    expect(fetchImpl.mock.calls[0][0]).toBe("http://localhost:3000/internal/media/media_01");
    expect(headersOf(fetchImpl.mock.calls[0][1] as RequestInit).get("Authorization")).toBe(`Bearer ${TOKEN}`);
  });

  it("never stores anything in browser storage", async () => {
    const { api } = client(() => json({ data: [], nextCursor: null }));
    await api.listReviewEvents(null);
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });
});
