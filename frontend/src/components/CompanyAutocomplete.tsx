import { useCallback, useEffect, useRef, useState } from 'react';
import { companies as companiesApi } from '../api/client';

const SOURCE_BADGES = {
  own_contacts: { label: 'Your network', style: 'text-primary font-medium' },
  registry: { label: 'Known board', style: 'text-emerald-400' },
  discovered: { label: 'Discovered', style: 'text-sky-400' },
};

interface CompanySuggestion {
  name: string;
  source?: string;
  contact_count: number;
}

interface CompanyAutocompleteProps {
  value?: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
}

export default function CompanyAutocomplete({ value = [], onChange, placeholder }: CompanyAutocompleteProps) {
  const [input, setInput] = useState('');
  const [suggestions, setSuggestions] = useState<CompanySuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [searchedEmpty, setSearchedEmpty] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Fetch suggestions with debounce
  const fetchSuggestions = useCallback(
    (query: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (query.length < 2) {
        setSuggestions([]);
        setOpen(false);
        setSearchedEmpty(false);
        return;
      }
      debounceRef.current = setTimeout(async () => {
        setLoading(true);
        try {
          const res = await companiesApi.suggest({ q: query, limit: 8 });
          const items = (res.data ?? []).filter(
            (c) => !value.includes(c.name),
          );
          setSuggestions(items);
          setOpen(items.length > 0);
          setSearchedEmpty(items.length === 0);
          setActiveIndex(-1);
        } catch {
          // Fallback to legacy search endpoint
          try {
            const res = await companiesApi.search({ query, limit: 8 });
            const items = (res.data ?? []).filter(
              (c) => !value.includes(c.name),
            );
            setSuggestions(items);
            setOpen(items.length > 0);
            setSearchedEmpty(items.length === 0);
            setActiveIndex(-1);
          } catch {
            setSuggestions([]);
            setOpen(false);
            setSearchedEmpty(true);
          }
        } finally {
          setLoading(false);
        }
      }, 300);
    },
    [value],
  );

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const addCompany = (name: string) => {
    const trimmed = name.trim();
    if (trimmed && !value.includes(trimmed)) {
      onChange([...value, trimmed]);
    }
    setInput('');
    setSuggestions([]);
    setOpen(false);
    setActiveIndex(-1);
    setSearchedEmpty(false);
    inputRef.current?.focus();
  };

  const remove = (idx: number) => {
    onChange(value.filter((_, i) => i !== idx));
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    // Comma triggers add
    if (val.includes(',')) {
      const parts = val.split(',');
      parts.forEach((part) => {
        const trimmed = part.trim();
        if (trimmed && !value.includes(trimmed)) {
          onChange((prev) => [...prev, trimmed]);
        }
      });
      setInput('');
      setSuggestions([]);
      setOpen(false);
      return;
    }
    setInput(val);
    fetchSuggestions(val);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (open && suggestions.length > 0) {
        setActiveIndex((prev) => Math.min(prev + 1, suggestions.length - 1));
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (open) {
        setActiveIndex((prev) => Math.max(prev - 1, 0));
      }
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (open && activeIndex >= 0 && suggestions[activeIndex]) {
        addCompany(suggestions[activeIndex].name);
      } else if (input.trim()) {
        addCompany(input);
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
      setActiveIndex(-1);
    } else if (e.key === 'Backspace' && !input && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  const handleBlur = () => {
    // Delay so click on dropdown item registers before blur closes it
    setTimeout(() => {
      if (input.trim() && !open) {
        addCompany(input);
      }
    }, 200);
  };

  const handleVerifyCompany = async (name: string) => {
    setVerifying(true);
    try {
      await companiesApi.discover(name);
    } catch {
      // Still add the company even if discovery fails
    } finally {
      setVerifying(false);
    }
    addCompany(name);
  };

  return (
    <div ref={containerRef} className="relative">
      <label className="mb-1 block text-sm font-medium text-secondary-foreground">
        Target Companies
      </label>
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border bg-muted px-3 py-2 focus-within:border-ring focus-within:ring-1 focus-within:ring-ring">
        {value.map((tag, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1 text-sm text-primary"
          >
            {tag}
            <button
              type="button"
              onClick={() => remove(i)}
              className="text-primary hover:text-primary"
              aria-label={`Remove ${tag}`}
            >
              &times;
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onBlur={handleBlur}
          placeholder={value.length === 0 ? placeholder : ''}
          className="min-w-[120px] flex-1 border-none bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          aria-activedescendant={
            activeIndex >= 0 ? `company-option-${activeIndex}` : undefined
          }
        />
        {loading && (
          <svg
            className="h-4 w-4 animate-spin text-muted-foreground"
            viewBox="0 0 24 24"
            fill="none"
          >
            <circle
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="3"
              className="opacity-25"
            />
            <path
              d="M4 12a8 8 0 018-8"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
            />
          </svg>
        )}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        Type to search companies in your network, or press Enter to add any company
      </p>

      {/* Dropdown */}
      {open && (
        <ul
          role="listbox"
          className="absolute z-30 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-border bg-card shadow-xl"
        >
          {suggestions.map((company, i) => {
            const badge = SOURCE_BADGES[company.source];
            return (
              <li
                key={company.name + i}
                id={`company-option-${i}`}
                role="option"
                aria-selected={i === activeIndex}
                onMouseDown={() => addCompany(company.name)}
                onMouseEnter={() => setActiveIndex(i)}
                className={`flex cursor-pointer items-center justify-between px-3 py-2 ${
                  i === activeIndex ? 'bg-muted' : ''
                }`}
              >
                <span className="text-sm font-medium text-foreground">
                  {company.name}
                </span>
                <span className="flex items-center gap-2">
                  {badge && (
                    <span className={`text-[10px] ${badge.style}`}>
                      {badge.label}
                    </span>
                  )}
                  <span
                    className={`text-xs ${
                      company.contact_count > 0
                        ? 'font-medium text-primary'
                        : 'text-muted-foreground'
                    }`}
                  >
                    {company.contact_count}{' '}
                    {company.contact_count === 1 ? 'connection' : 'connections'}
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {/* "Not found" state — show when suggestions are empty after a search */}
      {searchedEmpty && input.length >= 2 && !loading && (
        <div className="absolute z-30 mt-1 w-full rounded-lg border border-border bg-card p-3 shadow-xl">
          <p className="text-sm text-muted-foreground">
            &ldquo;{input}&rdquo; isn&rsquo;t in our network yet.
          </p>
          <button
            type="button"
            onMouseDown={() => handleVerifyCompany(input)}
            disabled={verifying}
            className="mt-2 rounded-md bg-primary/10 px-3 py-1.5 text-sm font-medium text-primary hover:bg-primary/20 disabled:opacity-50"
          >
            {verifying ? 'Verifying...' : 'Add & verify'}
          </button>
        </div>
      )}
    </div>
  );
}
