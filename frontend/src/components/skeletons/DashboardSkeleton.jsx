import Skeleton from '../ui/Skeleton';

export default function DashboardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading page">
      {/* Stat cards row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} variant="rect" className="h-20 rounded-lg" />
        ))}
      </div>

      {/* Main content area */}
      <Skeleton variant="rect" className="h-64 rounded-lg" />
    </div>
  );
}
