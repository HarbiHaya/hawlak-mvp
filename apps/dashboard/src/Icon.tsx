import type { ReactNode } from "react";

const paths: Record<string, ReactNode> = {
  "layout-dashboard": <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="4" rx="1" /><rect x="14" y="11" width="7" height="10" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /></>,
  hospital: <><path d="M5 21V6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v15" /><path d="M3 21h18M9 9h6M12 6v6M9 21v-4h6v4" /></>,
  "file-plus-2": <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M12 18v-6M9 15h6" /></>,
  "briefcase-medical": <><path d="M12 11v4M10 13h4" /><path d="M8 6V4h8v2M4 6h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2Z" /></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
  "heart-handshake": <><path d="M12 20 4.8 13A4.8 4.8 0 0 1 12 6.7 4.8 4.8 0 0 1 19.2 13Z" /><path d="m8.5 12 2 2 5-5" /></>,
  languages: <><path d="m5 8 6 6M4 14l6-7M2 5h12M7 2v3M13 22l4-10 4 10M14.5 18h5" /></>,
  logout: <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" /></>,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 22a8 8 0 0 1 16 0" /></>,
  shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
  arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
};

export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return <svg className="product-icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.shield}</svg>;
}
