import Tooltip from './Tooltip';

export default function SourceTag({ source, label }) {
  return (
    <Tooltip content={source} position="top">
      <span className="cursor-help text-xs text-slate-500 underline decoration-dotted underline-offset-2">
        {label || 'industry research'}
      </span>
    </Tooltip>
  );
}

export function UserDataTag() {
  return <span className="text-xs text-slate-500">(your data)</span>;
}
