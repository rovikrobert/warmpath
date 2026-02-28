import { Link } from 'react-router-dom';
import SourceTag from './SourceTag';

interface EmptyStateAction {
  label: string;
  to?: string;
  onClick?: () => void;
}

interface EmptyStateStat {
  label: string;
  value: string | number;
}

interface EmptyStateProps {
  icon?: React.ReactNode;
  title?: string;
  description?: string;
  primaryAction?: EmptyStateAction;
  secondaryAction?: EmptyStateAction;
  stats?: EmptyStateStat[];
  statsSource?: string;
  preview?: React.ReactNode;
}

export default function EmptyState({
  icon,
  title,
  description,
  primaryAction,
  secondaryAction,
  stats,
  statsSource,
  preview,
}: EmptyStateProps) {
  return (
    <div className="mx-auto max-w-md py-16 text-center">
      {icon && (
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center text-muted-foreground">
          {icon}
        </div>
      )}

      {title && (
        <h2 className="mb-2 text-center text-lg font-medium text-secondary-foreground">
          {title}
        </h2>
      )}

      {description && (
        <p className="mx-auto mb-6 max-w-sm text-center text-sm leading-relaxed text-muted-foreground">
          {description}
        </p>
      )}

      {stats && stats.length > 0 && (
        <div className="mb-6">
          <div className="flex justify-center gap-8">
            {stats.map((stat) => (
              <div key={stat.label}>
                <div className="text-lg font-semibold text-primary">
                  {stat.value}
                </div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground">
                  {stat.label}
                </div>
              </div>
            ))}
          </div>
          {statsSource && (
            <div className="mt-2 text-center">
              <SourceTag source={statsSource} />
            </div>
          )}
        </div>
      )}

      {preview && (
        <div className="mb-6 rounded-xl border border-dashed border-border p-4 opacity-60">
          {preview}
        </div>
      )}

      {primaryAction && (
        <div>
          {primaryAction.to ? (
            <Link
              to={primaryAction.to}
              className="inline-flex items-center justify-center rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-background transition-colors hover:bg-primary/90"
            >
              {primaryAction.label}
            </Link>
          ) : (
            <button
              onClick={primaryAction.onClick}
              className="inline-flex items-center justify-center rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-background transition-colors hover:bg-primary/90"
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
              className="text-sm text-muted-foreground transition-colors hover:text-secondary-foreground"
            >
              {secondaryAction.label}
            </Link>
          ) : (
            <button
              onClick={secondaryAction.onClick}
              className="text-sm text-muted-foreground transition-colors hover:text-secondary-foreground"
            >
              {secondaryAction.label}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
