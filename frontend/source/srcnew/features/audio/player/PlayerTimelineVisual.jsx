import SpectrumBars from './SpectrumBars';
import PlayerEqTray from './PlayerEqTray';
import WaveSurferTimeline from './WaveSurferTimeline';

function SpectrumTimelineVisualization({ levels = [] }) {
  return (
    <div className="player-waveform-host player-spectrum-host-inline" aria-hidden="true">
      <SpectrumBars levels={levels} showLabels showValues={false} />
    </div>
  );
}

export default function PlayerTimelineVisual({
  visualMode = 'waveform',
  cursorLockEnabled = true,
  disabled = false,
  track = null,
  audioRef = null,
  isPlaying = false,
  waveformBars = [],
  waveformKey = '',
  waveformLoading = false,
  waveformZoom = 1,
  eqPanelOpen = false,
  eqGains = [],
  selectionRange = null,
  currentTime = 0,
  duration = 0,
  spectrumLevels = [],
  onSeek = () => {},
  onWaveformZoomChange = () => {},
  onSelectionChange = () => {},
  onEqGainChange = () => {},
  onEqReset = () => {},
}) {
  const visual = visualMode === 'spectrum' ? (
    <SpectrumTimelineVisualization levels={spectrumLevels} />
  ) : (
    <WaveSurferTimeline
      disabled={disabled}
      track={track}
      audioRef={audioRef}
      isPlaying={isPlaying}
      cursorLockEnabled={cursorLockEnabled}
      waveformBars={waveformBars}
      waveformKey={waveformKey}
      waveformLoading={waveformLoading}
      waveformZoom={waveformZoom}
      selectionRange={selectionRange}
      duration={duration}
      currentTime={currentTime}
      onSeek={onSeek}
      onWaveformZoomChange={onWaveformZoomChange}
      onSelectionChange={onSelectionChange}
    />
  );

  return (
    <div className={`player-timeline-visual-stage${eqPanelOpen ? ' has-eq-overlay' : ''}`}>
      {visual}
      <PlayerEqTray
        open={eqPanelOpen}
        overlay
        gains={eqGains}
        spectrumLevels={spectrumLevels}
        onGainChange={onEqGainChange}
        onReset={onEqReset}
      />
    </div>
  );
}
