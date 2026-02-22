import { useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import SourceTag from '../components/ui/SourceTag';
import { SOURCES } from '../utils/sources';
import useDocumentTitle from '../hooks/useDocumentTitle';

export default function Join() {
  useDocumentTitle('Share Your Network');
  const [searchParams] = useSearchParams();

  // Store referral code from URL for post-signup attribution
  useEffect(() => {
    const ref = searchParams.get('ref');
    if (ref) {
      localStorage.setItem('referral_code', ref);
    }
  }, [searchParams]);

  return (
    <div className="min-h-screen bg-slate-950">
      {/* Minimal nav bar */}
      <header className="border-b border-slate-700/50 bg-slate-900">
        <nav
          className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3 sm:px-6"
          role="navigation"
          aria-label="Join page navigation"
        >
          <Link
            to="/"
            className="flex items-center gap-2 text-xl font-bold text-slate-50"
            aria-label="WarmPath home"
          >
            <span className="text-amber-500">~</span>
            <span>WarmPath</span>
          </Link>
          <Link
            to="/#sign-up"
            className="rounded-lg bg-amber-500 px-4 py-1.5 text-sm font-medium text-white hover:bg-amber-400"
          >
            Sign up free
          </Link>
        </nav>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-12 sm:px-6" role="main">
        {/* Hero */}
        <section className="mb-12 text-center">
          <h1 className="text-3xl font-bold tracking-tight text-slate-50 sm:text-4xl">
            Your network is more valuable than you think
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-lg text-slate-300">
            Help people land their next role through referrals — and earn your
            employer's referral bonus while you're at it.
          </p>
        </section>

        {/* Value prop cards */}
        <section className="mb-12 space-y-4" aria-label="Why share your network">
          {/* Card 1 — Referral bonuses */}
          <div className="rounded-xl border border-slate-700/50 bg-slate-900 p-6">
            <div className="mb-2 flex items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10">
                <svg
                  className="h-5 w-5 text-emerald-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="1.5"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
                  />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-slate-50">
                Referral bonuses you're missing
              </h2>
            </div>
            <p className="text-sm leading-relaxed text-slate-300">
              Your employer probably offers{' '}
              <span className="font-medium text-emerald-400">
                {SOURCES.REFERRAL_BONUS_RANGE.claim}
              </span>{' '}
              per successful referral hire. Most go unclaimed because finding
              qualified candidates is hard. We route pre-qualified candidates to
              you so you can collect what you're already owed.{' '}
              <SourceTag
                source={SOURCES.REFERRAL_BONUS_RANGE.source}
                label={SOURCES.REFERRAL_BONUS_RANGE.label}
              />
            </p>
          </div>

          {/* Card 2 — Control */}
          <div className="rounded-xl border border-slate-700/50 bg-slate-900 p-6">
            <div className="mb-2 flex items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-500/10">
                <svg
                  className="h-5 w-5 text-blue-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="1.5"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z"
                  />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-slate-50">
                You stay in control
              </h2>
            </div>
            <p className="text-sm leading-relaxed text-slate-300">
              Upload your LinkedIn connections and choose who gets introduced.
              Your contacts appear anonymously on the marketplace — no names, no
              emails. When someone requests an intro, you review their profile
              and decide. Nothing happens without your explicit approval.
            </p>
          </div>

          {/* Card 3 — Zero cost */}
          <div className="rounded-xl border border-slate-700/50 bg-slate-900 p-6">
            <div className="mb-2 flex items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-amber-500/10">
                <svg
                  className="h-5 w-5 text-amber-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="1.5"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z"
                  />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-slate-50">
                Zero cost, real impact
              </h2>
            </div>
            <p className="text-sm leading-relaxed text-slate-300">
              Completely free. Upload your connections, review intro requests on
              your schedule, and help someone skip the cold application grind.
              Referred candidates are hired{' '}
              <span className="font-medium text-amber-400">
                {SOURCES.REFERRAL_HIRE_SPEED.claim}
              </span>{' '}
              faster than non-referred applicants.{' '}
              <SourceTag
                source={SOURCES.REFERRAL_HIRE_SPEED.source}
                label={SOURCES.REFERRAL_HIRE_SPEED.label}
              />
            </p>
          </div>
        </section>

        {/* How it works */}
        <section className="mb-12" aria-label="How it works">
          <h2 className="mb-6 text-center text-xl font-bold text-slate-50">
            How it works
          </h2>
          <div className="grid gap-4 sm:grid-cols-3">
            {[
              {
                step: '1',
                title: 'Upload your connections',
                desc: 'Export your LinkedIn CSV and upload it. Takes 2 minutes.',
              },
              {
                step: '2',
                title: 'Review intro requests',
                desc: 'Job seekers find anonymous matches. You see who they are before deciding.',
              },
              {
                step: '3',
                title: 'Collect referral bonuses',
                desc: 'When your contact hires the candidate, the referral bonus goes to you.',
              },
            ].map((item) => (
              <div
                key={item.step}
                className="rounded-xl border border-slate-700/50 bg-slate-900 p-5 text-center"
              >
                <div className="mx-auto mb-3 flex h-8 w-8 items-center justify-center rounded-full bg-amber-500/10 text-sm font-bold text-amber-400">
                  {item.step}
                </div>
                <h3 className="mb-1 text-sm font-semibold text-slate-50">
                  {item.title}
                </h3>
                <p className="text-xs leading-relaxed text-slate-400">
                  {item.desc}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* Privacy reassurance */}
        <section
          className="mb-12 rounded-xl border border-slate-700/50 bg-slate-900 p-6"
          aria-label="Privacy commitment"
        >
          <h2 className="mb-3 text-base font-semibold text-slate-50">
            Privacy is our foundation
          </h2>
          <ul className="space-y-2 text-sm text-slate-300">
            <li className="flex items-start gap-2">
              <svg
                className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth="2"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="m4.5 12.75 6 6 9-13.5"
                />
              </svg>
              Your contacts are stored in a private vault visible only to you
            </li>
            <li className="flex items-start gap-2">
              <svg
                className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth="2"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="m4.5 12.75 6 6 9-13.5"
                />
              </svg>
              Marketplace listings show only role level and department — never
              names or emails
            </li>
            <li className="flex items-start gap-2">
              <svg
                className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth="2"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="m4.5 12.75 6 6 9-13.5"
                />
              </svg>
              No identity is revealed without your active, explicit approval
            </li>
            <li className="flex items-start gap-2">
              <svg
                className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth="2"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="m4.5 12.75 6 6 9-13.5"
                />
              </svg>
              You can pause sharing or exclude specific contacts at any time
            </li>
          </ul>
          <div className="mt-3">
            <Link
              to="/privacy"
              className="text-xs text-amber-400 hover:text-amber-300"
            >
              Read our full privacy policy
            </Link>
          </div>
        </section>

        {/* CTA */}
        <section className="text-center" aria-label="Sign up">
          <Link
            to="/#sign-up"
            className="inline-block rounded-lg bg-amber-500 px-8 py-3 text-base font-semibold text-white shadow-lg shadow-amber-500/20 hover:bg-amber-400"
          >
            Get started — it's free
          </Link>
          <p className="mt-3 text-sm text-slate-400">
            No credit card required. Upload your connections and start earning
            referral bonuses.
          </p>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-700/50 bg-slate-900">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-4 sm:px-6">
          <p className="text-xs text-slate-500">
            Majiq Pte Ltd &middot; Singapore
          </p>
          <Link
            to="/privacy"
            className="text-xs text-slate-400 hover:text-slate-300"
          >
            Privacy
          </Link>
        </div>
      </footer>
    </div>
  );
}
