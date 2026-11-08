/** Open-ring mark from the Hawlak identity kit. */
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <path
        d="M40.31 16.39 A18 18 0 1 1 31.61 7.69"
        fill="none"
        stroke="#2B66E4"
        strokeWidth="5.2"
        strokeLinecap="round"
      />
      <circle cx="24" cy="24" r="6.4" fill="#111418" />
    </svg>
  );
}
