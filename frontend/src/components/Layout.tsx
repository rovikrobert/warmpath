import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { UserButton } from '@clerk/clerk-react';
import { useAuth } from '../context/AuthContext';
import { credits as creditsApi, feed as feedApi, onUsageWarning } from '../api/client';
import BetaFeedbackButton from './BetaFeedbackButton';
import CommandPalette from './CommandPalette';
import KeyboardShortcutsModal from './KeyboardShortcutsModal';
import KeevsBar from './KeevsBar';
import TrustShield from './TrustShield';
import { ThemeToggle } from './ThemeToggle';
import useKeyboardShortcuts from '../hooks/useKeyboardShortcuts';

const NAV_ITEMS = [
  {
    to: '/coach',
    label: 'Coach',
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955a1.126 1.126 0 011.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
      </svg>
    ),
    show: () => true,
  },
  {
    to: '/notifications',
    label: 'Notifications',
    badge: true,
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0" />
      </svg>
    ),
    show: () => true,
  },
  {
    to: '/contacts',
    label: 'Contacts',
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
      </svg>
    ),
    show: () => true,
  },
  {
    to: '/referrals',
    label: 'Find Referrals',
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
      </svg>
    ),
    show: () => true,
  },
  {
    to: '/applications',
    label: 'Applications',
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15a2.25 2.25 0 012.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z" />
      </svg>
    ),
    show: () => true,
  },
  {
    to: '/marketplace',
    label: 'Marketplace',
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 21v-7.5a.75.75 0 01.75-.75h3a.75.75 0 01.75.75V21m-4.5 0H2.36m11.14 0H18m0 0h3.64m-1.39 0V9.349m-16.5 11.65V9.35m0 0a3.001 3.001 0 003.75-.615A2.993 2.993 0 009.75 9.75c.896 0 1.7-.393 2.25-1.016a2.993 2.993 0 002.25 1.016c.896 0 1.7-.393 2.25-1.016a3.001 3.001 0 003.75.614m-16.5 0a3.004 3.004 0 01-.621-4.72L4.318 3.44A1.5 1.5 0 015.378 3h13.243a1.5 1.5 0 011.06.44l1.19 1.189a3 3 0 01-.621 4.72m-13.5 8.65h3.75a.75.75 0 00.75-.75V13.5a.75.75 0 00-.75-.75H6.75a.75.75 0 00-.75.75v3.15c0 .414.336.75.75.75z" />
      </svg>
    ),
    show: () => true,
  },
  {
    to: '/invite',
    label: 'Invite & Earn',
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 11.25v8.25a1.5 1.5 0 01-1.5 1.5H5.25a1.5 1.5 0 01-1.5-1.5v-8.25M12 4.875A2.625 2.625 0 109.375 7.5H12m0-2.625V7.5m0-2.625A2.625 2.625 0 1114.625 7.5H12m0 0V21m-8.625-9.75h18c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125h-18c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
      </svg>
    ),
    show: () => true,
  },
];

const BOTTOM_NAV_ITEMS = [
  { to: '/coach', label: 'Coach', iconPath: 'M2.25 12l8.954-8.955a1.126 1.126 0 011.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25' },
  { to: '/contacts', label: 'Contacts', iconPath: 'M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z' },
  { to: '/referrals', label: 'Search', iconPath: 'M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z' },
  { to: '/applications', label: 'Apps', iconPath: 'M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15a2.25 2.25 0 012.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z' },
  { to: '/marketplace', label: 'Market', iconPath: 'M13.5 21v-7.5a.75.75 0 01.75-.75h3a.75.75 0 01.75.75V21m-4.5 0H2.36m11.14 0H18m0 0h3.64m-1.39 0V9.349m-16.5 11.65V9.35m0 0a3.001 3.001 0 003.75-.615A2.993 2.993 0 009.75 9.75c.896 0 1.7-.393 2.25-1.016a2.993 2.993 0 002.25 1.016c.896 0 1.7-.393 2.25-1.016a3.001 3.001 0 003.75.614m-16.5 0a3.004 3.004 0 01-.621-4.72L4.318 3.44A1.5 1.5 0 015.378 3h13.243a1.5 1.5 0 011.06.44l1.19 1.189a3 3 0 01-.621 4.72m-13.5 8.65h3.75a.75.75 0 00.75-.75V13.5a.75.75 0 00-.75-.75H6.75a.75.75 0 00-.75.75v3.15c0 .414.336.75.75.75z' },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [balance, setBalance] = useState<number | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [usageWarning, setUsageWarning] = useState<string | null>(null);
  const [feedUnseen, setFeedUnseen] = useState(0);
  const [showShortcuts, setShowShortcuts] = useState(false);

  useKeyboardShortcuts([
    { key: '/', action: () => {
      const el = document.querySelector('[data-search-input]');
      if (el) {
        const input = el.tagName === 'INPUT' ? el : el.querySelector('input');
        if (input) input.focus();
      }
    }},
    { key: 'n', action: () => {
      if (location.pathname === '/contacts') navigate('/contacts?upload=true');
      else if (location.pathname === '/applications') navigate('/applications?add=true');
      else if (location.pathname.startsWith('/referrals') || location.pathname.startsWith('/search')) navigate('/referrals');
    }},
    { key: '?', action: () => setShowShortcuts(true) },
  ], [location.pathname]);

  useEffect(() => {
    creditsApi.balance().then((r) => setBalance(r.data?.balance ?? 0)).catch((err) => { console.error('Layout: balance fetch failed', err); });
    feedApi.count().then((r) => setFeedUnseen(r.data?.unseen ?? 0)).catch((err) => { console.error('Layout: feed count failed', err); });
    onUsageWarning((msg) => setUsageWarning(msg));
    // Refresh feed count every 2 minutes
    const interval = setInterval(() => {
      feedApi.count().then((r) => setFeedUnseen(r.data?.unseen ?? 0)).catch((err) => { console.error('Layout: feed count failed', err); });
    }, 120_000);
    // Also refresh immediately when feed items are seen/dismissed
    const refreshOnUpdate = () => {
      feedApi.count().then((r) => setFeedUnseen(r.data?.unseen ?? 0)).catch((err) => { console.error('Layout: feed count failed', err); });
    };
    window.addEventListener('feed-updated', refreshOnUpdate);
    return () => {
      clearInterval(interval);
      window.removeEventListener('feed-updated', refreshOnUpdate);
    };
  }, []);

  // Refetch balance on route change (debounced: 10s minimum between fetches)
  const lastBalanceFetchRef = useRef<number>(0);
  useEffect(() => {
    const now = Date.now();
    if (now - lastBalanceFetchRef.current > 10000) {
      lastBalanceFetchRef.current = now;
      creditsApi.balance().then((r) => setBalance(r.data?.balance ?? 0)).catch((err) => { console.error('Layout: balance fetch failed', err); });
    }
  }, [location.pathname]);

  // Detect balance changes and trigger animation
  const prevBalanceRef = useRef<number | null>(null);
  const [creditAnimating, setCreditAnimating] = useState(false);
  const [creditDecreased, setCreditDecreased] = useState(false);
  useEffect(() => {
    if (prevBalanceRef.current !== null && balance !== null && balance !== prevBalanceRef.current) {
      setCreditAnimating(true);
      setCreditDecreased(balance < prevBalanceRef.current);
      const timer = setTimeout(() => {
        setCreditAnimating(false);
        setCreditDecreased(false);
      }, 600);
      prevBalanceRef.current = balance;
      return () => clearTimeout(timer);
    }
    prevBalanceRef.current = balance;
  }, [balance]);

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };
  const visibleNav = NAV_ITEMS.filter((item) => item.show(user));

  return (
    <div className="flex h-screen overflow-x-hidden bg-background">
      {/* Desktop Sidebar */}
      <aside className={`hidden lg:flex flex-col border-r border-border bg-card transition-all ${collapsed ? 'w-16' : 'w-56'}`}>
        {/* Logo */}
        <div className="flex items-center gap-2 border-b border-border px-4 py-4">
          <Link to="/coach" className="flex items-center gap-2">
            <span className="text-xl font-bold text-primary">~</span>
            {!collapsed && <span className="text-lg font-bold text-foreground">WarmPath</span>}
          </Link>
          <button
            onClick={() => setCollapsed(!collapsed)}
            className={`ml-auto text-muted-foreground hover:text-secondary-foreground transition-colors ${collapsed ? 'mx-auto' : ''}`}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <svg className={`h-4 w-4 transition-transform ${collapsed ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
          </button>
        </div>

        {/* Nav items */}
        <nav className="flex-1 overflow-y-auto py-2">
          {visibleNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? 'border-l-2 border-primary bg-primary/10 text-primary'
                    : 'border-l-2 border-transparent text-muted-foreground hover:bg-muted hover:text-foreground'
                } ${collapsed ? 'justify-center px-0' : ''}`
              }
              title={collapsed ? item.label : undefined}
            >
              <span className="relative">
                {item.icon}
                {item.badge && feedUnseen > 0 && (
                  <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold text-background">
                    {feedUnseen > 9 ? '9+' : feedUnseen}
                  </span>
                )}
              </span>
              {!collapsed && item.label}
            </NavLink>
          ))}

          {/* Separator */}
          <div className="mx-4 my-2 border-t border-border" />

          <NavLink
            to="/settings"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'border-l-2 border-primary bg-primary/10 text-primary'
                  : 'border-l-2 border-transparent text-muted-foreground hover:bg-muted hover:text-foreground'
              } ${collapsed ? 'justify-center px-0' : ''}`
            }
            title={collapsed ? 'Settings' : undefined}
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            {!collapsed && 'Settings'}
          </NavLink>
        </nav>

        {/* Sidebar footer */}
        <div className="border-t border-border p-4">
          {!collapsed && (
            <>
              <div className="mb-2 flex items-center justify-between">
                <TrustShield />
                <ThemeToggle />
              </div>
              <Link to="/credits" className="mb-3 flex items-center gap-2 rounded-lg bg-primary/10 px-3 py-2 text-sm font-medium text-primary hover:bg-primary/20 transition-colors">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125" />
                </svg>
                <span className={`inline-block ${creditAnimating ? 'animate-count-change' : ''} ${creditDecreased ? 'text-primary' : ''} transition-colors`}>{balance ?? '—'}</span> credits
              </Link>
              <div className="flex items-center gap-2">
                <UserButton signInUrl="/" />
                <div className="flex-1 min-w-0">
                  <p className="truncate text-sm font-medium text-foreground">{user?.full_name}</p>
                </div>
              </div>
            </>
          )}
          {collapsed && (
            <div className="flex flex-col items-center gap-2">
              <UserButton signInUrl="/" />
            </div>
          )}
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="fixed top-0 left-0 right-0 z-40 flex items-center justify-between border-b border-border bg-card px-4 py-3 lg:hidden">
        <Link to="/coach" className="flex items-center gap-2">
          <span className="text-xl font-bold text-primary">~</span>
          <span className="text-lg font-bold text-foreground">WarmPath</span>
        </Link>
        <div className="flex items-center gap-3">
          <Link to="/credits" className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
            <span className={`inline-block ${creditAnimating ? 'animate-count-change' : ''} ${creditDecreased ? 'text-primary' : ''} transition-colors`}>{balance ?? '—'}</span>
          </Link>
          <button
            onClick={() => setMobileNav(!mobileNav)}
            className="text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Menu"
          >
            {mobileNav ? (
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Mobile slide-out menu */}
      {mobileNav && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setMobileNav(false)} aria-hidden="true" />
          <div className="absolute right-0 top-0 bottom-0 w-64 bg-card border-l border-border animate-in">
            <div className="flex items-center justify-between border-b border-border px-4 py-4">
              <span className="text-sm font-medium text-secondary-foreground">{user?.full_name}</span>
              <button onClick={() => setMobileNav(false)} aria-label="Close menu" className="text-muted-foreground hover:text-secondary-foreground">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <nav className="py-2">
              {visibleNav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={() => setMobileNav(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-4 py-2.5 text-sm font-medium transition-colors ${
                      isActive
                        ? 'border-l-2 border-primary bg-primary/10 text-primary'
                        : 'border-l-2 border-transparent text-muted-foreground hover:bg-muted hover:text-foreground'
                    }`
                  }
                >
                  {item.icon}
                  {item.label}
                </NavLink>
              ))}
              <div className="mx-4 my-2 border-t border-border" />
              <NavLink
                to="/settings"
                onClick={() => setMobileNav(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-2.5 text-sm font-medium transition-colors ${
                    isActive
                      ? 'border-l-2 border-primary bg-primary/10 text-primary'
                      : 'border-l-2 border-transparent text-muted-foreground hover:bg-muted hover:text-foreground'
                  }`
                }
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
                Settings
              </NavLink>
              <div className="mx-4 my-2 border-t border-border" />
              <div className="px-4 py-2">
                <TrustShield />
              </div>
              <div className="mx-4 my-2 border-t border-border" />
              <div className="flex items-center gap-3 px-4 py-2.5">
                <UserButton signInUrl="/" />
                <span className="text-sm text-muted-foreground">Account</span>
              </div>
            </nav>
          </div>
        </div>
      )}

      {/* Main content area */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Spacer for mobile top bar */}
        <div className="h-14 lg:hidden" />

        {/* Beta sandbox banner */}
        {import.meta.env.VITE_BETA_MODE === 'true' && (
          <div className="border-b border-blue-500/30 bg-blue-500/10 px-4 py-2.5">
            <p className="text-sm text-blue-400 text-center">
              You're in the WarmPath beta — explore freely, limits are relaxed!
            </p>
          </div>
        )}

        {/* Usage warning banner */}
        {usageWarning && (
          <div className="border-b border-primary/30 bg-primary/10 px-4 py-2.5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-primary">
                {usageWarning}{' '}
                {import.meta.env.VITE_BETA_MODE !== 'true' && (
                  <Link to="/credits" className="font-medium text-primary underline hover:text-primary">
                    Upgrade &rarr;
                  </Link>
                )}
              </p>
              <button onClick={() => setUsageWarning(null)} aria-label="Dismiss warning" className="ml-4 text-primary hover:text-primary">
                &times;
              </button>
            </div>
          </div>
        )}

        <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-6xl">
            <KeevsBar />
            <div key={location.pathname} className="page-enter">
              <Outlet />
            </div>
          </div>
        </main>

        {/* Footer (inside main area) — hidden on mobile to save viewport space */}
        <footer className="hidden lg:block border-t border-border px-4 py-4 sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-6xl items-center justify-between">
            <p className="text-xs text-muted-foreground">WarmPath &mdash; Majiq Pte Ltd</p>
            <div className="flex items-center gap-4">
              <button
                onClick={() => setShowShortcuts(true)}
                className="hidden text-xs text-muted-foreground hover:text-muted-foreground lg:block"
              >
                Press <kbd className="rounded bg-muted px-1 py-0.5 text-muted-foreground">?</kbd> for shortcuts
              </button>
              <Link to="/privacy" className="text-xs text-muted-foreground hover:text-muted-foreground">Privacy Policy</Link>
            </div>
          </div>
        </footer>

        {/* Mobile bottom tab bar */}
        <nav className="fixed bottom-0 left-0 right-0 z-40 flex items-center justify-around border-t border-border bg-card py-2 pb-[calc(0.5rem+env(safe-area-inset-bottom))] lg:hidden">
          {BOTTOM_NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex flex-col items-center gap-0.5 px-2 py-2.5 text-xs transition-colors ${
                  isActive ? 'text-primary' : 'text-muted-foreground'
                }`
              }
            >
              <span className="relative">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d={item.iconPath} />
                </svg>
              </span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        {/* Spacer for mobile bottom tabs */}
        <div className="h-16 lg:hidden" />
      </div>

      {/* Beta feedback button */}
      {import.meta.env.VITE_BETA_MODE === 'true' && <BetaFeedbackButton />}

      {/* Command palette (Cmd+K) */}
      <CommandPalette />

      {/* Keyboard shortcuts modal */}
      <KeyboardShortcutsModal open={showShortcuts} onClose={() => setShowShortcuts(false)} />
    </div>
  );
}
