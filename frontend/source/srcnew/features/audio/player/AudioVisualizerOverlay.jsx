import { useEffect, useMemo, useRef, useState } from 'react';
import butterchurnModule from 'butterchurn';
import butterchurnPresetsMinimal from 'butterchurn-presets/lib/butterchurnPresetsMinimal.min';
import { NextIcon, PlayerPauseIcon, PlayerPlayIcon, PreviousIcon, XIcon } from '../../../shared/ui/TablerIcons';
import { getArtistLabel } from './playerUtils';

function formatTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return '0:00';
  }
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  const remainder = String(total % 60).padStart(2, '0');
  return `${minutes}:${remainder}`;
}

function drawFallbackFrame(canvas, levels, time, isPlaying) {
  const context = canvas.getContext('2d');
  if (!context) return;
  const width = canvas.width;
  const height = canvas.height;
  const cx = width / 2;
  const cy = height / 2;
  const levelAverage = levels.length
    ? levels.reduce((sum, value) => sum + value, 0) / levels.length
    : 0;
  const pulse = 0.45 + Math.min(0.55, levelAverage / 100);
  const phase = time * (isPlaying ? 0.0012 : 0.00028);

  context.fillStyle = '#050706';
  context.fillRect(0, 0, width, height);

  const gradient = context.createRadialGradient(cx, cy, 20, cx, cy, Math.max(width, height) * 0.72);
  gradient.addColorStop(0, `rgba(83, 184, 137, ${0.18 + pulse * 0.2})`);
  gradient.addColorStop(0.42, 'rgba(39, 78, 65, 0.26)');
  gradient.addColorStop(1, 'rgba(2, 4, 4, 1)');
  context.fillStyle = gradient;
  context.fillRect(0, 0, width, height);

  for (let ring = 0; ring < 5; ring += 1) {
    context.beginPath();
    const radius = Math.min(width, height) * (0.13 + ring * 0.078) * (0.86 + pulse * 0.22);
    const points = 180;
    for (let point = 0; point <= points; point += 1) {
      const angle = (point / points) * Math.PI * 2;
      const wobble = Math.sin(angle * (3 + ring) + phase * (2.2 + ring * 0.4)) * radius * 0.14 * pulse;
      const x = cx + Math.cos(angle + phase * (ring % 2 ? -0.18 : 0.18)) * (radius + wobble);
      const y = cy + Math.sin(angle - phase * 0.12) * (radius + wobble);
      if (point === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    }
    context.strokeStyle = ring % 2
      ? `rgba(205, 235, 170, ${0.1 + pulse * 0.2})`
      : `rgba(67, 181, 134, ${0.14 + pulse * 0.25})`;
    context.lineWidth = Math.max(1, width * 0.0018);
    context.stroke();
  }

  const barCount = Math.max(20, Math.min(72, levels.length || 32));
  const barWidth = width / barCount;
  for (let index = 0; index < barCount; index += 1) {
    const level = levels[index % Math.max(levels.length, 1)] || (Math.sin(phase * 4 + index) + 1) * 30;
    const barHeight = Math.max(3, (level / 100) * height * 0.22);
    context.fillStyle = `rgba(83, 184, 137, ${0.2 + Math.min(0.6, level / 120)})`;
    context.fillRect(index * barWidth, height - barHeight, Math.max(1, barWidth - 2), barHeight);
  }
}

let cachedButterchurnSupport = null;

function browserSupportsButterchurn() {
  if (cachedButterchurnSupport !== null) {
    return cachedButterchurnSupport;
  }
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextCtor) {
    cachedButterchurnSupport = false;
    return false;
  }
  try {
    const probe = document.createElement('canvas');
    const context = probe.getContext('webgl2');
    context?.getExtension?.('WEBGL_lose_context')?.loseContext?.();
    cachedButterchurnSupport = Boolean(context);
    return cachedButterchurnSupport;
  } catch (_error) {
    cachedButterchurnSupport = false;
    return false;
  }
}

function getErrorMessage(error) {
  return error?.message || 'Full visualizer unavailable in this browser.';
}

function getButterchurnApi() {
  const candidates = [
    butterchurnModule,
    butterchurnModule?.default,
    butterchurnModule?.default?.default,
    butterchurnModule?.butterchurn,
    window.butterchurn,
    window.butterchurn?.default,
  ];
  return candidates.find((candidate) => typeof candidate?.createVisualizer === 'function') || null;
}

export default function AudioVisualizerOverlay({
  open = false,
  track = null,
  nextTrack = null,
  queueIndex = -1,
  queueLength = 0,
  isPlaying = false,
  currentTime = 0,
  duration = 0,
  volume = 1,
  spectrumLevels = [],
  onToggle = () => {},
  onPrevious = () => {},
  onNext = () => {},
  onVolumeChange = () => {},
  onClose = () => {},
  onRequestAudioInput = () => null,
}) {
  const canvasRef = useRef(null);
  const visualizerRef = useRef(null);
  const connectedNodeRef = useRef(null);
  const frameRef = useRef(0);
  const spectrumLevelsRef = useRef(spectrumLevels);
  const isPlayingRef = useRef(isPlaying);
  const [engineMode, setEngineMode] = useState('starting');
  const [engineMessage, setEngineMessage] = useState('');
  const [presetIndex, setPresetIndex] = useState(0);
  const presets = useMemo(() => {
    const pack = butterchurnPresetsMinimal?.default || butterchurnPresetsMinimal;
    return pack?.getPresets?.() || {};
  }, []);
  const presetNames = useMemo(() => Object.keys(presets), [presets]);
  const progress = duration > 0 ? Math.min(100, Math.max(0, (currentTime / duration) * 100)) : 0;

  useEffect(() => {
    spectrumLevelsRef.current = spectrumLevels;
  }, [spectrumLevels]);

  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  useEffect(() => {
    if (!open || !canvasRef.current) {
      return undefined;
    }

    let cancelled = false;
    const canvas = canvasRef.current;

    function resizeCanvas() {
      const bounds = canvas.getBoundingClientRect();
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.max(1, Math.floor(bounds.width * pixelRatio));
      const height = Math.max(1, Math.floor(bounds.height * pixelRatio));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      visualizerRef.current?.setRendererSize?.(width, height);
    }

    function createButterchurnVisualizer() {
      if (!browserSupportsButterchurn()) {
        throw new Error('Full visualizer unavailable in this browser.');
      }
      const input = onRequestAudioInput?.();
      if (!input?.context || !input?.node || !presetNames.length) {
        return null;
      }
      resizeCanvas();
      const butterchurn = getButterchurnApi();
      if (!butterchurn) {
        throw new Error('Full visualizer unavailable in this browser.');
      }
      const visualizer = butterchurn.createVisualizer(input.context, canvas, {
        width: canvas.width,
        height: canvas.height,
        pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
        textureRatio: 1,
      });
      visualizer.connectAudio(input.node);
      connectedNodeRef.current = input.node;
      visualizer.loadPreset(presets[presetNames[presetIndex % presetNames.length]], 0);
      return visualizer;
    }

    try {
      setEngineMessage('');
      visualizerRef.current = createButterchurnVisualizer();
      if (visualizerRef.current) {
        setEngineMode('butterchurn');
      } else {
        setEngineMode('fallback');
        setEngineMessage('Start playback to enable the full visualizer.');
      }
    } catch (error) {
      visualizerRef.current = null;
      connectedNodeRef.current = null;
      setEngineMode('fallback');
      setEngineMessage(getErrorMessage(error));
    }

    const resizeObserver = new ResizeObserver(() => resizeCanvas());
    resizeObserver.observe(canvas);
    resizeCanvas();

    function renderFrame(timestamp) {
      if (cancelled) return;
      try {
        if (visualizerRef.current) {
          visualizerRef.current.render();
        } else {
          drawFallbackFrame(canvas, spectrumLevelsRef.current, timestamp, isPlayingRef.current);
        }
      } catch (error) {
        visualizerRef.current = null;
        connectedNodeRef.current = null;
        setEngineMode('fallback');
        setEngineMessage(getErrorMessage(error));
        drawFallbackFrame(canvas, spectrumLevelsRef.current, timestamp, isPlayingRef.current);
      }
      frameRef.current = window.requestAnimationFrame(renderFrame);
    }

    frameRef.current = window.requestAnimationFrame(renderFrame);
    return () => {
      cancelled = true;
      resizeObserver.disconnect();
      window.cancelAnimationFrame(frameRef.current);
      try {
        if (connectedNodeRef.current) {
          visualizerRef.current?.disconnectAudio?.(connectedNodeRef.current);
        }
      } catch (_error) {}
      visualizerRef.current = null;
      connectedNodeRef.current = null;
    };
  }, [onRequestAudioInput, open, presetIndex, presetNames, presets]);

  useEffect(() => {
    if (!visualizerRef.current || !presetNames.length) {
      return;
    }
    try {
      visualizerRef.current.loadPreset(presets[presetNames[presetIndex % presetNames.length]], 2.4);
    } catch (_error) {}
  }, [presetIndex, presetNames, presets]);

  if (!open) {
    return null;
  }

  return (
    <section className="audio-visualizer-overlay" aria-label="Audio visualizer">
      <canvas ref={canvasRef} className="audio-visualizer-canvas" />
      <div className="audio-visualizer-vignette" aria-hidden="true" />
      {engineMode === 'fallback' && engineMessage ? (
        <div className="audio-visualizer-status">{engineMessage}</div>
      ) : null}
      <div className="audio-visualizer-topbar">
        <div className="audio-visualizer-track">
          <span>{queueIndex >= 0 && queueLength > 0 ? `${queueIndex + 1} / ${queueLength}` : engineMode}</span>
          <strong>{track?.canonical_title || track?.title || 'No track playing'}</strong>
          <span>{track ? getArtistLabel(track) : 'trueRiver visualizer'}</span>
        </div>
        <button type="button" className="audio-visualizer-close" onClick={onClose} aria-label="Close visualizer">
          <XIcon />
        </button>
      </div>
      <div className="audio-visualizer-controls">
        <div className="audio-visualizer-next">
          <span>Next</span>
          <strong>{nextTrack?.canonical_title || nextTrack?.title || 'End of queue'}</strong>
        </div>
        <div className="audio-visualizer-transport">
          <button type="button" onClick={onPrevious} aria-label="Previous track">
            <PreviousIcon />
          </button>
          <button type="button" className="is-primary" onClick={onToggle} aria-label={isPlaying ? 'Pause' : 'Play'}>
            {isPlaying ? <PlayerPauseIcon /> : <PlayerPlayIcon />}
          </button>
          <button type="button" onClick={onNext} aria-label="Next track">
            <NextIcon />
          </button>
          <button type="button" onClick={() => setPresetIndex((current) => current + 1)}>
            Preset
          </button>
        </div>
        <label className="audio-visualizer-volume">
          <span>Volume</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={volume}
            onChange={(event) => onVolumeChange(Number(event.target.value))}
          />
          <strong>{Math.round(volume * 100)}%</strong>
        </label>
        <div className="audio-visualizer-progress">
          <span>{formatTime(currentTime)}</span>
          <div aria-hidden="true">
            <span style={{ width: `${progress}%` }} />
          </div>
          <span>{formatTime(duration)}</span>
        </div>
      </div>
    </section>
  );
}
