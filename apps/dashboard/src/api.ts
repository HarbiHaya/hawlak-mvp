import {
  PharmacistReviewRequestedSchema,
  type PharmacistReviewRequested,
} from "@hawlak/contracts";

export type DialectCode = "ar-SA-hijazi" | "ar-SA-najdi" | "ar-SA-janoubi";

export interface VoiceOptions {
  dialects: Array<{ code: DialectCode; labelAr: string; labelEn: string }>;
  voice: {
    provider: "elevenlabs";
    voiceLabel: string;
    modelId: string;
    languageCode: "ar";
  };
}

export interface AudioFirstScript {
  kind: "session_summary" | "recovery_warning";
  artifactId: string;
  spokenTextAr: string;
  scriptChecksum: string;
}

export interface AudioFirstDraft {
  caseId: string;
  approvalChecksum: string;
  scripts: AudioFirstScript[];
  factReport: { passed: boolean; differences: Array<Record<string, unknown>> };
}

export interface ReviewPage {
  data: PharmacistReviewRequested[];
  nextCursor: string | null;
}

export interface TimelineEntry {
  type: string;
  occurredAt: string;
  details: {
    status?: string;
    step?: string;
    deliveryStatus?: string;
    choice?: string;
    [key: string]: string | number | undefined;
  };
}

export interface CaseTimeline {
  caseId: string;
  data: TimelineEntry[];
}

export type WorkspaceReviewStatus = "draft" | "approved";

export interface WorkspaceCaseSummary {
  caseId: string;
  patientName: string;
  languageCode: "ar" | "en";
  reviewStatus: WorkspaceReviewStatus;
  alertCount: number;
}

export interface DischargeVoiceNote {
  enabled: boolean;
  script: string;
}

export interface MedicationImage {
  source: "catalog" | "patient_photo";
  objectKey: string;
  reviewStatus: "pending" | "approved" | "rejected";
  ocrCandidate?: string | null;
}

export interface WorkspaceMedication {
  medicationId: string;
  displayName: string;
  doseInstruction: string;
  dispensed: boolean;
  image: MedicationImage | null;
  reminderEnabled: boolean;
  reminderScript: string;
}

export interface CallQuestion {
  id: string;
  prompt: string;
}

export interface CallPlan {
  enabled: boolean;
  scheduledAfterHours: number;
  openingScript: string;
  questions: CallQuestion[];
  completionScript: string;
  transferScript: string;
  transferTarget: string;
  responderPhoneE164: string;
}

export interface DeliveryRun {
  id: string;
  kind: "discharge_voice_note" | "medication_reminder" | "follow_up_call";
  status: string;
  scheduledAt: string;
}

export interface WorkspaceCaseDetail extends WorkspaceCaseSummary {
  preferredFormOfAddress: string | null;
  dialectCode: DialectCode;
  sourceDocument: { objectKey: string; filename: string };
  dischargeVoiceNote: DischargeVoiceNote;
  medications: WorkspaceMedication[];
  callPlan: CallPlan;
  approvedBy: string | null;
  approvedAt: string | null;
  deliveryRuns: DeliveryRun[];
}

export interface WorkspaceAlert {
  id: string;
  caseId: string;
  type: string;
  severity: string;
  status: "open" | "resolved";
  summary: string;
  createdAt: string;
}

export interface CaregiverCase {
  caseId: string;
  patientName: string;
  journeyStatus: WorkspaceReviewStatus;
  medications: Array<{
    medicationId: string;
    displayName: string;
    status: "scheduled" | "needs_support";
  }>;
  openAlertCount: number;
  nextCallAt: string | null;
}

export interface ApprovalResult {
  caseId: string;
  reviewStatus: "approved";
  deliveryRuns: DeliveryRun[];
}

export interface SubmitDischargePacket {
  document: File;
  patientFullName: string;
  preferredAddress?: string;
  phoneE164: string;
  languageCode: "ar" | "en";
  dialectCode: DialectCode;
}

export type ReviewOutcome =
  | "matched"
  | "mismatch_found"
  | "unclear_photo"
  | "contact_patient";

export interface SyntheticPlan {
  synthetic: true;
  reviewStatus: string;
  case: {
    caseId: string;
    patientRef: string;
    patientAlias: string;
    dialectCode: DialectCode;
    expectedBoxCount: number;
  };
  approvedPlan: {
    planId: string;
    version: number;
    approvedBy: string;
    approvedAt: string;
    source: Record<string, string>;
    clinicalFacts: Record<string, unknown>;
  };
}

export class HawlakApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
  ) {
    super(code);
  }
}

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export class HawlakApi {
  private readonly baseUrl: string;

  constructor(
    baseUrl: string,
    private readonly token: string = "",
    private readonly fetcher: Fetcher = globalThis.fetch.bind(globalThis),
  ) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  getVoiceOptions(): Promise<VoiceOptions> {
    return this.request("/internal/voice-options");
  }

  async createCase(
    source: SyntheticPlan,
    recipient: string,
    dialectCode: DialectCode,
    runId: string,
  ): Promise<{ caseId: string; planId: string; version: number; status: string }> {
    const plan = structuredClone(source);
    plan.case.caseId = `case_${runId}`;
    plan.case.patientRef = `SYN-${runId}`;
    plan.case.dialectCode = dialectCode;
    plan.approvedPlan.planId = `plan_${runId}`;
    plan.approvedPlan.source = {
      ...plan.approvedPlan.source,
      recordId: `SYN-${runId}`,
    };
    return this.request("/internal/cases", {
      method: "POST",
      body: JSON.stringify({ ...plan, demoRecipient: recipient }),
    });
  }

  generateAudioFirst(caseId: string): Promise<AudioFirstDraft> {
    return this.request(`/internal/cases/${encodeURIComponent(caseId)}/generate-audio-first`, {
      method: "POST",
    });
  }

  getCaseTimeline(caseId: string): Promise<CaseTimeline> {
    return this.request(`/internal/cases/${encodeURIComponent(caseId)}/timeline`);
  }

  listWorkspaceCases(): Promise<{ data: WorkspaceCaseSummary[] }> {
    return this.request("/internal/workspace/cases");
  }

  getWorkspaceCase(caseId: string): Promise<WorkspaceCaseDetail> {
    return this.request(`/internal/workspace/cases/${encodeURIComponent(caseId)}`);
  }

  async submitDischargePacket(
    packet: SubmitDischargePacket,
  ): Promise<{ caseId: string; reviewStatus: WorkspaceReviewStatus }> {
    const runId = `${Date.now().toString(36)}${crypto.randomUUID().slice(0, 6)}`;
    const caseId = `case_${runId}`;
    const stored = await this.request<{ objectKey: string; filename: string }>(
      "/internal/workspace/documents",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/pdf",
          "X-Case-Id": caseId,
          "X-Filename": packet.document.name,
        },
        body: packet.document,
      },
    );
    return this.request("/internal/workspace/cases", {
      method: "POST",
      body: JSON.stringify({
        caseId,
        patientName: packet.patientFullName,
        preferredFormOfAddress: packet.preferredAddress || null,
        phoneE164: packet.phoneE164,
        languageCode: packet.languageCode,
        dialectCode: packet.dialectCode,
        sourceDocument: stored,
      }),
    });
  }

  listWorkspaceAlerts(): Promise<{ data: WorkspaceAlert[] }> {
    return this.request("/internal/workspace/alerts");
  }

  uploadMedicationImage(
    caseId: string,
    image: File,
  ): Promise<{ objectKey: string; filename: string; contentType: string }> {
    return this.request(
      `/internal/workspace/cases/${encodeURIComponent(caseId)}/medication-images`,
      {
        method: "POST",
        headers: {
          "Content-Type": image.type,
          "X-Filename": image.name,
        },
        body: image,
      },
    );
  }

  updateWorkspaceContent(
    caseId: string,
    content: Pick<WorkspaceCaseDetail, "dischargeVoiceNote" | "medications" | "callPlan">,
  ): Promise<{ caseId: string; reviewStatus: WorkspaceReviewStatus }> {
    return this.request(`/internal/workspace/cases/${encodeURIComponent(caseId)}/content`, {
      method: "PATCH",
      body: JSON.stringify(content),
    });
  }

  approveWorkspaceCase(caseId: string, approvedBy: string, idempotencyKey: string): Promise<ApprovalResult> {
    return this.request(`/internal/workspace/cases/${encodeURIComponent(caseId)}/approve`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ approvedBy }),
    });
  }

  getCaregiverCase(caseId: string): Promise<CaregiverCase> {
    return this.request(`/internal/caregiver/cases/${encodeURIComponent(caseId)}`);
  }

  approveAudioFirst(
    draft: AudioFirstDraft,
    approvedBy: string,
    idempotencyKey: string,
  ): Promise<{ caseId: string; approvalChecksum: string; messageIds: string[] }> {
    const session = draft.scripts.find((script) => script.kind === "session_summary");
    const recovery = draft.scripts.find((script) => script.kind === "recovery_warning");
    if (!session || !recovery) {
      throw new HawlakApiError(0, "audio_first_draft_incomplete");
    }
    return this.request(
      `/internal/cases/${encodeURIComponent(draft.caseId)}/approve-audio-first-and-send`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({
          sessionArtifactId: session.artifactId,
          recoveryArtifactId: recovery.artifactId,
          approvalChecksum: draft.approvalChecksum,
          approvedBy,
        }),
      },
    );
  }

  async listReviewEvents(after: string | null = null): Promise<ReviewPage> {
    const search = after ? `?after=${encodeURIComponent(after)}` : "";
    const page = await this.request<{ data: unknown[]; nextCursor: string | null }>(
      `/internal/review-events${search}`,
    );
    return {
      data: page.data.map((item) => PharmacistReviewRequestedSchema.parse(item)),
      nextCursor: page.nextCursor,
    };
  }

  async getMedia(mediaId: string): Promise<Blob> {
    const response = await this.fetcher(
      `${this.baseUrl}/internal/media/${encodeURIComponent(mediaId)}`,
      { headers: this.headers() },
    );
    if (!response.ok) {
      throw await this.errorFrom(response);
    }
    return response.blob();
  }

  sendPhotoReminder(
    caseId: string,
    mediaId: string,
    reminderId: string,
    idempotencyKey: string,
  ): Promise<{ voiceMessageId: string; messageId: string; mediaId: string }> {
    return this.request(
      `/internal/cases/${encodeURIComponent(caseId)}/send-photo-reminder`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({ mediaId, reminderId }),
      },
    );
  }

  recordOutcome(
    eventId: string,
    outcome: ReviewOutcome,
    reviewerId: string,
    note: string | null,
    idempotencyKey: string,
  ): Promise<{ data: { outcomeId: string; outcome: ReviewOutcome; recordedAt: string } }> {
    return this.request(`/internal/review-events/${encodeURIComponent(eventId)}/outcomes`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ eventVersion: 1, outcome, reviewerId, note }),
    });
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = this.headers(init.headers);
    if (init.body instanceof FormData) {
      headers.delete("Content-Type");
    }
    const response = await this.fetcher(`${this.baseUrl}${path}`, {
      ...init,
      headers,
    });
    if (!response.ok) {
      throw await this.errorFrom(response);
    }
    return response.json() as Promise<T>;
  }

  private headers(extra: HeadersInit = {}): Headers {
    const headers = new Headers(extra);
    if (this.token) headers.set("Authorization", `Bearer ${this.token}`);
    headers.set("Accept", "application/json");
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    return headers;
  }

  private async errorFrom(response: Response): Promise<HawlakApiError> {
    let code = `request_failed_${response.status}`;
    try {
      const body = (await response.json()) as { error?: string; detail?: string };
      code = body.error ?? body.detail ?? code;
    } catch {
      // Provider and credential details are intentionally not surfaced in the UI.
    }
    return new HawlakApiError(response.status, code);
  }
}
