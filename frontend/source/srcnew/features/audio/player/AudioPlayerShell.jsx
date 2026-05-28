import EmptyPlayerState from './EmptyPlayerState';
import PlayerHeader from './PlayerHeader';
import PlayerTimeline from './PlayerTimeline';
import PlayerTransport from './PlayerTransport';

export default function AudioPlayerShell({
  audioRef = null,
  track = null,
  isPlaying = false,
  currentTime = 0,
  duration = 0,
  selectionRange = null,
  loopMode = 'none',
  shuffleEnabled = false,
  volume = 1,
  visualMode = 'waveform',
  cursorLockEnabled = true,
  waveformBars = [],
  waveformKey = '',
  waveformLoading = false,
  waveformZoom = 1,
  eqPanelOpen = false,
  eqGains = [],
  spectrumLevels = [],
  speedPanelOpen = false,
  pitchPanelOpen = false,
  playbackSpeed = 1,
  pitchSemitones = 0,
  pagination = null,
  onToggle = () => {},
  onPrevious = () => {},
  onNext = () => {},
  onLoopModeChange = () => {},
  onShuffleToggle = () => {},
  onVolumeChange = () => {},
  onClearSelection = () => {},
  onSeek = () => {},
  onWaveformZoomChange = () => {},
  onSelectionChange = () => {},
  onToggleVisualMode = () => {},
  onToggleCursorLock = () => {},
  onToggleEqPanel = () => {},
  onToggleSpeedPanel = () => {},
  onTogglePitchPanel = () => {},
  onEqGainChange = () => {},
  onEqReset = () => {},
  onPlaybackSpeedChange = () => {},
  onPitchSemitonesChange = () => {},
}) {
  if (!track) {
    return <EmptyPlayerState pagination={pagination} />;
  }

  return (
    <section className="player-bar player-bar-wavesurfer">
      <div className="player-main">
        <PlayerHeader track={track} />
        <div className="player-transport player-transport-wavesurfer">
          <PlayerTransport
            isPlaying={isPlaying}
            loopMode={loopMode}
            shuffleEnabled={shuffleEnabled}
            volume={volume}
            pagination={pagination}
            onToggle={onToggle}
            onPrevious={onPrevious}
            onNext={onNext}
            onLoopModeChange={onLoopModeChange}
            onShuffleToggle={onShuffleToggle}
            onVolumeChange={onVolumeChange}
          />
          <PlayerTimeline
            track={track}
            audioRef={audioRef}
            isPlaying={isPlaying}
            currentTime={currentTime}
            duration={duration}
            selectionRange={selectionRange}
            visualMode={visualMode}
            cursorLockEnabled={cursorLockEnabled}
            waveformBars={waveformBars}
            waveformKey={waveformKey}
            waveformLoading={waveformLoading}
            waveformZoom={waveformZoom}
            eqPanelOpen={eqPanelOpen}
            eqGains={eqGains}
            spectrumLevels={spectrumLevels}
            speedPanelOpen={speedPanelOpen}
            pitchPanelOpen={pitchPanelOpen}
            playbackSpeed={playbackSpeed}
            pitchSemitones={pitchSemitones}
            onSeek={onSeek}
            onWaveformZoomChange={onWaveformZoomChange}
            onSelectionChange={onSelectionChange}
            onClearSelection={onClearSelection}
            onToggleVisualMode={onToggleVisualMode}
            onToggleCursorLock={onToggleCursorLock}
            onToggleEqPanel={onToggleEqPanel}
            onToggleSpeedPanel={onToggleSpeedPanel}
            onTogglePitchPanel={onTogglePitchPanel}
            onEqGainChange={onEqGainChange}
            onEqReset={onEqReset}
            onPlaybackSpeedChange={onPlaybackSpeedChange}
            onPitchSemitonesChange={onPitchSemitonesChange}
          />
        </div>
      </div>
    </section>
  );
}
