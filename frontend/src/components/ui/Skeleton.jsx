export default function Skeleton({ className = '', variant = 'text', width, height }) {
  const base = 'animate-pulse bg-slate-800 rounded';

  const style = {};
  if (width) style.width = typeof width === 'number' ? `${width}px` : width;
  if (height) style.height = typeof height === 'number' ? `${height}px` : height;

  const variants = {
    text: 'h-4 w-full rounded',
    circle: 'rounded-full',
    rect: 'w-full rounded-lg',
    badge: 'h-5 w-16 rounded-full',
  };

  return (
    <div
      className={`${base} ${variants[variant] || variants.text} ${className}`}
      style={style}
    />
  );
}
