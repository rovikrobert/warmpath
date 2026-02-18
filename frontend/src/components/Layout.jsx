import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { auth as authApi, credits as creditsApi, onUsageWarning } from '../api/client';
import WelcomeToast from './WelcomeToast';
import BetaFeedbackButton from './BetaFeedbackButton';

export default function Layout() {
  const { user, logout, refreshUser, justSignedUp, setJustSignedUp } = useAuth();
  const navigate = useNavigate();
  const [balance, setBalance] = useState(null);
  const [mobileNav, setMobileNav] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef(null);
  const [usageWarning, setUsageWarning] = useState(null);
  const [resending, setResending] = useState(false);
  const [resendMsg, setResendMsg] = useState('');
  const [verifyDismissed, setVerifyDismissed] = useState(false);
  const [showWelcome, setShowWelcome] = useState(justSignedUp);

  useEffect(() => {
    creditsApi.balance().then((r) => setBalance(r.data?.balance ?? 0)).catch(() => {});
    onUsageWarning((msg) => setUsageWarning(msg));
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const handleResendVerification = async () => {
    setResending(true);
    setResendMsg('');
    try {
      await authApi.resendVerification();
      setResendMsg('Verification email sent!');
      // Refresh user in case they verified between page loads
      await refreshUser();
    } catch (err) {
      setResendMsg(err.message || 'Failed to resend');
    } finally {
      setResending(false);
    }
  };

  // Close "More" dropdown on outside click
  useEffect(() => {
    if (!moreOpen) return;
    const handleClick = (e) => {
      if (moreRef.current && !moreRef.current.contains(e.target)) setMoreOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [moreOpen]);

  const isSeeker = !user?.user_type || user.user_type === 'job_seeker' || user.user_type === 'both';
  const isHolder = user?.user_type === 'network_holder' || user?.user_type === 'both';
  const isUnverified = user && !user.email_verified;

  const navLinkClass = ({ isActive }) =>
    `text-sm ${isActive ? 'font-medium text-amber-600' : 'text-slate-600 hover:text-slate-900'}`;

  // Primary links always visible in desktop nav
  const primaryLinks = [
    { to: '/dashboard', label: 'Keevs', show: true },
    { to: '/contacts', label: 'Contacts', show: true },
    { to: '/referrals', label: 'Find Referrals', show: isSeeker },
  ];

  // Secondary links collapsed under "More" dropdown
  const moreLinks = [
    { to: '/applications', label: 'My Applications', show: isSeeker },
    { to: '/marketplace/requests', label: 'Marketplace Requests', show: isSeeker },
    { to: '/marketplace/dashboard', label: 'Network Dashboard', show: isHolder },
    { to: '/invite', label: 'Invite & Earn', show: true },
  ];

  // All links for mobile nav
  const allLinks = [...primaryLinks, ...moreLinks];

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-6">
            <Link to="/dashboard" className="flex items-center gap-2 text-xl font-bold text-slate-900">
              <span className="text-amber-500">~</span>
              <span>WarmPath</span>
            </Link>
            <nav className="hidden items-center gap-4 lg:flex">
              {primaryLinks.filter((l) => l.show).map((link) => (
                <NavLink key={link.to} to={link.to} className={navLinkClass}>
                  {link.label}
                </NavLink>
              ))}
              {/* More dropdown */}
              <div ref={moreRef} className="relative">
                <button
                  onClick={() => setMoreOpen(!moreOpen)}
                  className={`flex items-center gap-1 text-sm ${moreOpen ? 'font-medium text-amber-600' : 'text-slate-600 hover:text-slate-900'}`}
                >
                  More
                  <svg className={`h-3.5 w-3.5 transition ${moreOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
                  </svg>
                </button>
                {moreOpen && (
                  <div className="absolute left-0 top-full z-40 mt-2 w-52 rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
                    {moreLinks.filter((l) => l.show).map((link) => (
                      <NavLink
                        key={link.to}
                        to={link.to}
                        onClick={() => setMoreOpen(false)}
                        className={({ isActive }) =>
                          `block px-4 py-2 text-sm ${isActive ? 'bg-amber-50 font-medium text-amber-600' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'}`
                        }
                      >
                        {link.label}
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/credits" className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-700 hover:bg-amber-200">
              {balance ?? '—'} credits
            </Link>
            <Link to="/settings?tab=profile" className="hidden text-sm text-amber-600 hover:text-amber-700 sm:inline">
              {user?.full_name}
            </Link>
            <Link to="/settings?tab=profile" aria-label="Settings" className="hidden text-slate-500 hover:text-slate-700 sm:inline-flex">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
              </svg>
            </Link>
            {/* Mobile menu toggle */}
            <button
              onClick={() => setMobileNav(!mobileNav)}
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-600 hover:bg-slate-50 lg:hidden"
            >
              {mobileNav ? 'Close' : 'Menu'}
            </button>
            <button
              onClick={handleLogout}
              className="hidden rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 sm:inline-flex"
            >
              Log out
            </button>
          </div>
        </div>

        {/* Mobile nav */}
        {mobileNav && (
          <div className="border-t border-slate-200 px-4 py-3 lg:hidden">
            <nav className="flex flex-col gap-2">
              {allLinks.filter((l) => l.show).map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  onClick={() => setMobileNav(false)}
                  className={navLinkClass}
                >
                  {link.label}
                </NavLink>
              ))}
              <NavLink to="/settings?tab=profile" onClick={() => setMobileNav(false)} className={navLinkClass}>
                Settings
              </NavLink>
              <button
                onClick={() => { setMobileNav(false); handleLogout(); }}
                className="text-left text-sm text-slate-600 hover:text-slate-900"
              >
                Log out
              </button>
            </nav>
          </div>
        )}
      </header>

      {/* Email verification banner */}
      {isUnverified && !verifyDismissed && (
        <div className="border-b border-blue-300 bg-blue-50 px-4 py-2.5">
          <div className="mx-auto flex max-w-6xl items-center justify-between">
            <p className="text-sm text-blue-800">
              Please verify your email to access marketplace features.{' '}
              {resendMsg ? (
                <span className="font-medium">{resendMsg}</span>
              ) : (
                <button
                  onClick={handleResendVerification}
                  disabled={resending}
                  className="font-medium text-blue-700 underline hover:text-blue-900 disabled:opacity-50"
                >
                  {resending ? 'Sending...' : 'Resend verification email'}
                </button>
              )}
            </p>
            <button
              onClick={() => setVerifyDismissed(true)}
              className="ml-4 text-blue-600 hover:text-blue-800"
            >
              &times;
            </button>
          </div>
        </div>
      )}

      {/* Usage warning banner */}
      {usageWarning && (
        <div className="border-b border-amber-300 bg-amber-50 px-4 py-2.5">
          <div className="mx-auto flex max-w-6xl items-center justify-between">
            <p className="text-sm text-amber-800">
              {usageWarning}
              {' '}
              <Link to="/credits" className="font-medium text-amber-700 underline hover:text-amber-900">
                Upgrade &rarr;
              </Link>
            </p>
            <button
              onClick={() => setUsageWarning(null)}
              className="ml-4 text-amber-600 hover:text-amber-800"
            >
              &times;
            </button>
          </div>
        </div>
      )}

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
          <p className="text-xs text-slate-400">
            WarmPath &mdash; Majiq Pte Ltd
          </p>
          <Link to="/privacy" className="text-xs text-slate-400 hover:text-slate-600">
            Privacy Policy
          </Link>
        </div>
      </footer>

      {/* Welcome toast for new signups */}
      {showWelcome && (
        <WelcomeToast onDismiss={() => { setShowWelcome(false); setJustSignedUp(false); }} />
      )}

      {/* Beta feedback button */}
      {import.meta.env.VITE_BETA_MODE === 'true' && <BetaFeedbackButton />}
    </div>
  );
}
