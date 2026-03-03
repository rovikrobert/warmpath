import { useEffect, useState } from 'react';
import Spinner from './ui/Spinner';

export default function RouteLoadingFallback() {
  const [showHint, setShowHint] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setShowHint(true), 5000);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="flex h-screen flex-col items-center justify-center gap-4 bg-background">
      <div className="flex items-center gap-2">
        <span className="text-xl font-bold text-primary">~</span>
        <span className="text-lg font-bold text-foreground">WarmPath</span>
      </div>
      <Spinner size="lg" />
      <p className="text-sm text-muted-foreground animate-pulse">Loading...</p>
      {showHint && (
        <p className="mt-2 max-w-xs text-center text-xs text-muted-foreground animate-slide-up-fade-in">
          Taking longer than expected. Check the browser console for errors
          or verify your Clerk keys are correct for this domain.
        </p>
      )}
    </div>
  );
}
