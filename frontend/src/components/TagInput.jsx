import { useState } from 'react';

export default function TagInput({ label, value = [], onChange, placeholder }) {
  const [input, setInput] = useState('');

  const addTags = (text) => {
    const newTags = text
      .split(',')
      .map((t) => t.trim())
      .filter((t) => t && !value.includes(t));
    if (newTags.length > 0) {
      onChange([...value, ...newTags]);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      if (input.trim()) {
        addTags(input);
        setInput('');
      }
    } else if (e.key === 'Backspace' && !input && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  const handleBlur = () => {
    if (input.trim()) {
      addTags(input);
      setInput('');
    }
  };

  const remove = (idx) => {
    onChange(value.filter((_, i) => i !== idx));
  };

  return (
    <div>
      {label && (
        <label className="mb-1 block text-sm font-medium text-slate-700">
          {label}
        </label>
      )}
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 focus-within:border-amber-500 focus-within:ring-1 focus-within:ring-amber-500">
        {value.map((tag, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-0.5 text-sm text-amber-800"
          >
            {tag}
            <button
              type="button"
              onClick={() => remove(i)}
              className="text-amber-500 hover:text-amber-700"
            >
              &times;
            </button>
          </span>
        ))}
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={handleBlur}
          placeholder={value.length === 0 ? placeholder : ''}
          className="min-w-[120px] flex-1 border-none bg-transparent text-sm outline-none placeholder:text-slate-400"
        />
      </div>
      <p className="mt-1 text-xs text-slate-400">Press Enter or comma to add</p>
    </div>
  );
}
