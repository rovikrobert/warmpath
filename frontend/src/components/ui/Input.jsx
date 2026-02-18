import { forwardRef } from 'react';

const Input = forwardRef(function Input({ label, error, id, className = '', ...rest }, ref) {
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);
  const borderClass = error
    ? 'border-red-400 focus:border-red-400 focus:ring-1 focus:ring-red-400'
    : 'border-slate-700/50 focus:border-amber-500 focus:ring-1 focus:ring-amber-500';

  return (
    <div>
      {label && (
        <label htmlFor={inputId} className="mb-1 block text-sm font-medium text-slate-300">
          {label}
        </label>
      )}
      <input
        ref={ref}
        id={inputId}
        className={`w-full rounded-lg border bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none disabled:opacity-50 transition-colors ${borderClass} ${className}`}
        {...rest}
      />
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  );
});

export default Input;

export const Textarea = forwardRef(function Textarea({ label, error, id, className = '', ...rest }, ref) {
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);
  const borderClass = error
    ? 'border-red-400 focus:border-red-400 focus:ring-1 focus:ring-red-400'
    : 'border-slate-700/50 focus:border-amber-500 focus:ring-1 focus:ring-amber-500';

  return (
    <div>
      {label && (
        <label htmlFor={inputId} className="mb-1 block text-sm font-medium text-slate-300">
          {label}
        </label>
      )}
      <textarea
        ref={ref}
        id={inputId}
        className={`w-full rounded-lg border bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none disabled:opacity-50 transition-colors resize-none ${borderClass} ${className}`}
        {...rest}
      />
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  );
});

export const Select = forwardRef(function Select({ label, error, id, className = '', children, ...rest }, ref) {
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);
  const borderClass = error
    ? 'border-red-400 focus:border-red-400 focus:ring-1 focus:ring-red-400'
    : 'border-slate-700/50 focus:border-amber-500 focus:ring-1 focus:ring-amber-500';

  return (
    <div>
      {label && (
        <label htmlFor={inputId} className="mb-1 block text-sm font-medium text-slate-300">
          {label}
        </label>
      )}
      <select
        ref={ref}
        id={inputId}
        className={`w-full rounded-lg border bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:outline-none disabled:opacity-50 transition-colors ${borderClass} ${className}`}
        {...rest}
      >
        {children}
      </select>
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  );
});
