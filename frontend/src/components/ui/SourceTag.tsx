import Tooltip from './Tooltip';

interface SourceTagProps {
  source: string;
  label?: string;
  compact?: boolean;
}

export default function SourceTag({ source, label, compact = false }: SourceTagProps) {
  return (
    <Tooltip content={source} position="top">
      <span className="inline-flex cursor-help items-center gap-1 text-xs text-muted-foreground underline decoration-dotted underline-offset-2">
        {!compact && (
          <svg className="h-3 w-3 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m9.86-2.56a4.5 4.5 0 0 0-1.242-7.244l4.5-4.5a4.5 4.5 0 0 1 6.364 6.364l-1.757 1.757" />
          </svg>
        )}
        {label || 'Industry research'}
      </span>
    </Tooltip>
  );
}

export function UserDataTag() {
  return <span className="text-xs text-muted-foreground">(your data)</span>;
}
