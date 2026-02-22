/**
 * Treb — WarmPath's AI network partner avatar.
 *
 * A friendly, strategic character rendered as inline SVG. Teal/cyan color scheme
 * with network node visual (connecting lines instead of headphones).
 *
 * Props:
 *   size  — "sm" (24px) | "md" (40px) | "lg" (64px) | "xl" (96px) | number
 *   pulse — boolean, adds a subtle glow animation
 *   className — extra wrapper classes
 */
export default function TrebAvatar({ size = 'md', pulse = false, className = '' }) {
  const sizes = { sm: 24, md: 40, lg: 64, xl: 96 };
  const px = typeof size === 'number' ? size : (sizes[size] || 40);

  return (
    <div
      className={`relative inline-flex items-center justify-center ${pulse ? 'animate-pulse-slow' : ''} ${className}`}
      style={{ width: px, height: px }}
      aria-hidden="true"
    >
      <svg
        viewBox="0 0 120 120"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        width={px}
        height={px}
        role="img"
        aria-label="Treb, your AI network partner"
      >
        {/* Background circle — teal gradient */}
        <defs>
          <linearGradient id="treb-bg" x1="0" y1="0" x2="120" y2="120" gradientUnits="userSpaceOnUse">
            <stop stopColor="#14B8A6" />
            <stop offset="1" stopColor="#0D9488" />
          </linearGradient>
          <linearGradient id="treb-face" x1="30" y1="30" x2="90" y2="100" gradientUnits="userSpaceOnUse">
            <stop stopColor="#CCFBF1" />
            <stop offset="1" stopColor="#99F6E4" />
          </linearGradient>
          <linearGradient id="treb-node" x1="0" y1="0" x2="20" y2="20" gradientUnits="userSpaceOnUse">
            <stop stopColor="#5EEAD4" />
            <stop offset="1" stopColor="#2DD4BF" />
          </linearGradient>
        </defs>

        {/* Outer circle */}
        <circle cx="60" cy="60" r="58" fill="url(#treb-bg)" />
        <circle cx="60" cy="60" r="56" fill="#1E293B" />

        {/* Network connection lines — emanating from center */}
        <line x1="60" y1="32" x2="38" y2="20" stroke="#14B8A6" strokeWidth="1.5" strokeLinecap="round" opacity="0.6" />
        <line x1="60" y1="32" x2="82" y2="20" stroke="#14B8A6" strokeWidth="1.5" strokeLinecap="round" opacity="0.6" />
        <line x1="60" y1="32" x2="60" y2="14" stroke="#14B8A6" strokeWidth="1.5" strokeLinecap="round" opacity="0.6" />

        {/* Network nodes at endpoints */}
        <circle cx="38" cy="20" r="3.5" fill="url(#treb-node)" />
        <circle cx="82" cy="20" r="3.5" fill="url(#treb-node)" />
        <circle cx="60" cy="14" r="3.5" fill="url(#treb-node)" />

        {/* Face — warm teal-tinted circle */}
        <circle cx="60" cy="64" r="32" fill="url(#treb-face)" />

        {/* Eyes — friendly, slightly asymmetric */}
        <ellipse cx="48" cy="60" rx="4.5" ry="5" fill="#1E293B" />
        <ellipse cx="72" cy="60" rx="4.5" ry="5" fill="#1E293B" />

        {/* Eye shine */}
        <circle cx="49.5" cy="58" r="1.8" fill="white" opacity="0.9" />
        <circle cx="73.5" cy="58" r="1.8" fill="white" opacity="0.9" />

        {/* Smile — warm, approachable curve */}
        <path
          d="M48 72 C52 78, 68 78, 72 72"
          stroke="#115E59"
          strokeWidth="2.5"
          strokeLinecap="round"
          fill="none"
        />

        {/* Cheeks — subtle teal blush */}
        <circle cx="42" cy="70" r="4" fill="#2DD4BF" opacity="0.25" />
        <circle cx="78" cy="70" r="4" fill="#2DD4BF" opacity="0.25" />

        {/* Central hub node on top */}
        <circle cx="60" cy="28" r="5" fill="url(#treb-node)" />
        <line x1="60" y1="33" x2="60" y2="36" stroke="#2DD4BF" strokeWidth="2" strokeLinecap="round" />

        {/* Side connection arcs — network holder vibe */}
        <path
          d="M30 55 C30 40, 42 30, 60 30 C78 30, 90 40, 90 55"
          stroke="#14B8A6"
          strokeWidth="2.5"
          strokeLinecap="round"
          fill="none"
        />
        {/* Side nodes */}
        <circle cx="30" cy="55" r="4" fill="#14B8A6" />
        <circle cx="90" cy="55" r="4" fill="#14B8A6" />

        {/* Teal ring accent */}
        <circle cx="60" cy="60" r="56" stroke="#14B8A6" strokeWidth="1.5" fill="none" opacity="0.4" />
      </svg>
    </div>
  );
}
