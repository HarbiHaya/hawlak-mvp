import { describe, expect, it, vi } from "vitest";

import { HawlakApi } from "./api";

describe("HawlakApi", () => {
  it("keeps the operator token in the authorization header and loads dialect options", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(
        JSON.stringify({
          dialects: [
            { code: "ar-SA-hijazi", labelAr: "حجازي", labelEn: "Hijazi" },
          ],
          voice: {
            provider: "elevenlabs",
            voiceLabel: "Fahad — Saudi",
            modelId: "eleven_v4",
            languageCode: "ar",
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const api = new HawlakApi("http://127.0.0.1:3000", "memory-only-token", fetcher);

    const result = await api.getVoiceOptions();

    expect(result.dialects[0]?.labelAr).toBe("حجازي");
    expect(fetcher).toHaveBeenCalledOnce();
    const [url, init] = fetcher.mock.calls[0] ?? [];
    expect(url).toBe("http://127.0.0.1:3000/internal/voice-options");
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      "Bearer memory-only-token",
    );
  });

  it("sends one explicit reminder occurrence for a stored patient photo", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(
        JSON.stringify({
          voiceMessageId: "MM-voice",
          messageId: "MM-card",
          mediaId: "media-1",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const api = new HawlakApi("http://127.0.0.1:3000", "token", fetcher);

    const result = await api.sendPhotoReminder(
      "case-1",
      "media-1",
      "demo-1",
      "reminder-action-1",
    );

    expect(result.voiceMessageId).toBe("MM-voice");
    const [url, init] = fetcher.mock.calls[0] ?? [];
    expect(url).toBe(
      "http://127.0.0.1:3000/internal/cases/case-1/send-photo-reminder",
    );
    expect(JSON.parse(String(init?.body))).toEqual({
      mediaId: "media-1",
      reminderId: "demo-1",
    });
    expect(new Headers(init?.headers).get("Idempotency-Key")).toBe(
      "reminder-action-1",
    );
  });

  it("loads the auditable delivery and patient-choice timeline", async () => {
    const fetcher = vi.fn(async () =>
      new Response(
        JSON.stringify({
          caseId: "case-1",
          data: [
            {
              type: "whatsapp_outbound_audio",
              occurredAt: "2026-11-08T18:00:00Z",
              details: {
                status: "sent",
                step: "session_summary",
                deliveryStatus: "delivered",
              },
            },
            {
              type: "whatsapp_inbound_button",
              occurredAt: "2026-11-08T18:05:00Z",
              details: { status: "processed", step: "inbound", choice: "taken" },
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const api = new HawlakApi("http://127.0.0.1:3000", "token", fetcher);

    const result = await api.getCaseTimeline("case-1");

    expect(result.data[0]?.details.deliveryStatus).toBe("delivered");
    expect(result.data[1]?.details.choice).toBe("taken");
    expect(fetcher).toHaveBeenCalledWith(
      "http://127.0.0.1:3000/internal/cases/case-1/timeline",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });
});
