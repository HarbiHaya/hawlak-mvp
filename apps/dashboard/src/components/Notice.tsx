import type { ReactNode } from "react";

import type { Tone } from "../lib/format";

export function Notice({
  tone = "grey",
  title,
  children,
  role,
}: {
  tone?: Tone;
  title?: string;
  children?: ReactNode;
  role?: "alert" | "status";
}) {
  return (
    <div className={`notice notice--${tone}`} role={role}>
      {title ? <div className="notice__title">{title}</div> : null}
      {children ? <div className="notice__body">{children}</div> : null}
    </div>
  );
}

export function Chip({ tone = "grey", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`chip chip--${tone}`}>{children}</span>;
}

export function Spinner({ label }: { label: string }) {
  return (
    <span className="spinner" role="status">
      <span className="spinner__dot" aria-hidden="true" />
      {label}
    </span>
  );
}
