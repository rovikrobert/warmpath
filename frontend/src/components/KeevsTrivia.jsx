import KeevsAvatar from './KeevsAvatar';
import SourceTag from './ui/SourceTag';

export default function KeevsTrivia({ triviaIdx, triviaFade, triviaPool, currentTrivia }) {
  const poolLength = triviaPool?.length || 0;

  return (
    <div className="mt-4 rounded-xl border border-amber-500/20 bg-slate-900/60 p-4" aria-live="polite">
      {/* Header row */}
      <div className="mb-3 flex items-center gap-2">
        <KeevsAvatar size="md" pulse={currentTrivia?.isGreeting} />
        <span className="text-sm font-medium text-amber-400">Keevs</span>
        <span className="text-xs text-slate-500">&mdash; while you wait</span>
      </div>

      {/* Trivia content with slide-up-fade animation */}
      <div
        key={triviaIdx}
        className={triviaFade ? 'animate-slide-up-fade-in' : 'opacity-0'}
      >
        <p className="text-sm leading-relaxed text-slate-200">{currentTrivia?.text}</p>
        {currentTrivia?.source && (
          <div className="mt-2">
            <SourceTag source={currentTrivia.source.source} label={currentTrivia.source.label} />
          </div>
        )}
      </div>

      {/* Dot progress indicator */}
      {triviaIdx !== -1 && poolLength > 0 && (
        <div className="mt-3 flex items-center gap-1.5">
          {Array.from({ length: poolLength }, (_, i) => (
            <div
              key={i}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                i === triviaIdx
                  ? 'w-4 bg-amber-500'
                  : 'w-1.5 bg-slate-700'
              }`}
            />
          ))}
        </div>
      )}
    </div>
  );
}
