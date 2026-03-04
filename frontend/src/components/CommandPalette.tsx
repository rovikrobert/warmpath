import { useEffect, useState, useRef, useCallback } from 'react';
import { Command } from 'cmdk';
import { useNavigate } from 'react-router-dom';
import { contacts as contactsApi } from '../api/client';
import MatchBadge from './MatchBadge';

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

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [contactResults, setContactResults] = useState<any[]>([]);
  const [loadingContacts, setLoadingContacts] = useState(false);
  const navigate = useNavigate();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Toggle on Cmd+K / Ctrl+K
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
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
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setOpen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  // Debounced contact search
  const searchContacts = useCallback((query: string) => {
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
      } catch (err) {
        console.error('CommandPalette: failed to search contacts', err);
        setContactResults([]);
      } finally {
        setLoadingContacts(false);
      }
    }, 300);
  }, []);

  const handleSearchChange = (value: string) => {
    setSearch(value);
    searchContacts(value);
  };

  const go = (path: string) => {
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
      <div className="relative mx-auto mt-[20vh] max-w-lg rounded-xl border border-border bg-card shadow-2xl">
        <Command label="Command palette" shouldFilter={true}>
          <Command.Input
            ref={inputRef}
            value={search}
            onValueChange={handleSearchChange}
            placeholder="Search contacts, pages, actions..."
            className="w-full border-b border-border bg-transparent px-4 py-3 text-lg text-foreground placeholder:text-muted-foreground outline-none"
          />

          <Command.List className="max-h-80 overflow-y-auto p-2">
            <Command.Empty className="flex items-center justify-center py-8 text-sm text-muted-foreground">
              No results found.
            </Command.Empty>

            {/* Navigation */}
            <Command.Group heading="Navigation">
              {NAV_ITEMS.map((item) => (
                <Command.Item
                  key={item.path}
                  value={item.label}
                  onSelect={() => go(item.path)}
                  className="mx-2 flex cursor-pointer items-center rounded-md px-4 py-2.5 text-sm text-secondary-foreground aria-selected:bg-primary/10 aria-selected:text-primary"
                >
                  <span>{item.label}</span>
                  <span className="ml-auto text-xs text-muted-foreground">{item.path}</span>
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
                  className="mx-2 flex cursor-pointer items-center rounded-md px-4 py-2.5 text-sm text-secondary-foreground aria-selected:bg-primary/10 aria-selected:text-primary"
                >
                  <span>{item.label}</span>
                  <span className="ml-auto text-xs text-muted-foreground">action</span>
                </Command.Item>
              ))}
            </Command.Group>

            {/* Contacts Search */}
            {(contactResults.length > 0 || loadingContacts) && (
              <Command.Group heading="Contacts">
                {loadingContacts && contactResults.length === 0 && (
                  <div className="flex items-center justify-center py-4 text-sm text-muted-foreground">
                    Searching contacts...
                  </div>
                )}
                {contactResults.map((c) => (
                  <Command.Item
                    key={c.id}
                    value={`${c.full_name ?? ''} ${c.current_title ?? ''} ${c.current_company ?? ''}`}
                    onSelect={() => go(`/contacts?highlight=${c.id}`)}
                    className="mx-2 flex cursor-pointer items-center rounded-md px-4 py-2.5 text-sm text-secondary-foreground aria-selected:bg-primary/10 aria-selected:text-primary"
                  >
                    <span className="truncate">
                      {c.full_name ?? 'Unknown'}
                      {(c.current_title || c.current_company) && (
                        <span className="text-muted-foreground">
                          {' — '}
                          {[c.current_title, c.current_company].filter(Boolean).join(' at ')}
                        </span>
                      )}
                    </span>
                    {c.warm_score != null && <MatchBadge score={c.warm_score} type="warm" showScore />}
                  </Command.Item>
                ))}
              </Command.Group>
            )}
          </Command.List>

          {/* Footer hint */}
          <div className="flex items-center justify-between border-t border-border px-4 py-2">
            <span className="text-xs text-muted-foreground">
              <kbd className="rounded bg-muted px-1.5 py-0.5 text-muted-foreground">↑↓</kbd> navigate
            </span>
            <span className="text-xs text-muted-foreground">
              <kbd className="rounded bg-muted px-1.5 py-0.5 text-muted-foreground">↵</kbd> select
              <span className="mx-2">·</span>
              <kbd className="rounded bg-muted px-1.5 py-0.5 text-muted-foreground">esc</kbd> close
            </span>
          </div>
        </Command>
      </div>
    </div>
  );
}
