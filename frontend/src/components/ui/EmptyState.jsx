import { Link } from 'react-router-dom';

export default function EmptyState({
  icon,
  title,
  description,
  primaryAction,
  secondaryAction,
  stats,
  preview,
}) {
  return (
    <div className="mx-auto max-w-md py-16 text-center">
      {icon && (
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center text-slate-600">
          {icon}
        </div>
      )}

      {title && (
        <h2 className="mb-2 text-center text-lg font-medium text-slate-300">
          {title}
        </h2>
      )}

      {description && (
        <p className="mx-auto mb-6 max-w-sm text-center text-sm leading-relaxed text-slate-500">
          {description}
        </p>
      )}

      {stats && stats.length > 0 && (
        <div className="mb-6 flex justify-center gap-8">
          {stats.map((stat) => (
            <div key={stat.label}>
              <div className="text-lg font-semibold text-amber-400">
                {stat.value}
              </div>
              <div className="text-xs uppercase tracking-wider text-slate-500">
                {stat.label}
              </div>
            </div>
          ))}
        </div>
      )}

      {preview && (
        <div className="mb-6 rounded-xl border border-dashed border-slate-700/50 p-4 opacity-60">
          {preview}
        </div>
      )}

      {primaryAction && (
        <div>
          {primaryAction.to ? (
            <Link
              to={primaryAction.to}
              className="inline-flex items-center justify-center rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-slate-950 transition-colors hover:bg-amber-400"
            >
              {primaryAction.label}
            </Link>
          ) : (
            <button
              onClick={primaryAction.onClick}
              className="inline-flex items-center justify-center rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-slate-950 transition-colors hover:bg-amber-400"
            >
              {primaryAction.label}
            </button>
          )}
        </div>
      )}

      {secondaryAction && (
        <div className="mt-3">
          {secondaryAction.to ? (
            <Link
              to={secondaryAction.to}
              className="text-sm text-slate-400 transition-colors hover:text-slate-300"
            >
              {secondaryAction.label}
            </Link>
          ) : (
            <button
              onClick={secondaryAction.onClick}
              className="text-sm text-slate-400 transition-colors hover:text-slate-300"
            >
              {secondaryAction.label}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
