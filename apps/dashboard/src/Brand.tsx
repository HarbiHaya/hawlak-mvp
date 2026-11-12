export function HawlakMark({ tone = "blue" }: { tone?: "blue" | "white" | "ink" }) {
  return <svg className={`hawlak-mark hawlak-mark--${tone}`} viewBox="0 0 48 48" aria-hidden="true"><path d="M40.31 16.39 A18 18 0 1 1 31.61 7.69" /><circle cx="24" cy="24" r="6.4" /></svg>;
}

export function HawlakLogo({ inverse = false }: { inverse?: boolean }) {
  return <div className={`hawlak-logo${inverse ? " hawlak-logo--inverse" : ""}`} aria-label="حولك"><HawlakMark tone={inverse ? "white" : "blue"} /><span>حولك</span></div>;
}
