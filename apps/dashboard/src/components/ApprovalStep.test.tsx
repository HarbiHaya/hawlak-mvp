import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApproveRequest, ApproveResponse } from "../lib/schemas";
import { byText, click, flush, render, type Rendered } from "../test/dom";
import { ApprovalStep } from "./ApprovalStep";

const CHECKSUM = `sha256:${"b".repeat(64)}`;
const response: ApproveResponse = {
  artifactId: "art_1",
  caseId: "case_01-najdi",
  scriptChecksum: CHECKSUM,
  audioChecksum: `sha256:${"c".repeat(64)}`,
  messageIds: ["wamid.1", "wamid.2", "wamid.3"],
};

type Approve = (body: ApproveRequest, key: string) => Promise<ApproveResponse>;

let view: Rendered | null = null;
afterEach(async () => {
  await view?.unmount();
  view = null;
});

const approveButton = (c: HTMLElement) => byText(c, "button", "اعتماد النص") as HTMLButtonElement | null;
const checkbox = (c: HTMLElement) => c.querySelector<HTMLInputElement>('input[type="checkbox"]');

describe("ApprovalStep", () => {
  it("never approves on its own and stays disabled until the operator acknowledges", async () => {
    const onApprove = vi.fn<Approve>(async () => response);
    view = await render(<ApprovalStep artifactId="art_1" scriptChecksum={CHECKSUM} factPassed onApprove={onApprove} />);
    await flush();

    expect(onApprove).toHaveBeenCalledTimes(0);
    expect(approveButton(view.container)?.disabled).toBe(true);
    expect(view.container.textContent).toContain("أكّد الإقرار");

    await click(approveButton(view.container));
    expect(onApprove).toHaveBeenCalledTimes(0);
  });

  it("sends the exact artifact id and checksum once, with a fresh key per click", async () => {
    let calls = 0;
    const onApprove = vi.fn<Approve>(async () => {
      calls += 1;
      if (calls === 1) throw new TypeError("network down");
      return response;
    });
    view = await render(<ApprovalStep artifactId="art_1" scriptChecksum={CHECKSUM} factPassed onApprove={onApprove} />);

    await click(checkbox(view.container));
    await click(approveButton(view.container));
    await flush();
    expect(view.container.textContent).toContain("لم يكتمل الاعتماد");

    await click(approveButton(view.container));
    await flush();

    expect(onApprove).toHaveBeenCalledTimes(2);
    const [body, firstKey] = onApprove.mock.calls[0];
    expect(body).toEqual({ artifactId: "art_1", scriptChecksum: CHECKSUM, approvedBy: "demo-operator-01" });
    expect(onApprove.mock.calls[1][1]).not.toBe(firstKey);
    expect(view.container.textContent).toContain("تم الاعتماد والإرسال");
    expect(view.container.textContent).toContain("wamid.3");
    expect(approveButton(view.container)?.disabled).toBe(true);
  });

  it("blocks approval when the clinical fact check did not pass", async () => {
    const onApprove = vi.fn<Approve>(async () => response);
    view = await render(<ApprovalStep artifactId="art_1" scriptChecksum={CHECKSUM} factPassed={false} onApprove={onApprove} />);
    expect(checkbox(view.container)?.disabled).toBe(true);
    expect(approveButton(view.container)?.disabled).toBe(true);
    expect(view.container.textContent).toContain("فحص الحقائق السريرية لم ينجح");
  });
});
