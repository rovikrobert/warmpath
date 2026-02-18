import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

export default function WelcomeToast({ onDismiss }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Delay entry for smooth appearance
    const timer = setTimeout(() => setVisible(true), 500);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    // Auto-dismiss after 12 seconds
    const timer = setTimeout(() => {
      setVisible(false);
      setTimeout(onDismiss, 300);
    }, 12000);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  return (
    <div
      className={`fixed bottom-6 left-6 z-50 w-80 rounded-xl bg-white shadow-lg ring-1 ring-slate-200 transition-all duration-300 ${
        visible ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0'
      }`}
      role="status"
      aria-live="polite"
    >
      <div className="px-5 py-4">
        <div className="flex items-start gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-500 text-sm font-bold text-white" aria-hidden="true">~</span>
          <div className="flex-1">
            <p className="text-sm font-semibold text-slate-900">Welcome to WarmPath!</p>
            <p className="mt-1 text-xs text-slate-600">
              You've got <span className="font-semibold text-amber-600">50 credits</span> to get started.
              Upload your LinkedIn CSV to earn <span className="font-semibold text-amber-600">100 more</span>.
            </p>
            <Link
              to="/contacts"
              className="mt-2 inline-block rounded-md bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600"
            >
              Upload CSV
            </Link>
          </div>
          <button
            onClick={() => {
              setVisible(false);
              setTimeout(onDismiss, 300);
            }}
            aria-label="Dismiss welcome message"
            className="text-slate-400 hover:text-slate-600 text-lg leading-none"
          >
            &times;
          </button>
        </div>
      </div>
    </div>
  );
}
