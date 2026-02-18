import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { auth as authApi, credits as creditsApi, onUsageWarning } from '../api/client';

export default function Layout() {
  const { user, logout, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [balance, setBalance] = useState(null);
  const [mobileNav, setMobileNav] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef(null);
  const [usageWarning, setUsageWarning] = useState(null);
  const [resending, setResending] = useState(false);
  const [resendMsg, setResendMsg] = useState('');
  const [verifyDismissed, setVerifyDismissed] = useState(false);

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
    { to: '/dashboard', label: 'Dashboard', show: true },
    { to: '/contacts', label: 'Contacts', show: true },
    { to: '/referrals', label: 'Find Referrals', show: isSeeker },
  ];

  // Secondary links collapsed under "More" dropdown
  const moreLinks = [
    { to: '/applications', label: 'My Applications', show: isSeeker },
    { to: '/marketplace/requests', label: 'Marketplace Requests', show: isSeeker },
    { to: '/marketplace/dashboard', label: 'Network Dashboard', show: isHolder },
    { to: '/marketplace/settings', label: 'Sharing Settings', show: isHolder },
    { to: '/credits', label: 'Credits', show: true },
    { to: '/invite', label: 'Invite & Earn', show: true },
    { to: '/settings/privacy', label: 'Privacy Settings', show: true },
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
            <Link to="/profile/edit" className="hidden text-sm text-amber-600 hover:text-amber-700 sm:inline">
              {user?.full_name}
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
              <NavLink to="/profile/edit" onClick={() => setMobileNav(false)} className={navLinkClass}>
                Profile
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
    </div>
  );
}
