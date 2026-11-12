// The dealt "dots" mark beside the Amira name (taste-skill), used by the landing and the redesigned pages.
export function LpMark() {
  return (
    <svg aria-hidden="true" className="lp-mark" viewBox="0 0 24 24">
      <circle cx="6" cy="6" r="3" />
      <circle cx="18" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="18" cy="18" r="3" fill="var(--lp-action)" />
    </svg>
  );
}
