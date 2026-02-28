import { useEffect } from 'react';

interface KeyboardShortcut {
  key: string;
  ctrl?: boolean;
  meta?: boolean;
  shift?: boolean;
  action: () => void;
}

export default function useKeyboardShortcuts(shortcuts: KeyboardShortcut[], deps: React.DependencyList = []) {
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      // Don't fire in input/textarea/contenteditable
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;

      for (const shortcut of shortcuts) {
        const { key, ctrl, meta, shift, action } = shortcut;
        const modMatch = (!ctrl || e.ctrlKey) && (!meta || e.metaKey) && (!shift || e.shiftKey);
        if (e.key === key && modMatch) {
          e.preventDefault();
          action();
          return;
        }
      }
    }
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, deps);
}
