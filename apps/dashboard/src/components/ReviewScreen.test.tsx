import { afterEach, describe, expect, it, vi } from "vitest";

import type { ReviewQueueHandle } from "../hooks/useReviewQueue";
import { DEMO_REVIEW_EVENT } from "../lib/demoCase";
import { applyPage, initialQueueState, sortedTasks, type QueueState } from "../lib/queue";
import { flush, render, type Rendered } from "../test/dom";
import type { MediaLoader } from "./MedicinePhoto";
import { ReviewScreen } from "./ReviewScreen";

let view: Rendered | null = null;
afterEach(async () => {
  await view?.unmount();
  view = null;
});

function handle(state: QueueState, overrides: Partial<ReviewQueueHandle> = {}): ReviewQueueHandle {
  return {
    state,
    tasks: sortedTasks(state),
    sync: { phase: "ok", error: null, unauthorized: false },
    refresh: vi.fn(),
    markReviewed: vi.fn(),
    ...overrides,
  };
}

const loadMedia: MediaLoader = async () => new Blob(["x"]);
const submit = () => async () => {
  throw new Error("not used");
};

describe("ReviewScreen", () => {
  it("shows the review task details for the pharmacist", async () => {
    const state = applyPage(initialQueueState, { data: [DEMO_REVIEW_EVENT], nextCursor: "c1" }, "2026-11-08T10:00:00Z");
    view = await render(<ReviewScreen queue={handle(state)} loadMedia={loadMedia} submitOutcome={submit} offline={false} />);
    await flush();

    const text = view.container.textContent ?? "";
    expect(text).toContain("أبو محمد");
    expect(text).toContain("+9665*****123");
    expect(text).toContain("plan_01");
    expect(text).toContain("الصور 3 من 3");
    expect(view.container.querySelectorAll(".photo")).toHaveLength(3);
  });

  it("shows contract violations instead of crashing", async () => {
    const bad = { ...(DEMO_REVIEW_EVENT as object), eventId: "evt_bad", eventVersion: 2 };
    const state = applyPage(initialQueueState, { data: [bad], nextCursor: null }, "2026-11-08T10:00:00Z");
    view = await render(<ReviewScreen queue={handle(state)} loadMedia={loadMedia} submitOutcome={submit} offline={false} />);

    const text = view.container.textContent ?? "";
    expect(text).toContain("لا تطابق العقد");
    expect(text).toContain("evt_bad");
    expect(text).toContain("لا توجد طلبات مراجعة بعد");
  });

  it("shows loading, then a polling error, without losing tasks", async () => {
    const loading = handle(initialQueueState, { sync: { phase: "loading", error: null, unauthorized: false } });
    view = await render(<ReviewScreen queue={loading} loadMedia={loadMedia} submitOutcome={submit} offline={false} />);
    expect(view.container.textContent).toContain("جارٍ تحميل قائمة المراجعة");

    const state = applyPage(initialQueueState, { data: [DEMO_REVIEW_EVENT], nextCursor: "c1" }, "2026-11-08T10:00:00Z");
    const failing = handle(state, { sync: { phase: "error", error: "تعذّر الوصول إلى الخادم.", unauthorized: false } });
    await view.rerender(<ReviewScreen queue={failing} loadMedia={loadMedia} submitOutcome={submit} offline={false} />);
    expect(view.container.textContent).toContain("تعذّر تحديث القائمة");
    expect(view.container.textContent).toContain("أبو محمد");
  });
});
