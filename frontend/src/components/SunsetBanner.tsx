export default function SunsetBanner() {
  const enabled = import.meta.env.VITE_SUNSET_MODE === 'true';
  if (!enabled) return null;

  return (
    <div
      role="alert"
      className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200"
    >
      <p className="font-semibold">WarmPath is shutting down on April 28, 2026.</p>
      <p className="mt-1">
        If you want a copy of your data, reply to the shutdown email you received.
        After April 28, all data will be permanently deleted.
      </p>
    </div>
  );
}
