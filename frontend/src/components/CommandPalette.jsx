import { useEffect, useState, useRef, useCallback } from 'react';
import { Command } from 'cmdk';
import { useNavigate } from 'react-router-dom';
import { contacts as contactsApi } from '../api/client';

const NAV_ITEMS = [
  { label: 'Coach', path: '/coach' },
  { label: 'Contacts', path: '/contacts' },
  { label: 'Find Referrals', path: '/referrals' },
  { label: 'Applications', path: '/applications' },
  { label: 'Marketplace', path: '/marketplace' },
  { label: 'Credits', path: '/credits' },
  { label: 'Invite & Earn', path: '/invite' },
  { label: 'Settings', path: '/settings' },
];

const QUICK_ACTIONS = [
  { label: 'Upload CSV', path: '/contacts?upload=true' },
  { label: 'Track Application', path: '/applications?add=true' },
  { label: 'New Referral Search', path: '/referrals' },
];

function WarmScoreBadge({ score }) {
  if (score == null) return null;
  const color =
    score >= 70
      ? 'bg-green-500/20 text-green-400'
      : score >= 40
        ? 'bg-amber-500/20 text-amber-400'
        : 'bg-slate-500/20 text-slate-400';
  return (
    <span className={`ml-auto shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${color}`}>
      {score}
    </span>
  );
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [contactResults, setContactResults] = useState([]);
  const [loadingContacts, setLoadingContacts] = useState(false);
  const navigate = useNavigate();
  const debounceRef = useRef(null);
  const inputRef = useRef(null);

  // Toggle on Cmd+K / Ctrl+K
  useEffect(() => {
    const down = (e) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    document.addEventListener('keydown', down);
    return () => document.removeEventListener('keydown', down);
  }, []);

  // Focus input when opened, reset when closed
  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => inputRef.current?.focus());
    } else {
      setSearch('');
      setContactResults([]);
    }
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setOpen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  // Debounced contact search
  const searchContacts = useCallback((query) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (query.length < 3) {
      setContactResults([]);
      setLoadingContacts(false);
      return;
    }

    setLoadingContacts(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await contactsApi.list({ search: query, per_page: 8 });
        setContactResults(res.data ?? []);
      } catch {
        setContactResults([]);
      } finally {
        setLoadingContacts(false);
      }
    }, 300);
  }, []);

  const handleSearchChange = (value) => {
    setSearch(value);
    searchContacts(value);
  };

  const go = (path) => {
    setOpen(false);
    navigate(path);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      {/* Overlay */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm"
        onClick={() => setOpen(false)}
        aria-hidden="true"
      />

      {/* Dialog */}
      <div className="relative mx-auto mt-[20vh] max-w-lg rounded-xl border border-slate-700/50 bg-slate-900 shadow-2xl">
        <Command label="Command palette" shouldFilter={true}>
          <Command.Input
            ref={inputRef}
            value={search}
            onValueChange={handleSearchChange}
            placeholder="Search contacts, pages, actions..."
            className="w-full border-b border-slate-700/50 bg-transparent px-4 py-3 text-lg text-slate-100 placeholder-slate-500 outline-none"
          />

          <Command.List className="max-h-80 overflow-y-auto p-2">
            <Command.Empty className="flex items-center justify-center py-8 text-sm text-slate-500">
              No results found.
            </Command.Empty>

            {/* Navigation */}
            <Command.Group heading="Navigation">
              {NAV_ITEMS.map((item) => (
                <Command.Item
                  key={item.path}
                  value={item.label}
                  onSelect={() => go(item.path)}
                  className="mx-2 flex cursor-pointer items-center rounded-md px-4 py-2.5 text-sm text-slate-300 aria-selected:bg-amber-500/10 aria-selected:text-amber-400"
                >
                  <span>{item.label}</span>
                  <span className="ml-auto text-xs text-slate-600">{item.path}</span>
                </Command.Item>
              ))}
            </Command.Group>

            {/* Quick Actions */}
            <Command.Group heading="Quick Actions">
              {QUICK_ACTIONS.map((item) => (
                <Command.Item
                  key={item.label}
                  value={item.label}
                  onSelect={() => go(item.path)}
                  className="mx-2 flex cursor-pointer items-center rounded-md px-4 py-2.5 text-sm text-slate-300 aria-selected:bg-amber-500/10 aria-selected:text-amber-400"
                >
                  <span>{item.label}</span>
                  <span className="ml-auto text-xs text-slate-600">action</span>
                </Command.Item>
              ))}
            </Command.Group>

            {/* Contacts Search */}
            {(contactResults.length > 0 || loadingContacts) && (
              <Command.Group heading="Contacts">
                {loadingContacts && contactResults.length === 0 && (
                  <div className="flex items-center justify-center py-4 text-sm text-slate-500">
                    Searching contacts...
                  </div>
                )}
                {contactResults.map((c) => (
                  <Command.Item
                    key={c.id}
                    value={`${c.full_name ?? ''} ${c.current_title ?? ''} ${c.current_company ?? ''}`}
                    onSelect={() => go(`/contacts?highlight=${c.id}`)}
                    className="mx-2 flex cursor-pointer items-center rounded-md px-4 py-2.5 text-sm text-slate-300 aria-selected:bg-amber-500/10 aria-selected:text-amber-400"
                  >
                    <span className="truncate">
                      {c.full_name ?? 'Unknown'}
                      {(c.current_title || c.current_company) && (
                        <span className="text-slate-500">
                          {' — '}
                          {[c.current_title, c.current_company].filter(Boolean).join(' at ')}
                        </span>
                      )}
                    </span>
                    <WarmScoreBadge score={c.warm_score} />
                  </Command.Item>
                ))}
              </Command.Group>
            )}
          </Command.List>

          {/* Footer hint */}
          <div className="flex items-center justify-between border-t border-slate-700/50 px-4 py-2">
            <span className="text-xs text-slate-600">
              <kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-500">↑↓</kbd> navigate
            </span>
            <span className="text-xs text-slate-600">
              <kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-500">↵</kbd> select
              <span className="mx-2">·</span>
              <kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-500">esc</kbd> close
            </span>
          </div>
        </Command>
      </div>
    </div>
  );
}
