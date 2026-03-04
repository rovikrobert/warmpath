import keevsBase from '../assets/avatars/keevs-base.png';
import keevsThinking from '../assets/avatars/keevs-thinking.png';
import keevsCelebrating from '../assets/avatars/keevs-celebrating.png';

const moodAssets = {
  default: keevsBase,
  thinking: keevsThinking,
  celebrating: keevsCelebrating,
} as const;

interface KeevsAvatarProps {
  size?: 'sm' | 'md' | 'lg' | 'xl' | number;
  mood?: keyof typeof moodAssets;
  pulse?: boolean;
  className?: string;
}

export default function KeevsAvatar({ size = 'md', mood = 'default', pulse = false, className = '' }: KeevsAvatarProps) {
  const sizes: Record<string, number> = { sm: 24, md: 40, lg: 64, xl: 96 };
  const px = typeof size === 'number' ? size : (sizes[size] || 40);

  return (
    <div
      className={`relative inline-flex items-center justify-center ${pulse ? 'animate-pulse-slow' : ''} ${className}`}
      style={{ width: px, height: px }}
      aria-hidden="true"
    >
      <img
        src={moodAssets[mood]}
        alt="Keevs, your AI career coach"
        width={px}
        height={px}
        className="rounded-full object-cover"
        draggable={false}
        onError={(e) => {
          console.error('Failed to load Keevs avatar:', mood);
          e.currentTarget.style.display = 'none';
        }}
      />
    </div>
  );
}
