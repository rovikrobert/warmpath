const COLORS = {
  amber: 'bg-amber-500/10 text-amber-400',
  emerald: 'bg-emerald-500/10 text-emerald-400',
  red: 'bg-red-500/10 text-red-400',
  blue: 'bg-blue-500/10 text-blue-400',
  purple: 'bg-purple-500/10 text-purple-400',
  slate: 'bg-slate-700/50 text-slate-400',
  cyan: 'bg-cyan-500/10 text-cyan-400',
  indigo: 'bg-indigo-500/10 text-indigo-400',
  teal: 'bg-teal-500/10 text-teal-400',
  green: 'bg-emerald-500/10 text-emerald-400',
};

const SIZES = {
  sm: 'px-1.5 py-0.5 text-xs',
  md: 'px-2 py-0.5 text-xs',
};

export default function Badge({
  color = 'slate',
  size = 'md',
  variant = 'filled',
  className = '',
  children,
}) {
  const colorClass = COLORS[color] || COLORS.slate;
  const borderClass = variant === 'outline' ? 'border border-current/20' : '';
  return (
    <span className={`inline-flex items-center rounded-full font-medium ${colorClass} ${SIZES[size]} ${borderClass} ${className}`}>
      {children}
    </span>
  );
}
