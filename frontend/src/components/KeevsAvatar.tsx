/**
 * Keevs — WarmPath's AI career coach avatar.
 *
 * A friendly, approachable character rendered as inline SVG so it works
 * everywhere (onboarding, coach page, KeevsBar, nav) without extra assets.
 *
 * Props:
 *   size  — "sm" (24px) | "md" (40px) | "lg" (64px) | "xl" (96px) | number
 *   pulse — boolean, adds a subtle glow animation
 *   className — extra wrapper classes
 */
interface KeevsAvatarProps {
  size?: 'sm' | 'md' | 'lg' | 'xl' | number;
  pulse?: boolean;
  className?: string;
}

export default function KeevsAvatar({ size = 'md', pulse = false, className = '' }: KeevsAvatarProps) {
  const sizes: Record<string, number> = { sm: 24, md: 40, lg: 64, xl: 96 };
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
        aria-label="Keevs, your AI career coach"
      >
        {/* Background circle — warm amber gradient */}
        <defs>
          <linearGradient id="keevs-bg" x1="0" y1="0" x2="120" y2="120" gradientUnits="userSpaceOnUse">
            <stop stopColor="#F59E0B" />
            <stop offset="1" stopColor="#D97706" />
          </linearGradient>
          <linearGradient id="keevs-face" x1="30" y1="30" x2="90" y2="100" gradientUnits="userSpaceOnUse">
            <stop stopColor="#FEF3C7" />
            <stop offset="1" stopColor="#FDE68A" />
          </linearGradient>
          <linearGradient id="keevs-spark" x1="0" y1="0" x2="20" y2="20" gradientUnits="userSpaceOnUse">
            <stop stopColor="#FCD34D" />
            <stop offset="1" stopColor="#FBBF24" />
          </linearGradient>
        </defs>

        {/* Outer circle */}
        <circle cx="60" cy="60" r="58" fill="url(#keevs-bg)" />
        <circle cx="60" cy="60" r="56" fill="#1E293B" />

        {/* Face — warm cream circle */}
        <circle cx="60" cy="64" r="32" fill="url(#keevs-face)" />

        {/* Eyes — friendly, slightly asymmetric for personality */}
        <ellipse cx="48" cy="60" rx="4.5" ry="5" fill="#1E293B" />
        <ellipse cx="72" cy="60" rx="4.5" ry="5" fill="#1E293B" />

        {/* Eye shine */}
        <circle cx="49.5" cy="58" r="1.8" fill="white" opacity="0.9" />
        <circle cx="73.5" cy="58" r="1.8" fill="white" opacity="0.9" />

        {/* Smile — warm, approachable curve */}
        <path
          d="M48 72 C52 78, 68 78, 72 72"
          stroke="#92400E"
          strokeWidth="2.5"
          strokeLinecap="round"
          fill="none"
        />

        {/* Cheeks — subtle warm blush */}
        <circle cx="42" cy="70" r="4" fill="#FBBF24" opacity="0.3" />
        <circle cx="78" cy="70" r="4" fill="#FBBF24" opacity="0.3" />

        {/* "Antenna" — neural network spark on top */}
        <circle cx="60" cy="26" r="6" fill="url(#keevs-spark)" />
        <line x1="60" y1="32" x2="60" y2="36" stroke="#FBBF24" strokeWidth="2" strokeLinecap="round" />

        {/* Spark rays */}
        <line x1="60" y1="18" x2="60" y2="14" stroke="#FCD34D" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="54" y1="22" x2="51" y2="19" stroke="#FCD34D" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="66" y1="22" x2="69" y2="19" stroke="#FCD34D" strokeWidth="1.5" strokeLinecap="round" />

        {/* Headphones — coach vibe */}
        <path
          d="M32 58 C32 42, 42 30, 60 30 C78 30, 88 42, 88 58"
          stroke="#F59E0B"
          strokeWidth="3"
          strokeLinecap="round"
          fill="none"
        />
        <rect x="26" y="54" width="10" height="14" rx="4" fill="#F59E0B" />
        <rect x="84" y="54" width="10" height="14" rx="4" fill="#F59E0B" />

        {/* Amber ring accent */}
        <circle cx="60" cy="60" r="56" stroke="#F59E0B" strokeWidth="1.5" fill="none" opacity="0.4" />
      </svg>
    </div>
  );
}
