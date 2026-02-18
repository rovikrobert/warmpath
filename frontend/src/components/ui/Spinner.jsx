const SIZES = {
  sm: 'h-4 w-4 border-2',
  md: 'h-6 w-6 border-[3px]',
  lg: 'h-8 w-8 border-4',
};

export default function Spinner({ size = 'md', className = '' }) {
  return (
    <div
      className={`animate-spin rounded-full border-amber-500 border-t-transparent ${SIZES[size]} ${className}`}
      role="status"
      aria-label="Loading"
    />
  );
}
