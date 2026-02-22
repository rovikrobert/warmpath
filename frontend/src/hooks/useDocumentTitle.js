import { useEffect } from 'react';

export default function useDocumentTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} — WarmPath` : 'WarmPath — Get Referred, Not Ignored';
    return () => {
      document.title = 'WarmPath — Get Referred, Not Ignored';
    };
  }, [title]);
}
