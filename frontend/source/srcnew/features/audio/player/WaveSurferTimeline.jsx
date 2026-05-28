import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import WaveSurfer from 'wavesurfer.js';
import RegionsPlugin from 'wavesurfer.js/dist/plugins/regions.esm.js';
import { formatClockTime } from './playerUtils';

function buildPeaks(waveformBars = []) {
  if (!Array.isArray(waveformBars) || !waveformBars.length) {
    return null;
  }

  return [
    waveformBars.map((point) => {
      const min = Math.abs(Number(point?.min) || 0);
      const max = Math.abs(Number(point?.max) || 0);
      return Math.max(min, max);
    }),
  ];
}

function chooseRulerStep(pxPerSec) {
  const targetSeconds = 90 / Math.max(pxPerSec, 0.001);
  const steps = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
  return steps.find((step) => step >= targetSeconds) || steps[steps.length - 1];
}

export default function WaveSurferTimeline({
  disabled = false,
  track = null,
  audioRef = null,
  isPlaying = false,
  cursorLockEnabled = true,
  waveformBars = [],
  waveformKey = '',
  waveformLoading = false,
  waveformZoom = 1,
  selectionRange = null,
  duration = 0,
  currentTime = 0,
  onSeek = () => {},
  onWaveformZoomChange = () => {},
  onSelectionChange = () => {},
}) {
  const containerRef = useRef(null);
  const wavesurferRef = useRef(null);
  const regionsRef = useRef(null);
  const regionSyncRef = useRef(false);
  const pendingZoomAnchorRef = useRef(null);
  const scrollbarDragRef = useRef(null);
  const onSeekRef = useRef(onSeek);
  const onSelectionChangeRef = useRef(onSelectionChange);
  const currentTimeRef = useRef(currentTime);
  const selectionRangeRef = useRef(selectionRange);
  const [scrollState, setScrollState] = useState({ left: 0, width: 1, visibleWidth: 1 });
  const peaks = useMemo(() => buildPeaks(waveformBars), [waveformBars]);
  const safeDuration = Math.max(Number(duration || track?.duration_seconds || 0), 0.001);
  const hasPeaks = Boolean(peaks?.[0]?.length);
  const absoluteRulerWidth = Math.max(
    scrollState.width,
    scrollState.visibleWidth * Math.max(Number(waveformZoom) || 1, 1),
    scrollState.visibleWidth,
    1,
  );
  const pxPerSec = Math.max(absoluteRulerWidth / safeDuration, 1);
  const rulerStep = chooseRulerStep(pxPerSec);
  const rulerTicks = useMemo(() => {
    const ticks = [];
    const visibleStart = Math.max(scrollState.left / pxPerSec, 0);
    const visibleEnd = Math.min((scrollState.left + scrollState.visibleWidth) / pxPerSec, safeDuration);
    const firstMajor = Math.floor(visibleStart / rulerStep) * rulerStep;
    const minorStep = rulerStep / 5;

    for (let majorTime = firstMajor; majorTime <= visibleEnd + rulerStep; majorTime += rulerStep) {
      for (let index = 0; index < 5; index += 1) {
        const time = majorTime + (minorStep * index);
        if (time < 0 || time > safeDuration || time < visibleStart - minorStep || time > visibleEnd + minorStep) {
          continue;
        }
        ticks.push({
          time,
          left: time * pxPerSec,
          kind: index === 0 ? 'major' : 'minor',
        });
      }
    }
    return ticks;
  }, [pxPerSec, rulerStep, safeDuration, scrollState.left, scrollState.visibleWidth]);
  const scrollbarEnabled = absoluteRulerWidth > scrollState.visibleWidth + 2;
  const scrollbarThumbWidth = scrollbarEnabled
    ? Math.max((scrollState.visibleWidth / absoluteRulerWidth) * 100, 6)
    : 100;
  const scrollbarThumbLeft = scrollbarEnabled
    ? Math.min((scrollState.left / Math.max(absoluteRulerWidth - scrollState.visibleWidth, 1)) * (100 - scrollbarThumbWidth), 100 - scrollbarThumbWidth)
    : 0;

  const getScrollElement = useCallback(() => {
    const container = containerRef.current;
    if (!container) {
      return null;
    }
    if (container.shadowRoot) {
      const direct = container.shadowRoot.querySelector('[part="scroll"]');
      if (direct) {
        return direct;
      }
    }
    const nestedHost = Array.from(container.querySelectorAll('*')).find((node) => (
      node.shadowRoot?.querySelector?.('[part="scroll"]')
    ));
    return nestedHost?.shadowRoot?.querySelector?.('[part="scroll"]') || container.querySelector('[part="scroll"]');
  }, []);

  const syncScrollState = useCallback(() => {
    const scrollElement = getScrollElement();
    if (!scrollElement) {
      return;
    }
    setScrollState({
      left: Math.max(scrollElement.scrollLeft || 0, 0),
      width: Math.max(scrollElement.scrollWidth || 1, 1),
      visibleWidth: Math.max(scrollElement.clientWidth || 1, 1),
    });
  }, [getScrollElement]);

  useEffect(() => {
    onSeekRef.current = onSeek;
  }, [onSeek]);

  useEffect(() => {
    onSelectionChangeRef.current = onSelectionChange;
  }, [onSelectionChange]);

  useEffect(() => {
    currentTimeRef.current = currentTime;
  }, [currentTime]);

  useEffect(() => {
    selectionRangeRef.current = selectionRange;
  }, [selectionRange]);

  useEffect(() => {
    const container = containerRef.current;
    const media = audioRef?.current;
    if (!container || !media || disabled || !track) {
      return undefined;
    }

    const regionsPlugin = RegionsPlugin.create();
    const wavesurfer = WaveSurfer.create({
      container,
      media,
      waveColor: 'rgba(236, 242, 238, 0.42)',
      progressColor: 'rgba(73, 160, 123, 0.84)',
      cursorColor: 'rgba(236, 242, 238, 0.96)',
      cursorWidth: 2,
      height: 78,
      normalize: false,
      dragToSeek: false,
      hideScrollbar: true,
      autoScroll: false,
      autoCenter: false,
      minPxPerSec: 1,
      interact: true,
      peaks: peaks || undefined,
      duration: safeDuration,
      plugins: [regionsPlugin],
    });

    wavesurferRef.current = wavesurfer;
    regionsRef.current = regionsPlugin;
    requestAnimationFrame(() => syncScrollState());
    const disableDragSelection = regionsPlugin.enableDragSelection({
      color: 'rgba(115, 218, 172, 0.18)',
      drag: true,
      resize: true,
    });

    const clearExtraRegions = (activeRegion) => {
      regionsPlugin.getRegions().forEach((region) => {
        if (region.id !== activeRegion.id) {
          region.remove();
        }
      });
    };

    const commitSelectionOut = (region, { seekToStart = false } = {}) => {
      if (regionSyncRef.current) {
        return;
      }
      clearExtraRegions(region);
      const nextStart = Math.min(region.start, region.end);
      const nextEnd = Math.max(region.start, region.end);
      if (Math.abs(nextEnd - nextStart) < 0.05) {
        onSelectionChangeRef.current?.(null);
        return;
      }
      onSelectionChangeRef.current?.({ start: nextStart, end: nextEnd });
      if (seekToStart) {
        onSeekRef.current?.(nextStart);
      }
    };

    const unsubscribeInteraction = wavesurfer.on('interaction', (nextTime) => {
      const currentSelection = selectionRangeRef.current;
      if (currentSelection) {
        const selectionStart = Math.min(currentSelection.start, currentSelection.end);
        const selectionEnd = Math.max(currentSelection.start, currentSelection.end);
        const clickIsOutsideSelection = nextTime < selectionStart || nextTime > selectionEnd;
        if (clickIsOutsideSelection) {
          onSelectionChangeRef.current?.(null);
          onSeekRef.current?.(currentTimeRef.current);
          return;
        }
      }
      onSeekRef.current?.(nextTime);
    });
    const unsubscribeScroll = wavesurfer.on('scroll', () => {
      syncScrollState();
    });
    const unsubscribeReady = wavesurfer.on('ready', () => {
      requestAnimationFrame(() => syncScrollState());
    });
    const unsubscribeRedraw = wavesurfer.on('redrawcomplete', () => {
      requestAnimationFrame(() => syncScrollState());
    });
    const unsubscribeRegionCreated = regionsPlugin.on('region-created', (region) => {
      commitSelectionOut(region, { seekToStart: true });
    });
    const unsubscribeRegionUpdated = regionsPlugin.on('region-updated', (region) => {
      commitSelectionOut(region, { seekToStart: true });
    });
    const unsubscribeRegionRemoved = regionsPlugin.on('region-removed', () => {
      if (!regionSyncRef.current && regionsPlugin.getRegions().length === 0) {
        onSelectionChangeRef.current?.(null);
      }
    });

    return () => {
      unsubscribeInteraction?.();
      unsubscribeScroll?.();
      unsubscribeReady?.();
      unsubscribeRedraw?.();
      unsubscribeRegionCreated?.();
      unsubscribeRegionUpdated?.();
      unsubscribeRegionRemoved?.();
      disableDragSelection?.();
      try {
        wavesurfer.destroy();
      } catch (_error) {
        // WaveSurfer may abort internal media tracking during teardown.
      }
      wavesurferRef.current = null;
      regionsRef.current = null;
    };
  }, [audioRef, disabled, syncScrollState]);

  useEffect(() => {
    const wavesurfer = wavesurferRef.current;
    if (!wavesurfer || !hasPeaks) {
      return;
    }

    wavesurfer.setOptions({
      peaks,
      duration: safeDuration,
    });
    if (typeof wavesurfer.renderer?.render === 'function') {
      const decodedData = wavesurfer.getDecodedData?.();
      if (decodedData) {
        wavesurfer.renderer.render(decodedData);
      }
    }
    requestAnimationFrame(() => syncScrollState());
  }, [hasPeaks, peaks, safeDuration, syncScrollState, track?.id, waveformKey]);

  useEffect(() => {
    const wavesurfer = wavesurferRef.current;
    if (!wavesurfer || !Number.isFinite(currentTime)) {
      return;
    }

    if (Math.abs((wavesurfer.getCurrentTime?.() || 0) - currentTime) > 0.35) {
      wavesurfer.setTime(currentTime);
    }
  }, [currentTime]);

  useEffect(() => {
    if (!cursorLockEnabled || !isPlaying || !hasPeaks) {
      return;
    }

    const playheadLeft = currentTime * pxPerSec;
    const viewportLeft = scrollState.left;
    const viewportRight = scrollState.left + scrollState.visibleWidth;
    const margin = Math.max(scrollState.visibleWidth * 0.18, 48);
    if (playheadLeft > viewportLeft + margin && playheadLeft < viewportRight - margin) {
      return;
    }

    scrollToLeft(playheadLeft - (scrollState.visibleWidth * 0.36));
  }, [currentTime, cursorLockEnabled, hasPeaks, isPlaying, pxPerSec, scrollState.left, scrollState.visibleWidth]);

  useEffect(() => {
    const wavesurfer = wavesurferRef.current;
    const container = containerRef.current;
    if (!wavesurfer || !hasPeaks || !container) {
      return;
    }

    const containerWidth = Math.max(container.getBoundingClientRect?.().width || scrollState.visibleWidth || 1, 1);
    const basePxPerSec = Math.max(containerWidth / safeDuration, 1);
    const minPxPerSec = Math.max(basePxPerSec * Math.max(Number(waveformZoom) || 1, 1), 1);
    try {
      wavesurfer.zoom(minPxPerSec);
      const pendingZoomAnchor = pendingZoomAnchorRef.current;
      pendingZoomAnchorRef.current = null;
      if (pendingZoomAnchor !== null) {
        requestAnimationFrame(() => {
          const scrollElement = getScrollElement();
          const nextVisibleWidth = Math.max(scrollElement?.clientWidth || containerWidth || 1, 1);
          const nextRenderableWidth = Math.max(nextVisibleWidth * Math.max(Number(waveformZoom) || 1, 1), nextVisibleWidth, 1);
          const nextScrollableWidth = Math.max((scrollElement?.scrollWidth || nextRenderableWidth) - nextVisibleWidth, 0);
          const nextPxPerSec = Math.max((scrollElement?.scrollWidth || nextRenderableWidth) / safeDuration, 1);
          if (scrollElement && nextScrollableWidth > 0) {
            const nextLeft = (pendingZoomAnchor.time * nextPxPerSec) - pendingZoomAnchor.localX;
            scrollElement.scrollLeft = Math.max(0, Math.min(nextLeft, nextScrollableWidth));
          }
          syncScrollState();
        });
      } else {
        requestAnimationFrame(() => syncScrollState());
      }
    } catch (_error) {
      // WaveSurfer can reject zoom before decoded peaks are fully registered.
    }
  }, [getScrollElement, hasPeaks, safeDuration, scrollState.visibleWidth, syncScrollState, waveformZoom]);

  function handleWheel(event) {
    if (disabled || !hasPeaks || event.deltaY === 0) {
      return;
    }

    event.preventDefault();
    const scrollElement = getScrollElement();
    const bounds = scrollElement?.getBoundingClientRect?.();
    const wrapperWidth = Math.max(scrollElement?.scrollWidth || absoluteRulerWidth || 1, 1);
    const currentPxPerSec = Math.max(wrapperWidth / safeDuration, 1);
    const localX = bounds?.width ? Math.max(0, Math.min(event.clientX - bounds.left, bounds.width)) : 0;
    pendingZoomAnchorRef.current = {
      localX,
      time: Math.max(0, Math.min(((scrollElement?.scrollLeft || 0) + localX) / currentPxPerSec, safeDuration)),
    };
    const factor = event.deltaY < 0 ? 1.18 : 1 / 1.18;
    onWaveformZoomChange(Math.max(1, Math.min((Number(waveformZoom) || 1) * factor, 64)));
  }

  function scrollToLeft(nextLeft) {
    const scrollElement = getScrollElement();
    if (!scrollElement) {
      return;
    }
    const maxLeft = Math.max((scrollElement.scrollWidth || absoluteRulerWidth) - (scrollElement.clientWidth || scrollState.visibleWidth), 0);
    scrollElement.scrollLeft = Math.max(0, Math.min(nextLeft, maxLeft));
    syncScrollState();
  }

  function handleScrollbarPointerDown(event) {
    if (!scrollbarEnabled) {
      return;
    }
    const bounds = event.currentTarget.getBoundingClientRect();
    const thumbLeftPx = (scrollbarThumbLeft / 100) * bounds.width;
    const thumbWidthPx = (scrollbarThumbWidth / 100) * bounds.width;
    const pointerInsideThumb = event.clientX >= bounds.left + thumbLeftPx && event.clientX <= bounds.left + thumbLeftPx + thumbWidthPx;

    if (!pointerInsideThumb) {
      const ratio = bounds.width ? Math.max(0, Math.min((event.clientX - bounds.left) / bounds.width, 1)) : 0;
      scrollToLeft((absoluteRulerWidth - scrollState.visibleWidth) * ratio);
    }

    scrollbarDragRef.current = {
      startX: event.clientX,
      startLeft: pointerInsideThumb ? scrollState.left : ((absoluteRulerWidth - scrollState.visibleWidth) * (bounds.width ? Math.max(0, Math.min((event.clientX - bounds.left) / bounds.width, 1)) : 0)),
      trackWidth: bounds.width,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function handleScrollbarPointerMove(event) {
    const dragState = scrollbarDragRef.current;
    if (!dragState) {
      return;
    }
    const scrollableWidth = Math.max(absoluteRulerWidth - scrollState.visibleWidth, 0);
    const draggableWidth = Math.max(dragState.trackWidth * (1 - (scrollbarThumbWidth / 100)), 1);
    const nextLeft = dragState.startLeft + (((event.clientX - dragState.startX) / draggableWidth) * scrollableWidth);
    scrollToLeft(nextLeft);
  }

  function handleScrollbarPointerUp() {
    scrollbarDragRef.current = null;
  }

  useEffect(() => {
    const regionsPlugin = regionsRef.current;
    if (!regionsPlugin) {
      return;
    }

    regionSyncRef.current = true;
    regionsPlugin.clearRegions();

    if (selectionRange) {
      const nextStart = Math.max(0, Math.min(selectionRange.start, selectionRange.end));
      const nextEnd = Math.min(safeDuration, Math.max(selectionRange.start, selectionRange.end));
      if (Math.abs(nextEnd - nextStart) >= 0.05) {
        regionsPlugin.addRegion({
          start: nextStart,
          end: nextEnd,
          color: 'rgba(115, 218, 172, 0.18)',
          drag: true,
          resize: true,
        });
      }
    }

    regionSyncRef.current = false;
  }, [safeDuration, selectionRange, track?.id]);

  return (
    <div
      className={`player-waveform-host player-wavesurfer-timeline${disabled ? ' is-empty' : ''}${waveformLoading ? ' is-loading' : ''}`}
      onWheel={handleWheel}
    >
      <div className="player-wavesurfer-ruler" aria-hidden="true">
        <div
          className="player-wavesurfer-ruler-content"
          style={{ width: `${absoluteRulerWidth}px`, transform: `translateX(${-scrollState.left}px)` }}
        >
          {rulerTicks.map((tick) => (
            <span
              key={`${tick.kind}-${tick.time.toFixed(3)}`}
              className={`player-wavesurfer-ruler-tick is-${tick.kind}`}
              style={{ left: `${tick.left}px` }}
            >
              {tick.kind === 'major' ? <em>{formatClockTime(tick.time)}</em> : null}
            </span>
          ))}
        </div>
      </div>
      <div ref={containerRef} className="player-wavesurfer-canvas" />
      <div
        className={`player-wavesurfer-scrollbar${scrollbarEnabled ? '' : ' is-disabled'}`}
        role="presentation"
        onPointerDown={handleScrollbarPointerDown}
        onPointerMove={handleScrollbarPointerMove}
        onPointerUp={handleScrollbarPointerUp}
        onPointerCancel={handleScrollbarPointerUp}
      >
        <span
          className="player-wavesurfer-scrollbar-thumb"
          style={{
            left: `${scrollbarThumbLeft}%`,
            width: `${scrollbarThumbWidth}%`,
          }}
        />
      </div>
      {!hasPeaks && !waveformLoading ? (
        <div className="player-wavesurfer-placeholder">
          <strong>WaveSurfer</strong>
          <span>Waveform unavailable for this track.</span>
        </div>
      ) : null}
    </div>
  );
}
