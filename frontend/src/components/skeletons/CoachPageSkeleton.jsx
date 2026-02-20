import Skeleton from '../ui/Skeleton';

export default function CoachPageSkeleton() {
  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col space-y-6 p-4" aria-busy="true" aria-label="Loading coach">
      {/* Keevs header */}
      <div className="flex items-center gap-3">
        <Skeleton variant="circle" width={48} height={48} />
        <div className="space-y-1.5">
          <Skeleton variant="text" className="w-32 h-5" />
          <Skeleton variant="text" className="w-48 h-3.5" />
        </div>
      </div>

      {/* Briefing card */}
      <Skeleton variant="rect" className="h-48 rounded-xl" />

      {/* Suggested prompts */}
      <div className="flex gap-2">
        <Skeleton variant="badge" className="w-28" />
        <Skeleton variant="badge" className="w-24" />
        <Skeleton variant="badge" className="w-32" />
      </div>

      {/* Chat input */}
      <div className="mt-auto">
        <Skeleton variant="rect" className="h-12 rounded-lg" />
      </div>
    </div>
  );
}
