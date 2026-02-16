import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { credits as creditsApi, onUsageWarning } from '../api/client';

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [balance, setBalance] = useState(null);
  const [mobileNav, setMobileNav] = useState(false);
  const [usageWarning, setUsageWarning] = useState(null);

  useEffect(() => {
    creditsApi.balance().then((r) => setBalance(r.data?.balance ?? 0)).catch(() => {});
    onUsageWarning((msg) => setUsageWarning(msg));
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const isSeeker = !user?.user_type || user.user_type === 'job_seeker' || user.user_type === 'both';
  const isHolder = user?.user_type === 'network_holder' || user?.user_type === 'both';

  const navLinkClass = ({ isActive }) =>
    `text-sm ${isActive ? 'font-medium text-amber-600' : 'text-slate-600 hover:text-slate-900'}`;

  const navLinks = [
    { to: '/dashboard', label: 'Dashboard', show: true },
    { to: '/referrals', label: 'Find Referrals', show: isSeeker },
    { to: '/applications', label: 'My Applications', show: isSeeker },
    { to: '/marketplace/requests', label: 'Marketplace Requests', show: isSeeker },
    { to: '/marketplace/dashboard', label: 'Network Dashboard', show: isHolder },
    { to: '/marketplace/settings', label: 'Sharing Settings', show: isHolder },
    { to: '/credits', label: 'Credits', show: true },
  ];

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-6">
            <Link to="/dashboard" className="flex items-center gap-2 text-xl font-bold text-slate-900">
              <span className="text-amber-500">~</span>
              <span>WarmPath</span>
            </Link>
            <nav className="hidden items-center gap-4 lg:flex">
              {navLinks.filter((l) => l.show).map((link) => (
                <NavLink key={link.to} to={link.to} className={navLinkClass}>
                  {link.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/credits" className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-700 hover:bg-amber-200">
              {balance ?? '—'} credits
            </Link>
            <span className="hidden text-sm text-slate-600 sm:inline">
              {user?.full_name}
            </span>
            <Link to="/profile/edit" className="hidden text-sm text-amber-600 hover:text-amber-700 sm:inline">
              Profile
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
              {navLinks.filter((l) => l.show).map((link) => (
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

      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
