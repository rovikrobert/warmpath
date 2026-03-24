export function WarmPathIcon({ size = 24, className = '' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M8 32 C8 32 12 20 20 20 C28 20 32 32 32 32"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M4 28 C4 28 12 12 20 12 C28 12 36 28 36 28"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
        opacity="0.5"
      />
      <circle cx="8" cy="32" r="3" fill="currentColor" />
      <circle cx="32" cy="32" r="3" fill="currentColor" opacity="0.8" />
    </svg>
  );
}

export function WarmPathLogo({ iconSize = 24, showText = true, className = '' }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <WarmPathIcon size={iconSize} className="text-primary" />
      {showText && <span className="text-lg font-bold text-foreground">WarmPath</span>}
    </span>
  );
}
