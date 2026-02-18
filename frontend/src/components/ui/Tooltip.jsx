import { useState } from 'react';

export default function Tooltip({ content, children, position = 'top' }) {
  const [show, setShow] = useState(false);

  const positions = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  };

  return (
    <span className="relative inline-flex" onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}>
      {children}
      {show && (
        <span className={`absolute z-50 whitespace-nowrap rounded-md bg-slate-700 px-2.5 py-1.5 text-xs text-slate-100 shadow-lg transition-opacity ${positions[position]}`}>
          {content}
        </span>
      )}
    </span>
  );
}
