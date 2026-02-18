export default function Skeleton({ className = '', variant = 'text' }) {
  const base = 'animate-pulse rounded-lg bg-slate-800';
  const variants = {
    text: 'h-4 w-full',
    avatar: 'h-10 w-10 rounded-full',
    card: 'h-32 w-full',
    title: 'h-6 w-48',
  };
  return <div className={`${base} ${variants[variant]} ${className}`} />;
}
