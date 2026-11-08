import { z } from "zod";

/**
 * Response shapes for the dashboard's non-event routes, taken from
 * docs/integration-contract.md and apps/api/app/schemas. Review events are
 * validated with the shared PharmacistReviewRequestedSchema instead.
 *
 * Objects are not strict: Haya may add optional fields without breaking us.
 */

export const OUTCOMES = ["matched", "mismatch_found", "unclear_photo", "contact_patient"] as const;
export type Outcome = (typeof OUTCOMES)[number];

const checksum = z.string().regex(/^sha256:[0-9a-f]{64}$/, "expected sha256:<64 hex>");

export const VoiceOptionsSchema = z.object({
  dialects: z
    .array(
      z.object({
        code: z.string().min(1),
        labelAr: z.string().min(1),
        labelEn: z.string().min(1),
      }),
    )
    .min(1),
  voice: z.object({
    provider: z.string(),
    voiceLabel: z.string(),
    modelId: z.string(),
    languageCode: z.string(),
  }),
});
export type VoiceOptions = z.infer<typeof VoiceOptionsSchema>;
export type DialectOption = VoiceOptions["dialects"][number];

export const CaseResponseSchema = z.object({
  caseId: z.string().min(1),
  planId: z.string().min(1),
  version: z.number().int(),
  status: z.string(),
});
export type CaseResponse = z.infer<typeof CaseResponseSchema>;

export const FactDifferenceSchema = z.object({
  path: z.string(),
  kind: z.string(),
  source: z.unknown(),
  output: z.unknown(),
});
export type FactDifference = z.infer<typeof FactDifferenceSchema>;

export const GeneratedScriptSchema = z.object({
  artifactId: z.string().min(1),
  caseId: z.string().min(1),
  spokenTextAr: z.string().min(1),
  scriptChecksum: checksum,
  factReport: z.object({
    passed: z.boolean(),
    differences: z.array(FactDifferenceSchema),
  }),
});
export type GeneratedScript = z.infer<typeof GeneratedScriptSchema>;

export const ApproveResponseSchema = z.object({
  artifactId: z.string().min(1),
  caseId: z.string().min(1),
  scriptChecksum: z.string(),
  audioChecksum: z.string(),
  messageIds: z.array(z.string()),
});
export type ApproveResponse = z.infer<typeof ApproveResponseSchema>;

/** Only the envelope is checked here; each item is validated by the queue. */
export const ReviewPageSchema = z.object({
  data: z.array(z.unknown()),
  nextCursor: z.string().nullable(),
});
export type ReviewPage = z.infer<typeof ReviewPageSchema>;

export const OutcomeResponseSchema = z.object({
  data: z.object({
    outcomeId: z.string().min(1),
    eventId: z.string().min(1),
    eventVersion: z.number().int(),
    outcome: z.enum(OUTCOMES),
    reviewerId: z.string(),
    note: z.string().nullable(),
    recordedAt: z.string(),
  }),
});
export type RecordedOutcome = z.infer<typeof OutcomeResponseSchema>["data"];

export interface ApproveRequest {
  artifactId: string;
  scriptChecksum: string;
  approvedBy: string;
}

export interface OutcomeRequest {
  eventVersion: 1;
  outcome: Outcome;
  reviewerId: string;
  note: string | null;
}

/** Turn validation issues into short, readable lines for the UI. */
export function issuesToText(error: z.ZodError): string[] {
  return error.issues.map((issue) => {
    const path = issue.path.map((part) => String(part)).join(".");
    return `${path || "(الجذر)"}: ${issue.message}`;
  });
}
