import Spinner from './Spinner';

const VARIANTS = {
  primary: 'bg-amber-500 text-white hover:bg-amber-400',
  secondary: 'border border-slate-700/50 text-slate-300 hover:bg-slate-800 hover:text-slate-100',
  ghost: 'text-slate-400 hover:text-slate-200 hover:bg-slate-800',
  danger: 'bg-red-500/10 text-red-400 hover:bg-red-500/20',
};

const SIZES = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
  lg: 'px-6 py-2.5 text-sm',
};

export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  className = '',
  children,
  ...rest
}) {
  return (
    <button
      className={`inline-flex items-center justify-center font-medium rounded-lg transition-colors active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Spinner size="sm" className="mr-2" />}
      {children}
    </button>
  );
}
