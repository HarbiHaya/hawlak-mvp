import { afterEach, describe, expect, it, vi } from "vitest";

import type { RecordedReview } from "../lib/queue";
import { byText, click, flush, render, typeInto, type Rendered } from "../test/dom";
import { OutcomePanel, type SubmitOutcome } from "./OutcomePanel";

const recorded: RecordedReview = {
  outcomeId: "outcome_01",
  outcome: "mismatch_found",
  reviewerId: "demo-pharmacist-01",
  note: "Wrong strength",
  recordedAt: "2026-11-04T12:00:00Z",
  simulated: false,
};

let view: Rendered | null = null;
afterEach(async () => {
  await view?.unmount();
  view = null;
});

const confirmButton = (c: HTMLElement) => c.querySelector<HTMLButtonElement>('[data-testid="confirm-outcome"]');
const choice = (c: HTMLElement, outcome: string) => c.querySelector(`[data-outcome="${outcome}"]`);

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("OutcomePanel", () => {
  it("keeps confirm disabled, with a reason, until an outcome is chosen", async () => {
    const submit = vi.fn<SubmitOutcome>(async () => recorded);
    view = await render(<OutcomePanel review={null} onSubmit={submit} />);
    expect(confirmButton(view.container)?.disabled).toBe(true);
    expect(view.container.textContent).toContain("اختر نتيجة المراجعة أولًا");

    await click(choice(view.container, "matched"));
    expect(confirmButton(view.container)?.disabled).toBe(false);
    expect(submit).toHaveBeenCalledTimes(0);
  });

  it("submits once even when confirm is clicked twice quickly", async () => {
    const pending = deferred<RecordedReview>();
    const submit = vi.fn<SubmitOutcome>(() => pending.promise);
    view = await render(<OutcomePanel review={null} onSubmit={submit} />);

    await click(choice(view.container, "matched"));
    const button = confirmButton(view.container);
    await click(button);
    await click(button);
    expect(submit).toHaveBeenCalledTimes(1);
    expect(submit.mock.calls[0][0]).toMatchObject({ outcome: "matched", reviewerId: "demo-pharmacist-01", note: null });
    expect(submit.mock.calls[0][0].idempotencyKey.startsWith("review-")).toBe(true);
    pending.resolve(recorded);
    await flush();
  });

  it("reuses the key for a retry of the same decision, and uses a new key when it changes", async () => {
    const submit = vi.fn<SubmitOutcome>(async () => {
      throw new TypeError("offline");
    });
    view = await render(<OutcomePanel review={null} onSubmit={submit} />);

    await click(choice(view.container, "unclear_photo"));
    await click(confirmButton(view.container));
    await flush();
    expect(view.container.textContent).toContain("لم يُسجَّل القرار");

    await click(confirmButton(view.container));
    await flush();
    const [first, second] = submit.mock.calls.map((call) => call[0].idempotencyKey);
    expect(second).toBe(first);

    await typeInto(view.container.querySelector("textarea"), "Box 2 is blurry");
    await click(confirmButton(view.container));
    await flush();
    const third = submit.mock.calls[2][0];
    expect(third.note).toBe("Box 2 is blurry");
    expect(third.idempotencyKey).not.toBe(first);
  });

  it("shows the recorded decision and no longer offers the controls", async () => {
    const submit = vi.fn<SubmitOutcome>(async () => recorded);
    view = await render(<OutcomePanel review={recorded} onSubmit={submit} />);
    expect(view.container.textContent).toContain("يوجد اختلاف");
    expect(view.container.textContent).toContain("Wrong strength");
    expect(confirmButton(view.container)).toBeNull();
    expect(byText(view.container, "button", "مطابقة للخطة")).toBeNull();
  });
});
