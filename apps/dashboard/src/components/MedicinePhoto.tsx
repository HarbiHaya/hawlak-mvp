import { useEffect, useState } from "react";

import { isAbortError } from "../lib/api";
import { OfflineMediaError, describeError } from "../lib/errors";

export type MediaLoader = (mediaId: string, signal: AbortSignal) => Promise<Blob>;

export interface ObjectUrlApi {
  create: (blob: Blob) => string;
  revoke: (url: string) => void;
}

export const browserObjectUrls: ObjectUrlApi = {
  create: (blob) => URL.createObjectURL(blob),
  revoke: (url) => URL.revokeObjectURL(url),
};

type PhotoState =
  | { status: "loading" }
  | { status: "ready"; url: string }
  | { status: "error"; message: string; offline: boolean };

/**
 * Fetches one photo with the bearer token, shows it from an in-memory object
 * URL and revokes that URL when the photo changes or leaves the screen.
 * The photo is shown as-is; nothing interprets it.
 */
export function MedicinePhoto({
  mediaId,
  index,
  load,
  urls = browserObjectUrls,
}: {
  mediaId: string;
  index: number;
  load: MediaLoader;
  urls?: ObjectUrlApi;
}) {
  const [state, setState] = useState<PhotoState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [zoomed, setZoomed] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    let url: string | null = null;
    let active = true;
    setState({ status: "loading" });
    load(mediaId, ctrl.signal)
      .then((blob) => {
        if (!active) return;
        url = urls.create(blob);
        setState({ status: "ready", url });
      })
      .catch((err: unknown) => {
        if (!active || isAbortError(err)) return;
        setState({ status: "error", message: describeError(err), offline: err instanceof OfflineMediaError });
      });
    return () => {
      active = false;
      ctrl.abort();
      if (url) urls.revoke(url);
    };
  }, [mediaId, load, urls, attempt]);

  useEffect(() => {
    if (!zoomed) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setZoomed(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoomed]);

  const caption = `صورة ${index}`;

  return (
    <figure className="photo">
      <div className="photo__frame">
        {state.status === "loading" ? <div className="photo__placeholder">جارٍ تحميل الصورة…</div> : null}
        {state.status === "error" ? (
          <div className={`photo__placeholder ${state.offline ? "" : "photo__placeholder--error"}`}>
            <span>{state.message}</span>
            {!state.offline ? (
              <button className="link" type="button" onClick={() => setAttempt((n) => n + 1)}>
                إعادة المحاولة
              </button>
            ) : null}
          </div>
        ) : null}
        {state.status === "ready" ? (
          <button className="photo__open" type="button" onClick={() => setZoomed(true)} aria-label={`تكبير ${caption}`}>
            <img src={state.url} alt={`${caption} — علبة دواء أرسلها المريض`} />
          </button>
        ) : null}
      </div>
      <figcaption className="photo__caption">
        <span>{caption}</span>
        <code dir="ltr">{mediaId}</code>
      </figcaption>

      {zoomed && state.status === "ready" ? (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label={caption} onClick={() => setZoomed(false)}>
          <img src={state.url} alt={caption} />
          <button className="btn btn--secondary lightbox__close" type="button" onClick={() => setZoomed(false)}>
            إغلاق
          </button>
        </div>
      ) : null}
    </figure>
  );
}
