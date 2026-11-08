import { afterEach, describe, expect, it, vi } from "vitest";

import { OfflineMediaError } from "../lib/errors";
import { flush, render, type Rendered } from "../test/dom";
import { MedicinePhoto, type MediaLoader, type ObjectUrlApi } from "./MedicinePhoto";

let view: Rendered | null = null;
afterEach(async () => {
  await view?.unmount();
  view = null;
});

function fakeUrls() {
  let n = 0;
  const urls: ObjectUrlApi = {
    create: vi.fn(() => `blob:test-${++n}`),
    revoke: vi.fn(),
  };
  return urls;
}

describe("MedicinePhoto", () => {
  it("shows the photo from an object URL and revokes it on unmount", async () => {
    const urls = fakeUrls();
    const load = vi.fn<MediaLoader>(async () => new Blob(["x"], { type: "image/jpeg" }));
    view = await render(<MedicinePhoto mediaId="media_01" index={1} load={load} urls={urls} />);
    await flush();

    expect(load).toHaveBeenCalledTimes(1);
    expect(view.container.querySelector("img")?.getAttribute("src")).toBe("blob:test-1");

    await view.unmount();
    view = null;
    expect(urls.revoke).toHaveBeenCalledWith("blob:test-1");
  });

  it("revokes the old URL when the photo changes", async () => {
    const urls = fakeUrls();
    const load = vi.fn<MediaLoader>(async () => new Blob(["x"]));
    view = await render(<MedicinePhoto mediaId="media_01" index={1} load={load} urls={urls} />);
    await flush();
    await view.rerender(<MedicinePhoto mediaId="media_02" index={1} load={load} urls={urls} />);
    await flush();

    expect(urls.revoke).toHaveBeenCalledWith("blob:test-1");
    expect(view.container.querySelector("img")?.getAttribute("src")).toBe("blob:test-2");
  });

  it("aborts an unfinished download and creates no URL after unmount", async () => {
    const urls = fakeUrls();
    let signal: AbortSignal | null = null;
    let finish: (blob: Blob) => void = () => {};
    const load = vi.fn<MediaLoader>((_id, s) => {
      signal = s;
      return new Promise<Blob>((resolve) => {
        finish = resolve;
      });
    });
    view = await render(<MedicinePhoto mediaId="media_01" index={1} load={load} urls={urls} />);
    await view.unmount();
    view = null;

    expect((signal as AbortSignal | null)?.aborted).toBe(true);
    finish(new Blob(["late"]));
    await flush();
    expect(urls.create).toHaveBeenCalledTimes(0);
  });

  it("explains when photos are unavailable offline", async () => {
    const load = vi.fn<MediaLoader>(async () => {
      throw new OfflineMediaError();
    });
    view = await render(<MedicinePhoto mediaId="media_01" index={2} load={load} urls={fakeUrls()} />);
    await flush();
    expect(view.container.textContent).toContain("الصور متاحة فقط عند الاتصال بالخادم");
    expect(view.container.querySelector("img")).toBeNull();
  });
});
