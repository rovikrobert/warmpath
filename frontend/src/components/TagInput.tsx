import { useState } from 'react';

interface TagInputProps {
  label?: string;
  sublabel?: string;
  value?: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
}

export default function TagInput({ label, sublabel, value = [], onChange, placeholder }: TagInputProps) {
  const [input, setInput] = useState('');

  const addTags = (text: string) => {
    const newTags = text
      .split(',')
      .map((t) => t.trim())
      .filter((t) => t && !value.includes(t));
    if (newTags.length > 0) {
      onChange([...value, ...newTags]);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
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

  const remove = (idx: number) => {
    onChange(value.filter((_, i) => i !== idx));
  };

  return (
    <div>
      {label && (
        <label className="mb-1 block text-sm font-medium text-secondary-foreground">
          {label}
        </label>
      )}
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border bg-muted px-3 py-2 focus-within:border-ring focus-within:ring-1 focus-within:ring-ring">
        {value.map((tag, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-sm text-primary"
          >
            {tag}
            <button
              type="button"
              onClick={() => remove(i)}
              className="text-primary hover:text-primary"
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
          className="min-w-[120px] flex-1 border-none bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
        />
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{sublabel || 'Press Enter or comma to add'}</p>
    </div>
  );
}
