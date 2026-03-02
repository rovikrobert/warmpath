import Spinner from './ui/Spinner';

export default function RouteLoadingFallback() {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-4 bg-background">
      <div className="flex items-center gap-2">
        <span className="text-xl font-bold text-primary">~</span>
        <span className="text-lg font-bold text-foreground">WarmPath</span>
      </div>
      <Spinner size="lg" />
      <p className="text-sm text-muted-foreground animate-pulse">Loading...</p>
    </div>
  );
}
