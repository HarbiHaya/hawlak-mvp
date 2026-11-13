import { describe, expect, it, vi } from "vitest";

import { HawlakApi } from "./api";

describe("HawlakApi", () => {
  it("starts a role-scoped demo session with username and password", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(
        JSON.stringify({
          accessToken: "signed-session-token",
          role: "admin",
          username: "admin",
          displayName: "إدارة العرض",
          expiresAt: "2026-11-13T12:00:00Z",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const session = await HawlakApi.login(
      "http://127.0.0.1:3000",
      "admin",
      "synthetic-demo-password",
      fetcher,
    );

    expect(session.role).toBe("admin");
    const [url, init] = fetcher.mock.calls[0] ?? [];
    expect(url).toBe("http://127.0.0.1:3000/auth/login");
    expect(JSON.parse(String(init?.body))).toEqual({
      username: "admin",
      password: "synthetic-demo-password",
    });
    expect(new Headers(init?.headers).has("Authorization")).toBe(false);
  });

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
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
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

  it("loads the insurer case queue through the workspace interface", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(
        JSON.stringify({
          data: [
            {
              caseId: "case-1",
              patientName: "محمد عبدالله السالم",
              preferredFormOfAddress: "أبو محمد",
              dialectCode: "ar-SA-najdi",
              languageCode: "ar",
              reviewStatus: "draft",
              submittedAt: "2026-11-12T09:00:00Z",
              alertCount: 1,
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const api = new HawlakApi("http://127.0.0.1:3000", "token", fetcher);

    const result = await api.listWorkspaceCases();

    expect(result.data[0]?.patientName).toBe("محمد عبدالله السالم");
    expect(fetcher).toHaveBeenCalledWith(
      "http://127.0.0.1:3000/internal/workspace/cases",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("uploads the hospital PDF before it creates the discharge case", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/documents")) {
        return new Response(
          JSON.stringify({ objectKey: "synthetic/case-new.pdf", filename: "synthetic-discharge.pdf" }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(
        JSON.stringify({ caseId: "case-new", reviewStatus: "awaiting_review" }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      );
    });
    const api = new HawlakApi("http://127.0.0.1:3000", "token", fetcher);
    const document = new File(["synthetic"], "synthetic-discharge.pdf", {
      type: "application/pdf",
    });

    await api.submitDischargePacket({
      document,
      patientFullName: "محمد عبدالله السالم",
      preferredAddress: "أبو محمد",
      phoneE164: "+966500000001",
      languageCode: "ar",
      dialectCode: "ar-SA-najdi",
    });

    expect(fetcher).toHaveBeenCalledTimes(2);
    const [uploadUrl, uploadInit] = fetcher.mock.calls[0] ?? [];
    expect(uploadUrl).toBe("http://127.0.0.1:3000/internal/workspace/documents");
    expect(uploadInit?.body).toBe(document);
    expect(new Headers(uploadInit?.headers).get("Content-Type")).toBe("application/pdf");
    expect(new Headers(uploadInit?.headers).get("X-Filename")).toBe("synthetic-discharge.pdf");
    const [createUrl, createInit] = fetcher.mock.calls[1] ?? [];
    expect(createUrl).toBe("http://127.0.0.1:3000/internal/workspace/cases");
    expect(JSON.parse(String(createInit?.body))).toEqual(
      expect.objectContaining({
        patientName: "محمد عبدالله السالم",
        preferredFormOfAddress: "أبو محمد",
        sourceDocument: {
          objectKey: "synthetic/case-new.pdf",
          filename: "synthetic-discharge.pdf",
        },
      }),
    );
  });

  it("omits browser authorization when the hosted proxy owns authentication", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ data: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const api = new HawlakApi("/api", "", fetcher);

    await api.listWorkspaceCases();

    const [, init] = fetcher.mock.calls[0] ?? [];
    expect(new Headers(init?.headers).has("Authorization")).toBe(false);
  });

  it("uploads a reviewed medication image through the case interface", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(
        JSON.stringify({
          objectKey: "cases/case-1/media/medicine.jpg",
          filename: "medicine.jpg",
          contentType: "image/jpeg",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    const api = new HawlakApi("/api", "", fetcher);
    const image = new File(["synthetic"], "medicine.jpg", { type: "image/jpeg" });

    const result = await api.uploadMedicationImage("case-1", image);

    expect(result.objectKey).toBe("cases/case-1/media/medicine.jpg");
    const [url, init] = fetcher.mock.calls[0] ?? [];
    expect(url).toBe("/api/internal/workspace/cases/case-1/medication-images");
    expect(init?.body).toBe(image);
    expect(new Headers(init?.headers).get("Content-Type")).toBe("image/jpeg");
    expect(new Headers(init?.headers).get("X-Filename")).toBe("medicine.jpg");
  });

  it("records a pharmacist's decision on a medicine-box photo", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ id: "photo-1", reviewStatus: "confirmed" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const api = new HawlakApi("/api", "", fetcher);

    const result = await api.reviewMedicinePhoto("case-1", "photo-1", "confirmed", "SYN-PHARMACIST");

    expect(result.reviewStatus).toBe("confirmed");
    const [url, init] = fetcher.mock.calls[0] ?? [];
    expect(url).toBe("/api/internal/workspace/cases/case-1/photos/photo-1/review");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      decision: "confirmed",
      reviewedBy: "SYN-PHARMACIST",
    });
  });

  it("sends the caregiver phone with the discharge case", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(
        JSON.stringify(
          String(input).endsWith("/documents")
            ? { objectKey: "synthetic/case-new.pdf", filename: "d.pdf" }
            : { caseId: "case-new", reviewStatus: "draft" },
        ),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    const api = new HawlakApi("/api", "", fetcher);

    await api.submitDischargePacket({
      document: new File(["synthetic"], "d.pdf", { type: "application/pdf" }),
      patientFullName: "Synthetic Patient",
      phoneE164: "+966500000001",
      caregiverPhoneE164: "+966500000002",
      languageCode: "en",
      dialectCode: "ar-SA-najdi",
    });

    const [, createInit] = fetcher.mock.calls[1] ?? [];
    expect(JSON.parse(String(createInit?.body)).caregiverPhoneE164).toBe("+966500000002");
  });

  it("approves exact reviewed content and receives queued delivery runs", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(
        JSON.stringify({
          caseId: "case-1",
          reviewStatus: "approved",
          deliveryRuns: [
            {
              id: "run-1",
              kind: "discharge_voice_note",
              status: "pending",
              scheduledAt: "2026-11-12T12:00:00Z",
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const api = new HawlakApi("/api", "", fetcher);

    const result = await api.approveWorkspaceCase("case-1", "SYN-REVIEWER", "approve-1");

    expect(result.deliveryRuns[0]?.kind).toBe("discharge_voice_note");
    const [url, init] = fetcher.mock.calls[0] ?? [];
    expect(url).toBe("/api/internal/workspace/cases/case-1/approve");
    expect(JSON.parse(String(init?.body))).toEqual({ approvedBy: "SYN-REVIEWER" });
    expect(new Headers(init?.headers).get("Idempotency-Key")).toBe("approve-1");
  });

  it("reports FastAPI validation errors as one readable code", async () => {
    const fetcher = vi.fn(async () =>
      new Response(JSON.stringify({ detail: [{ loc: ["body"], msg: "bad" }] }), { status: 422 }),
    );
    const api = new HawlakApi("/api", "", fetcher);

    await expect(api.listWorkspaceCases()).rejects.toMatchObject({ code: "validation_failed" });
  });

  it("downloads a case file so the reviewer can see it", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response("%PDF-1.4", { status: 200, headers: { "Content-Type": "application/pdf" } }),
    );
    const api = new HawlakApi("/api", "token", fetcher);

    const blob = await api.getCaseFile("case-1", "cases/case-1/media/a.pdf");

    expect(await blob.text()).toBe("%PDF-1.4");
    const [url, init] = fetcher.mock.calls[0] ?? [];
    expect(url).toBe("/api/internal/workspace/cases/case-1/files?key=cases%2Fcase-1%2Fmedia%2Fa.pdf");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer token");
  });

  it("loads what was read from the discharge PDF", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({
        status: "parsed", language: "en", text: "NEW MEDICINES", notes: [],
        medications: [{ name: "Fictional medicine A", instruction: "5 mg" }],
        stoppedMedications: [], sections: [],
      }), { status: 200 }),
    );
    const api = new HawlakApi("/api", "", fetcher);

    const extraction = await api.getCaseExtraction("case-1");

    expect(extraction.medications[0]?.name).toBe("Fictional medicine A");
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/internal/workspace/cases/case-1/extraction");
  });
});

