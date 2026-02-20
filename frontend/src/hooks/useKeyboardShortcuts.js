import { useEffect } from 'react';

export default function useKeyboardShortcuts(shortcuts, deps = []) {
  useEffect(() => {
    function handler(e) {
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
