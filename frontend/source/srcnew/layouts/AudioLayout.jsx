import { useEffect, useState } from 'react';
import AudioSidebar from '../features/audio/sidebar/AudioSidebar';
import AudioPlayerShell from '../features/audio/player/AudioPlayerShell';
import AudioVisualizerOverlay from '../features/audio/player/AudioVisualizerOverlay';
import AppContent from '../features/audio/content/AppContent';
import useAudioPlayer from '../features/audio/player/hooks/useAudioPlayer';
import VideoSurface from '../features/video/VideoSurface';
import { isVideoItem } from '../features/media/mediaItem';
import { MinusIcon, NextIcon, PlayerPauseIcon, PlayerPlayIcon, PlusIcon, PreviousIcon, SparklesIcon, XIcon } from '../shared/ui/TablerIcons';
import { getArtistLabel } from '../features/audio/player/playerUtils';

const SIDEBAR_WIDTH_STORAGE_KEY = 'triver.audioSidebarWidth';
const DEFAULT_SIDEBAR_WIDTH = 304;
const MIN_SIDEBAR_WIDTH = 288;
const MAX_SIDEBAR_WIDTH = 420;

function clampSidebarWidth(width) {
  return Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, width));
}

function getInitialSidebarWidth() {
  if (typeof window === 'undefined') {
    return DEFAULT_SIDEBAR_WIDTH;
  }
  const storedValue = window.localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY);
  const storedWidth = Number(storedValue);
  return storedValue !== null && Number.isFinite(storedWidth) ? clampSidebarWidth(storedWidth) : DEFAULT_SIDEBAR_WIDTH;
}

function formatMiniTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return '0:00';
  }
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  const remainder = String(total % 60).padStart(2, '0');
  return `${minutes}:${remainder}`;
}

function AudioDockMini({
  track = null,
  isPlaying = false,
  currentTime = 0,
  duration = 0,
  onPrevious = () => {},
  onNext = () => {},
  onTogglePlayback = () => {},
}) {
  const progress = duration > 0 ? Math.min(100, Math.max(0, (currentTime / duration) * 100)) : 0;

  return (
    <div className="player-dock-mini">
      <div className="player-dock-mini-controls">
        <button type="button" className="player-dock-mini-button" onClick={onPrevious} disabled={!track} aria-label="Previous">
          <PreviousIcon />
        </button>
        <button type="button" className="player-dock-mini-button is-primary" onClick={onTogglePlayback} disabled={!track} aria-label={isPlaying ? 'Pause' : 'Play'}>
          {isPlaying ? <PlayerPauseIcon /> : <PlayerPlayIcon />}
        </button>
        <button type="button" className="player-dock-mini-button" onClick={onNext} disabled={!track} aria-label="Next">
          <NextIcon />
        </button>
      </div>
      <div className="player-dock-mini-copy">
        <strong>{track?.canonical_title || 'No track playing'}</strong>
        <span>{track ? `${getArtistLabel(track)} · ${formatMiniTime(currentTime)} / ${formatMiniTime(duration)}` : 'Select a track'}</span>
      </div>
      <div className="player-dock-mini-timeline" aria-hidden="true">
        <span style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}

function PlayerDock({ title, expanded = true, onToggle = () => {}, onClose = null, collapsedContent = null, extraActions = null, children = null }) {
  return (
    <section className={`player-dock${expanded ? ' is-open' : ' is-collapsed'}`}>
      <div className="player-dock-bar">
        <div className="player-dock-bar-main">
          <strong className="player-dock-title">{title}</strong>
          {!expanded ? collapsedContent : null}
        </div>
        <div className="player-dock-actions">
          {extraActions}
          <button type="button" className="player-dock-button" onClick={onToggle} aria-label={expanded ? `Collapse ${title}` : `Expand ${title}`}>
            {expanded ? <MinusIcon /> : <PlusIcon />}
          </button>
          {onClose ? (
            <button type="button" className="player-dock-button is-danger" onClick={onClose} aria-label={`Close ${title}`}>
              <XIcon />
            </button>
          ) : null}
        </div>
      </div>
      <div className="player-dock-body" aria-hidden={!expanded}>
        <div className="player-dock-body-inner">{children}</div>
      </div>
    </section>
  );
}

export default function AudioLayout({ currentView = 'tracks' }) {
  const player = useAudioPlayer();
  const [sidebarWidth, setSidebarWidth] = useState(getInitialSidebarWidth);
  const [audioPlayerExpanded, setAudioPlayerExpanded] = useState(true);
  const [videoPlayerExpanded, setVideoPlayerExpanded] = useState(true);
  const [audioVisualizerOpen, setAudioVisualizerOpen] = useState(false);
  const [dismissedVideoTrackId, setDismissedVideoTrackId] = useState(null);
  const currentTrack = player.playerProps.track;
  const currentVideoTrack = isVideoItem(currentTrack) ? currentTrack : null;
  const audioPlayerTrack = currentVideoTrack ? null : currentTrack;
  const showVideoPlayer = Boolean(currentVideoTrack && dismissedVideoTrackId !== currentVideoTrack.id);
  const nextAudioTrack = player.queueIndex >= 0 ? player.queue[player.queueIndex + 1] || null : null;

  useEffect(() => {
    if (!showVideoPlayer) return;
    setAudioPlayerExpanded(false);
    setVideoPlayerExpanded(true);
  }, [showVideoPlayer, currentVideoTrack?.id]);

  useEffect(() => {
    if (!currentVideoTrack) {
      setDismissedVideoTrackId(null);
      return;
    }
    if (dismissedVideoTrackId && dismissedVideoTrackId !== currentVideoTrack.id) {
      setDismissedVideoTrackId(null);
    }
  }, [currentVideoTrack, dismissedVideoTrackId]);

  useEffect(() => {
    if (!audioPlayerTrack) {
      setAudioVisualizerOpen(false);
    }
  }, [audioPlayerTrack]);

  const handleCloseVideoPlayer = () => {
    if (currentVideoTrack?.id) {
      setDismissedVideoTrackId(currentVideoTrack.id);
    }
    player.actions.stopPlayback();
  };

  const handleSidebarResizePointerDown = (event) => {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();

    const startX = event.clientX;
    const startWidth = sidebarWidth;
    let nextWidth = startWidth;

    document.body.classList.add('is-resizing-sidebar-width');

    const handlePointerMove = (moveEvent) => {
      nextWidth = clampSidebarWidth(startWidth + moveEvent.clientX - startX);
      setSidebarWidth(nextWidth);
    };

    const finishResize = () => {
      document.body.classList.remove('is-resizing-sidebar-width');
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', finishResize);
      window.removeEventListener('pointercancel', finishResize);
      window.localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(Math.round(nextWidth)));
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', finishResize);
    window.addEventListener('pointercancel', finishResize);
  };

  return (
    <main className="app-shell" style={{ '--sidebar-width': `${sidebarWidth}px` }}>
      <audio ref={player.audioRef} preload="metadata" />
      <div className="sidebar-shell" onContextMenuCapture={(event) => event.preventDefault()}>
        <AudioSidebar
          currentView={currentView}
          queue={player.queue}
          queueIndex={player.queueIndex}
          playerActions={player.actions}
        />
        <button
          type="button"
          className="sidebar-width-resize-handle"
          aria-label="Resize sidebar width"
          onPointerDown={handleSidebarResizePointerDown}
        />
      </div>
      <section className="player-shell" onContextMenuCapture={(event) => event.preventDefault()}>
        <PlayerDock
          title="Audio Player"
          expanded={audioPlayerExpanded}
          onToggle={() => setAudioPlayerExpanded((current) => !current)}
          extraActions={(
            <button
              type="button"
              className={`player-dock-button${audioVisualizerOpen ? ' is-active' : ''}`}
              onClick={() => setAudioVisualizerOpen(true)}
              disabled={!audioPlayerTrack}
              aria-label="Open visualizer"
              title="Visualizer"
            >
              <SparklesIcon />
            </button>
          )}
          collapsedContent={(
            <AudioDockMini
              track={audioPlayerTrack}
              isPlaying={audioPlayerTrack ? player.playerProps.isPlaying : false}
              currentTime={player.playerProps.currentTime}
              duration={player.playerProps.duration}
              onPrevious={player.playerProps.onPrevious}
              onNext={player.playerProps.onNext}
              onTogglePlayback={player.playerProps.onToggle}
            />
          )}
        >
          <div className="app-player-slot">
            <AudioPlayerShell {...player.playerProps} track={audioPlayerTrack} isPlaying={audioPlayerTrack ? player.playerProps.isPlaying : false} />
          </div>
        </PlayerDock>
        {showVideoPlayer ? (
          <PlayerDock
            title="Video Player"
            expanded={videoPlayerExpanded}
            onToggle={() => setVideoPlayerExpanded((current) => !current)}
            onClose={handleCloseVideoPlayer}
          >
            <VideoSurface track={currentVideoTrack} />
          </PlayerDock>
        ) : null}
      </section>
      <AppContent currentView={currentView} playerActions={player.actions} playerState={{ queue: player.queue, queueIndex: player.queueIndex, currentTrack: player.playerProps.track, isPlaying: player.playerProps.isPlaying }} />
      <AudioVisualizerOverlay
        open={audioVisualizerOpen}
        track={audioPlayerTrack}
        nextTrack={nextAudioTrack}
        queueIndex={player.queueIndex}
        queueLength={player.queue.length}
        isPlaying={audioPlayerTrack ? player.playerProps.isPlaying : false}
        currentTime={player.playerProps.currentTime}
        duration={player.playerProps.duration}
        volume={player.playerProps.volume}
        spectrumLevels={player.playerProps.spectrumLevels}
        onToggle={player.playerProps.onToggle}
        onPrevious={player.playerProps.onPrevious}
        onNext={player.playerProps.onNext}
        onVolumeChange={player.playerProps.onVolumeChange}
        onClose={() => setAudioVisualizerOpen(false)}
        onRequestAudioInput={player.playerProps.onRequestVisualizerAudioInput}
      />
    </main>
  );
}
