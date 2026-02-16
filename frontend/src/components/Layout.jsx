import { useEffect, useState } from 'react';
import { Link, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { credits as creditsApi } from '../api/client';

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [balance, setBalance] = useState(null);

  useEffect(() => {
    creditsApi.balance().then((r) => setBalance(r.data?.balance ?? 0)).catch(() => {});
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const isSeeker = !user?.user_type || user.user_type === 'job_seeker' || user.user_type === 'both';
  const isHolder = user?.user_type === 'network_holder' || user?.user_type === 'both';

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-6">
            <Link to="/dashboard" className="flex items-center gap-2 text-xl font-bold text-slate-900">
              <span className="text-amber-500">~</span>
              <span>WarmPath</span>
            </Link>
            <nav className="hidden items-center gap-4 sm:flex">
              <Link to="/dashboard" className="text-sm text-slate-600 hover:text-slate-900">Dashboard</Link>
              {isSeeker && (
                <Link to="/referrals" className="text-sm text-slate-600 hover:text-slate-900">Find Referrals</Link>
              )}
              {isHolder && (
                <Link to="/marketplace" className="text-sm text-slate-600 hover:text-slate-900">Marketplace</Link>
              )}
              {isSeeker && (
                <Link to="/my-requests" className="text-sm text-slate-600 hover:text-slate-900">My Requests</Link>
              )}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            {balance !== null && (
              <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-700">
                {balance} credits
              </span>
            )}
            <span className="hidden text-sm text-slate-600 sm:inline">
              {user?.full_name}
            </span>
            <Link
              to="/profile/edit"
              className="text-sm text-amber-600 hover:text-amber-700"
            >
              Profile
            </Link>
            <button
              onClick={handleLogout}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
