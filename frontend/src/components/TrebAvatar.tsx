import trebBase from '../assets/avatars/treb-base.webp';
import trebThinking from '../assets/avatars/treb-thinking.webp';
import trebCelebrating from '../assets/avatars/treb-celebrating.webp';

const moodAssets = {
  default: trebBase,
  thinking: trebThinking,
  celebrating: trebCelebrating,
} as const;

interface TrebAvatarProps {
  size?: 'sm' | 'md' | 'lg' | 'xl' | number;
  mood?: keyof typeof moodAssets;
  pulse?: boolean;
  className?: string;
}

export default function TrebAvatar({ size = 'md', mood = 'default', pulse = false, className = '' }: TrebAvatarProps) {
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
        alt="Treb, your AI network partner"
        width={px}
        height={px}
        className="rounded-full object-cover"
        draggable={false}
        onError={(e) => {
          console.error('Failed to load Treb avatar:', mood);
          e.currentTarget.style.display = 'none';
        }}
      />
    </div>
  );
}
