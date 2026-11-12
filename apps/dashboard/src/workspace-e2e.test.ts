import { describe, expect, it, vi } from "vitest";

import { HawlakApi, type WorkspaceCaseDetail } from "./api";

describe("hospital to insurer workspace flow", () => {
  it("keeps the hospital document and exact reviewed content together through approval", async () => {
    const calls: string[] = [];
    let createdCaseId = "";
    let reviewedContent: unknown;
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      const method = init?.method ?? "GET";
      calls.push(`${method} ${url.pathname}`);

      if (method === "POST" && url.pathname.endsWith("/documents")) {
        createdCaseId = new Headers(init?.headers).get("X-Case-Id") ?? "";
        return json({
          objectKey: `synthetic/${createdCaseId}/discharge.pdf`,
          filename: "synthetic-discharge.pdf",
        }, 201);
      }
      if (method === "POST" && url.pathname.endsWith("/workspace/cases")) {
        const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
        expect(body).toMatchObject({
          caseId: createdCaseId,
          patientName: "مريض تجريبي",
          sourceDocument: {
            objectKey: `synthetic/${createdCaseId}/discharge.pdf`,
            filename: "synthetic-discharge.pdf",
          },
        });
        return json({ caseId: createdCaseId, reviewStatus: "draft" }, 201);
      }
      if (method === "GET" && url.pathname.endsWith("/workspace/cases")) {
        return json({
          data: [{
            caseId: createdCaseId,
            patientName: "مريض تجريبي",
            languageCode: "ar",
            reviewStatus: "draft",
            alertCount: 0,
          }],
        });
      }
      if (method === "PATCH" && url.pathname.endsWith("/content")) {
        reviewedContent = JSON.parse(String(init?.body));
        return json({ caseId: createdCaseId, reviewStatus: "draft" });
      }
      if (method === "POST" && url.pathname.endsWith("/approve")) {
        expect(reviewedContent).toEqual(exactReviewedContent);
        expect(new Headers(init?.headers).get("Idempotency-Key")).toBe(
          `approve-${createdCaseId}`,
        );
        return json({
          caseId: createdCaseId,
          reviewStatus: "approved",
          deliveryRuns: [{
            id: "run-discharge",
            kind: "discharge_voice_note",
            status: "pending",
            scheduledAt: "2026-11-12T12:00:00Z",
          }],
        });
      }
      return json({ detail: "unexpected_request" }, 500);
    });
    const api = new HawlakApi("https://hawlak.test/api", "", fetcher);

    const submitted = await api.submitDischargePacket({
      document: new File(["synthetic"], "synthetic-discharge.pdf", {
        type: "application/pdf",
      }),
      patientFullName: "مريض تجريبي",
      preferredAddress: "أبو التجربة",
      phoneE164: "+99900000000",
      languageCode: "ar",
      dialectCode: "ar-SA-najdi",
    });
    const queue = await api.listWorkspaceCases();
    await api.updateWorkspaceContent(submitted.caseId, exactReviewedContent);
    const approved = await api.approveWorkspaceCase(
      submitted.caseId,
      "SYN-REVIEWER",
      `approve-${submitted.caseId}`,
    );

    expect(queue.data[0]?.caseId).toBe(submitted.caseId);
    expect(approved.deliveryRuns).toHaveLength(1);
    expect(calls).toEqual([
      "POST /api/internal/workspace/documents",
      "POST /api/internal/workspace/cases",
      "GET /api/internal/workspace/cases",
      `PATCH /api/internal/workspace/cases/${submitted.caseId}/content`,
      `POST /api/internal/workspace/cases/${submitted.caseId}/approve`,
    ]);
  });
});

const exactReviewedContent: Pick<
  WorkspaceCaseDetail,
  "dischargeVoiceNote" | "medications" | "callPlan"
> = {
  dischargeVoiceNote: {
    enabled: true,
    script: "نص تجريبي معتمد من المراجع.",
  },
  medications: [{
    medicationId: "SYN-MED-1",
    displayName: "دواء تجريبي ألف",
    doseInstruction: "تعليمات تجريبية معتمدة",
    dispensed: true,
    image: {
      source: "catalog",
      objectKey: "synthetic/medicine-a.png",
      reviewStatus: "approved",
    },
    reminderEnabled: true,
    reminderScript: "تذكير تجريبي معتمد.",
  }],
  callPlan: {
    enabled: false,
    scheduledAfterHours: 24,
    openingScript: "",
    questions: [],
    completionScript: "",
    transferScript: "",
    transferTarget: "",
    responderPhoneE164: "",
  },
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
