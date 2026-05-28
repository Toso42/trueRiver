import { useEffect, useRef, useState } from 'react';

export default function SidebarAccordion({ title, children, expanded, onToggle, expandedMaxHeight = null }) {
  const contentRef = useRef(null);
  const [maxHeight, setMaxHeight] = useState(expanded ? 'none' : '0px');

  useEffect(() => {
    if (!contentRef.current) {
      return undefined;
    }

    function syncHeight() {
      if (!contentRef.current) {
        return;
      }
      if (!expanded) {
        setMaxHeight('0px');
        return;
      }
      if (expandedMaxHeight) {
        setMaxHeight(expandedMaxHeight);
        return;
      }
      setMaxHeight(`${contentRef.current.scrollHeight}px`);
    }

    syncHeight();

    const observer = new ResizeObserver(() => syncHeight());
    observer.observe(contentRef.current);
    return () => observer.disconnect();
  }, [expanded, expandedMaxHeight]);

  return (
    <section className={`sidebar-accordion${expanded ? ' is-open' : ''}`}>
      <button type="button" className="sidebar-accordion-header" onClick={onToggle}>
        <span className="nav-group-title">{title}</span>
        <span className={`sidebar-accordion-chevron${expanded ? ' is-open' : ''}`} aria-hidden="true">▾</span>
      </button>
      <div
        className={`sidebar-accordion-reveal${expandedMaxHeight ? ' has-explicit-height' : ''}`}
        style={{ maxHeight }}
      >
        <div
          ref={contentRef}
          className={`sidebar-accordion-body${expanded ? ' is-open' : ''}${expandedMaxHeight ? ' has-explicit-height' : ''}`}
        >
          {children}
        </div>
      </div>
    </section>
  );
}
