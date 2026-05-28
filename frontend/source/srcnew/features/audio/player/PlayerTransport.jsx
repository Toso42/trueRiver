import { useEffect, useRef, useState } from 'react';
import {
  NextIcon,
  LoopOffIcon,
  LoopOnceIcon,
  LoopQueueIcon,
  PlayerPauseIcon,
  PlayerPlayIcon,
  PreviousIcon,
  ShuffleIcon,
} from '../../../shared/ui/TablerIcons';

export default function PlayerTransport({
  disabled = false,
  isPlaying = false,
  loopMode = 'none',
  shuffleEnabled = false,
  volume = 1,
  pagination = null,
  onToggle = () => {},
  onPrevious = () => {},
  onNext = () => {},
  onLoopModeChange = () => {},
  onShuffleToggle = () => {},
  onVolumeChange = () => {},
}) {
  const storedWidthRef = useRef(null);
  if (storedWidthRef.current === null) {
    try {
      const raw = window.localStorage.getItem('triver.audioPlayer.controlsWidth');
      const stored = Number(raw);
      storedWidthRef.current = Number.isFinite(stored) ? Math.min(Math.max(stored, 210), 380) : 252;
    } catch (_error) {
      storedWidthRef.current = 252;
    }
  }
  const [controlsWidth, setControlsWidth] = useState(storedWidthRef.current);
  const resizeHandleRef = useRef(null);

  useEffect(() => {
    try {
      window.localStorage.setItem('triver.audioPlayer.controlsWidth', String(controlsWidth));
    } catch (_error) {
      // Ignore storage failures.
    }
  }, [controlsWidth]);

  useEffect(() => {
    function handlePointerMove(event) {
      const dragState = resizeHandleRef.current;
      if (!dragState) {
        return;
      }
      const nextWidth = Math.max(210, Math.min(dragState.startWidth + (event.clientX - dragState.startX), 380));
      setControlsWidth(nextWidth);
    }

    function handlePointerUp() {
      resizeHandleRef.current = null;
      document.body.classList.remove('is-resizing-player-controls');
    }

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, []);

  return (
    <div className="player-controls-stack player-controls-stack-resizable" style={{ width: `${controlsWidth}px` }}>
      <div className="player-controls">
        <button type="button" className="player-button player-button-secondary" onClick={onPrevious} disabled={disabled} aria-label="Previous">
          <PreviousIcon />
        </button>
        <button type="button" className="player-button" onClick={onToggle} disabled={disabled} aria-label={isPlaying ? 'Pause' : 'Play'}>
          {isPlaying ? <PlayerPauseIcon /> : <PlayerPlayIcon />}
        </button>
        <button type="button" className="player-button player-button-secondary" onClick={onNext} disabled={disabled} aria-label="Next">
          <NextIcon />
        </button>
      </div>
      <div className="player-aux-stack">
        <div className="player-aux-controls">
          <button
            type="button"
            className={`player-mini-button player-icon-button${loopMode !== 'none' ? ' is-active' : ''}`}
            onClick={onLoopModeChange}
            disabled={disabled}
            aria-label={loopMode === 'track' ? 'Loop Track' : loopMode === 'queue' ? 'Loop Queue' : 'No Loop'}
            title={loopMode === 'track' ? 'Loop Track' : loopMode === 'queue' ? 'Loop Queue' : 'No Loop'}
          >
            {loopMode === 'track' ? <LoopOnceIcon /> : loopMode === 'queue' ? <LoopQueueIcon /> : <LoopOffIcon />}
          </button>
          <button
            type="button"
            className={`player-mini-button player-icon-button${shuffleEnabled ? ' is-active' : ''}`}
            onClick={onShuffleToggle}
            disabled={disabled}
            aria-label={shuffleEnabled ? 'Shuffle On' : 'Shuffle Off'}
            title={shuffleEnabled ? 'Shuffle On' : 'Shuffle Off'}
          >
            <ShuffleIcon />
          </button>
        </div>
        <label className={`player-volume-control${disabled ? ' is-disabled' : ''}`}>
          <span>Vol</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={volume}
            disabled={disabled}
            readOnly={disabled}
            onChange={(event) => onVolumeChange(Number(event.target.value))}
          />
          <strong>{Math.round(volume * 100)}%</strong>
        </label>
        {pagination ? (
          <>
            <div className="player-controls-divider" />
            <div className="player-pagination-slot">{pagination}</div>
          </>
        ) : null}
      </div>
      <div
        className="player-controls-resize-handle"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize player controls"
        onPointerDown={(event) => {
          resizeHandleRef.current = {
            startX: event.clientX,
            startWidth: controlsWidth,
          };
          document.body.classList.add('is-resizing-player-controls');
          event.currentTarget.setPointerCapture?.(event.pointerId);
        }}
      />
    </div>
  );
}
