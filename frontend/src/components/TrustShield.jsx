import { useState } from 'react';
import { Link } from 'react-router-dom';

export default function TrustShield() {
  const [show, setShow] = useState(false);

  return (
    <div
      className="relative"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <button
        className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-400 transition-colors"
        aria-label="Privacy information"
        type="button"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
        </svg>
        Privacy Protected
      </button>

      {show && (
        <div className="absolute bottom-full left-0 mb-2 max-w-64 rounded-lg border border-slate-700/50 bg-slate-800 p-3 shadow-xl">
          <p className="text-xs text-slate-300">
            Your contacts are encrypted and never shared without your approval.
          </p>
          <p className="mt-1.5 text-xs text-slate-300">
            You can delete all your data anytime from{' '}
            <Link to="/settings" className="text-amber-400 hover:text-amber-300">
              Settings &rarr; Privacy
            </Link>.
          </p>
          <Link
            to="/privacy"
            className="mt-2 block text-xs text-slate-400 hover:text-slate-300 underline"
          >
            Privacy Policy
          </Link>
        </div>
      )}
    </div>
  );
}
