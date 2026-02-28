import Skeleton from '../ui/Skeleton';

function ContactRowSkeleton() {
  return (
    <div className="flex items-center gap-3 py-3 border-b border-border">
      <Skeleton variant="circle" width={40} height={40} />
      <div className="flex-1 space-y-1.5">
        <Skeleton variant="text" className="w-48 h-4" />
        <Skeleton variant="text" className="w-64 h-3.5" />
      </div>
      <Skeleton variant="badge" className="w-16 h-6" />
    </div>
  );
}

export default function ContactsPageSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading contacts">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Skeleton variant="text" className="w-48 h-8" />
        <div className="flex gap-2 ml-auto">
          <Skeleton variant="badge" className="w-24" />
          <Skeleton variant="badge" className="w-24" />
          <Skeleton variant="badge" className="w-24" />
        </div>
      </div>

      {/* Enrichment progress */}
      <div className="rounded-lg border border-primary/20 bg-card/80 p-4">
        <Skeleton variant="rect" className="h-2.5 w-full rounded-full" />
        <Skeleton variant="text" className="w-48 h-3 mt-2" />
      </div>

      {/* Search bar */}
      <Skeleton variant="rect" className="h-10 w-full rounded-lg" />

      {/* Contact rows */}
      <div>
        {Array.from({ length: 10 }, (_, i) => (
          <ContactRowSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}
