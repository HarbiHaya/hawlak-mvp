import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactElement, type ReactNode } from "react";

import { Icon } from "./Icon";
import type { Locale } from "./i18n";

/* ---------- Toasts ---------- */

type ToastTone = "success" | "error" | "info";
interface Toast { id: number; tone: ToastTone; message: string }
interface ToastApi { notify: (message: string, tone?: ToastTone) => void }

const ToastContext = createContext<ToastApi>({ notify: () => undefined });
export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children, locale }: { children: ReactNode; locale: Locale }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const dismiss = useCallback((id: number) => setToasts((items) => items.filter((item) => item.id !== id)), []);
  const notify = useCallback((message: string, tone: ToastTone = "success") => {
    const id = nextId.current++;
    setToasts((items) => [...items.filter((item) => item.message !== message), { id, tone, message }].slice(-3));
    // Errors stay until dismissed so they are not missed.
    if (tone !== "error") window.setTimeout(() => dismiss(id), 4500);
  }, [dismiss]);
  return <ToastContext.Provider value={{ notify }}>
    {children}
    <div className="toasts" role="region" aria-label={locale === "ar" ? "الإشعارات" : "Notifications"}>
      <div aria-live="polite" className="sr-only">{toasts.filter((t) => t.tone !== "error").map((t) => t.message).join(". ")}</div>
      <div role="alert" className="sr-only">{toasts.filter((t) => t.tone === "error").map((t) => t.message).join(". ")}</div>
      {toasts.map((toast) => <div key={toast.id} className={`toast toast--${toast.tone}`}>
        <Icon name={toast.tone === "error" ? "alert" : toast.tone === "success" ? "check-circle" : "info"} size={16} />
        <div>{toast.message}</div>
        <button type="button" onClick={() => dismiss(toast.id)} aria-label={locale === "ar" ? "إغلاق" : "Dismiss"}><Icon name="x" size={14} /></button>
      </div>)}
    </div>
  </ToastContext.Provider>;
}

/* ---------- Dialog (native <dialog>: focus trap, Esc and inert background) ---------- */

export function Dialog({ open, title, children, footer, onClose }: { open: boolean; title: string; children: ReactNode; footer: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return <dialog ref={ref} className="dialog" aria-labelledby={titleId} onCancel={(event) => { event.preventDefault(); onClose(); }} onClick={(event) => { if (event.target === ref.current) onClose(); }}>
    {open && <>
      <div className="dialog__body"><h2 id={titleId}>{title}</h2>{children}</div>
      <div className="dialog__footer">{footer}</div>
    </>}
  </dialog>;
}

/* ---------- Tabs (WAI-ARIA tabs pattern with arrow-key navigation) ---------- */

export interface TabItem<T extends string> { id: T; label: string; state?: "done" | "todo" }

export function Tabs<T extends string>({ items, value, onChange, label, idPrefix, locale }: { items: TabItem<T>[]; value: T; onChange: (id: T) => void; label: string; idPrefix: string; locale: Locale }) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  function onKeyDown(event: KeyboardEvent) {
    const index = items.findIndex((item) => item.id === value);
    const forward = locale === "ar" ? "ArrowLeft" : "ArrowRight";
    const back = locale === "ar" ? "ArrowRight" : "ArrowLeft";
    let next = -1;
    if (event.key === forward) next = (index + 1) % items.length;
    if (event.key === back) next = (index - 1 + items.length) % items.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = items.length - 1;
    if (next < 0) return;
    event.preventDefault();
    onChange(items[next].id);
    refs.current[items[next].id]?.focus();
  }
  return <div className="tabs" role="tablist" aria-label={label} onKeyDown={onKeyDown}>
    {items.map((item) => <button key={item.id} ref={(node) => { refs.current[item.id] = node; }} type="button" role="tab" id={`${idPrefix}-tab-${item.id}`} aria-controls={`${idPrefix}-panel`} aria-selected={item.id === value} tabIndex={item.id === value ? 0 : -1} onClick={() => onChange(item.id)}>
      {item.label}
      {item.state && <span className={`tab-state tab-state--${item.state}`} role="img" aria-label={item.state === "done" ? (locale === "ar" ? "مكتمل" : "Complete") : (locale === "ar" ? "يتطلب إجراءً" : "Action required")}>{item.state === "done" && <Icon name="check" size={11} />}</span>}
    </button>)}
  </div>;
}

/* ---------- Segmented control ---------- */

export function Segmented<T extends string>({ options, value, onChange, label, block = false }: { options: Array<{ value: T; label: ReactNode }>; value: T; onChange: (value: T) => void; label: string; block?: boolean }) {
  return <div className={`segmented${block ? " segmented--block" : ""}`} role="group" aria-label={label}>
    {options.map((option) => <button key={option.value} type="button" aria-pressed={option.value === value} onClick={() => onChange(option.value)}>{option.label}</button>)}
  </div>;
}

/* ---------- Form field ---------- */

export function Field({ label, hint, error, optional, full, aside, children }: { label: ReactNode; hint?: ReactNode; error?: string | null; optional?: string; full?: boolean; aside?: ReactNode; children: (ids: { id: string; describedBy?: string; invalid: boolean }) => ReactElement }) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(" ") || undefined;
  return <div className={`field${full ? " field--full" : ""}`}>
    <span className="field__label"><label htmlFor={id}>{label}{optional && <span className="optional"> ({optional})</span>}</label>{aside}</span>
    {children({ id, describedBy, invalid: !!error })}
    {error ? <span id={errorId} className="field__error">{error}</span> : hint ? <span id={hintId} className="field__hint">{hint}</span> : null}
  </div>;
}

/* ---------- Small pieces ---------- */

export function Badge({ tone = "neutral", children, plain = false }: { tone?: "neutral" | "success" | "warning" | "danger" | "info"; children: ReactNode; plain?: boolean }) {
  return <span className={`badge badge--${tone}${plain ? " badge--plain" : ""}`}>{children}</span>;
}

export function EmptyState({ icon = "info", title, children, compact = false }: { icon?: string; title: string; children?: ReactNode; compact?: boolean }) {
  return <div className={`empty${compact ? " empty--compact" : ""}`}><span className="empty__icon"><Icon name={icon} size={20} /></span><h2>{title}</h2>{children}</div>;
}

export function Notice({ tone, children, icon }: { tone: "info" | "success" | "warning" | "danger" | "neutral"; children: ReactNode; icon?: string }) {
  const fallback = tone === "success" ? "check-circle" : tone === "info" || tone === "neutral" ? "info" : "alert";
  return <div className={`notice notice--${tone}`} role={tone === "danger" ? "alert" : undefined}><Icon name={icon ?? fallback} size={16} /><div>{children}</div></div>;
}

export function CopyButton({ value, locale }: { value: string; locale: Locale }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try { await navigator.clipboard.writeText(value); setCopied(true); window.setTimeout(() => setCopied(false), 2000); }
    catch { /* Clipboard can be blocked; the value stays selectable on screen. */ }
  }
  return <button type="button" className="button button--sm" onClick={() => void copy()}>
    <Icon name={copied ? "check" : "copy"} size={14} />{copied ? (locale === "ar" ? "تم النسخ" : "Copied") : (locale === "ar" ? "نسخ" : "Copy")}
  </button>;
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return <header className="page-header">
    <div><h1 tabIndex={-1} data-page-title>{title}</h1>{description && <p>{description}</p>}</div>
    {actions && <div className="page-header__actions">{actions}</div>}
  </header>;
}
