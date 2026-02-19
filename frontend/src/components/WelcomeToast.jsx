import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

export default function WelcomeToast({ onDismiss }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), 500);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      setVisible(false);
      setTimeout(onDismiss, 300);
    }, 12000);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  return (
    <div
      className={`fixed bottom-6 left-6 z-50 w-80 rounded-xl bg-slate-900 border border-slate-700/50 shadow-lg transition-all duration-300 ${
        visible ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0'
      }`}
      role="status"
      aria-live="polite"
    >
      <div className="px-5 py-4">
        <div className="flex items-start gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-500 text-sm font-bold text-white" aria-hidden="true">~</span>
          <div className="flex-1">
            <p className="text-sm font-semibold text-slate-50">Welcome to WarmPath!</p>
            <p className="mt-1 text-xs text-slate-400">
              You've got <span className="font-semibold text-amber-400">{import.meta.env.VITE_BETA_MODE === 'true' ? '500' : '50'} credits</span> to get started.
              Upload your LinkedIn CSV to earn <span className="font-semibold text-amber-400">100 more</span>.
            </p>
            <Link
              to="/contacts"
              className="mt-2 inline-block rounded-md bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-400"
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
            className="text-slate-500 hover:text-slate-300 text-lg leading-none"
          >
            &times;
          </button>
        </div>
      </div>
    </div>
  );
}
