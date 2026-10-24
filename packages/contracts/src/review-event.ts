import { z } from "zod";

export const PharmacistReviewRequestedSchema = z.object({
  eventId: z.string().min(1),
  eventType: z.literal("pharmacist_review_requested"),
  eventVersion: z.literal(1),
  idempotencyKey: z.string().min(1),
  occurredAt: z.string().datetime(),
  case: z.object({
    caseId: z.string().min(1),
    patientAlias: z.string().min(1),
    phoneE164Masked: z.string().min(1),
    expectedBoxCount: z.number().int().positive(),
    receivedBoxCount: z.number().int().nonnegative(),
  }),
  approvedPlan: z.object({
    planId: z.string().min(1),
    version: z.number().int().positive(),
    sourceHash: z.string().min(1),
  }),
  medicinePhotos: z.array(
    z.object({
      mediaId: z.string().min(1),
      objectKey: z.string().min(1),
    }),
  ),
  reviewReason: z.enum(["expected_photo_count_reached", "patient_marked_done"]),
});

export type PharmacistReviewRequested = z.infer<
  typeof PharmacistReviewRequestedSchema
>;

