import { useEffect, useRef, useState } from 'react';

export default function MarqueeText({ text, className = '', title = '' }) {
  const normalized = String(text || '');
  const containerRef = useRef(null);
  const contentRef = useRef(null);
  const [shouldScroll, setShouldScroll] = useState(false);

  useEffect(() => {
    const evaluateOverflow = () => {
      if (!containerRef.current || !contentRef.current) {
        setShouldScroll(false);
        return;
      }
      const nextShouldScroll = contentRef.current.scrollWidth > containerRef.current.clientWidth + 2;
      setShouldScroll(nextShouldScroll);
    };

    evaluateOverflow();

    if (typeof ResizeObserver !== 'undefined') {
      const resizeObserver = new ResizeObserver(() => evaluateOverflow());
      resizeObserver.observe(containerRef.current);
      resizeObserver.observe(contentRef.current);
      return () => resizeObserver.disconnect();
    }

    window.addEventListener('resize', evaluateOverflow);
    return () => window.removeEventListener('resize', evaluateOverflow);
  }, [normalized]);

  if (!shouldScroll) {
    return (
      <span ref={containerRef} className={className} title={title || normalized}>
        <span ref={contentRef}>{normalized}</span>
      </span>
    );
  }

  return (
    <span ref={containerRef} className={`${className} marquee-text`} title={title || normalized}>
      <span className="marquee-track">
        <span ref={contentRef}>{normalized}</span>
        <span aria-hidden="true">{normalized}</span>
      </span>
    </span>
  );
}
