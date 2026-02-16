import { useMemo } from 'react';

const rules = [
  { test: (p) => p.length >= 8, label: '8+ characters' },
  { test: (p) => /[A-Z]/.test(p), label: 'Uppercase letter' },
  { test: (p) => /[a-z]/.test(p), label: 'Lowercase letter' },
  { test: (p) => /[0-9]/.test(p), label: 'Number' },
];

export default function PasswordStrength({ password }) {
  const passed = useMemo(() => rules.filter((r) => r.test(password)).length, [password]);

  if (!password) return null;

  const colors = ['bg-red-400', 'bg-orange-400', 'bg-yellow-400', 'bg-lime-400', 'bg-green-500'];
  const barColor = colors[passed];

  return (
    <div className="mt-2 space-y-2">
      <div className="flex gap-1">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className={`h-1.5 flex-1 rounded-full transition-colors ${
              i < passed ? barColor : 'bg-slate-200'
            }`}
          />
        ))}
      </div>
      <ul className="grid grid-cols-2 gap-x-2 gap-y-0.5">
        {rules.map((r) => (
          <li
            key={r.label}
            className={`text-xs ${r.test(password) ? 'text-green-600' : 'text-slate-400'}`}
          >
            {r.test(password) ? '\u2713' : '\u2022'} {r.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
