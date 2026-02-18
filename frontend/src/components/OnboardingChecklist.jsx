import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { contacts as contactsApi, preferences as prefsApi, marketplace as mpApi } from '../api/client';

const BASE_STEPS = [
  {
    key: 'contacts',
    label: 'Upload your contacts',
    description: 'Import your LinkedIn CSV to unlock 100 credits and start finding referrals.',
    cta: 'Upload CSV',
    href: '/contacts',
    credits: 100,
  },
  {
    key: 'preferences',
    label: 'Set job preferences',
    description: 'Tell us what roles and companies you\'re targeting for smarter matches.',
    cta: 'Set Preferences',
    href: '/settings?tab=profile',
    credits: null,
  },
  {
    key: 'sharing',
    label: 'Configure sharing settings',
    description: 'Opt in to help others get referrals and earn credits for every intro you facilitate.',
    cta: 'Configure Sharing',
    href: '/settings?tab=sharing',
    credits: null,
  },
];

export default function OnboardingChecklist() {
  const { user } = useAuth();
  const [completed, setCompleted] = useState({});
  const [loading, setLoading] = useState(true);
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem('warmpath_checklist_dismissed') === 'true'
  );

  const STEPS = BASE_STEPS;

  useEffect(() => {
    if (dismissed) return;

    let cancelled = false;
    (async () => {
      const done = {};
      try {
        const [contactsRes, prefsRes, sharingRes] = await Promise.allSettled([
          contactsApi.list({ per_page: 1 }),
          prefsApi.getJob(),
          mpApi.getSharingPrefs(),
        ]);

        if (contactsRes.status === 'fulfilled') {
          const total = contactsRes.value?.meta?.total ?? contactsRes.value?.data?.length ?? 0;
          done.contacts = total > 0;
        }

        done.preferences = prefsRes.status === 'fulfilled' && prefsRes.value?.data?.target_role;

        done.sharing = sharingRes.status === 'fulfilled' && sharingRes.value?.data?.is_configured;
      } catch {
        // If API calls fail, don't block the UI
      }

      if (!cancelled) {
        setCompleted(done);
        setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [dismissed]);

  if (dismissed || loading) return null;

  const completedCount = STEPS.filter((s) => completed[s.key]).length;
  if (completedCount === STEPS.length) return null;

  const progress = Math.round((completedCount / STEPS.length) * 100);

  return (
    <div className="mb-4 rounded-xl bg-slate-900 border border-slate-700/50" role="region" aria-label="Getting started checklist">
      <div className="border-b border-slate-700/50 px-5 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-50">Get started with WarmPath</h2>
            <p className="text-xs text-slate-500">{completedCount} of {STEPS.length} steps complete</p>
          </div>
          <button
            onClick={() => {
              setDismissed(true);
              localStorage.setItem('warmpath_checklist_dismissed', 'true');
            }}
            aria-label="Dismiss checklist"
            className="text-slate-500 hover:text-slate-300 text-lg leading-none"
          >
            &times;
          </button>
        </div>
        {/* Progress bar */}
        <div className="mt-2 h-1.5 w-full rounded-full bg-slate-800">
          <div
            className="h-1.5 rounded-full bg-amber-500 transition-all duration-500"
            style={{ width: `${progress}%` }}
            role="progressbar"
            aria-valuenow={completedCount}
            aria-valuemin={0}
            aria-valuemax={STEPS.length}
          />
        </div>
      </div>

      <div className="divide-y divide-slate-700/50">
        {STEPS.map((step) => {
          const isDone = completed[step.key];
          return (
            <div key={step.key} className="flex items-center gap-4 px-5 py-3">
              {/* Checkbox icon */}
              <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${isDone ? 'bg-emerald-500' : 'border-2 border-slate-600'}`}>
                {isDone && (
                  <svg className="h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24" strokeWidth="3" stroke="currentColor" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                  </svg>
                )}
              </div>

              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium ${isDone ? 'text-slate-500 line-through' : 'text-slate-50'}`}>
                  {step.label}
                  {step.credits && !isDone && (
                    <span className="ml-2 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-400">
                      +{step.credits} credits
                    </span>
                  )}
                </p>
                {!isDone && (
                  <p className="text-xs text-slate-500 mt-0.5">{step.description}</p>
                )}
              </div>

              {!isDone && (
                <Link
                  to={step.href}
                  className="shrink-0 rounded-md bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-400"
                >
                  {step.cta}
                </Link>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
