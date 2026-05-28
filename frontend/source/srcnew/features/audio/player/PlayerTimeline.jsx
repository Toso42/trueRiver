import PlayerTimelineVisual from './PlayerTimelineVisual';
import { formatClockTime } from './playerUtils';
import { LockIcon, LockOpenIcon } from '../../../shared/ui/TablerIcons';

export default function PlayerTimeline({
  track = null,
  audioRef = null,
  isPlaying = false,
  currentTime = 0,
  duration = 0,
  selectionRange = null,
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
  onSeek = () => {},
  onWaveformZoomChange = () => {},
  onSelectionChange = () => {},
  onClearSelection = () => {},
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
  const disabled = !track;
  const waveformActive = visualMode === 'waveform';
  const selectionLabel = selectionRange
    ? `${formatClockTime(Math.min(selectionRange.start, selectionRange.end))} - ${formatClockTime(Math.max(selectionRange.start, selectionRange.end))}`
    : formatClockTime(duration || track?.duration_seconds || 0);
  const bitrateLabel = track?.bitrate_kbps ? `${track.bitrate_kbps} kbps` : 'n/a';
  const formatLabel = track?.audio_format || track?.format || 'n/a';
  const pitchPercent = ((2 ** (pitchSemitones / 12)) - 1) * 100;

  function setPitchPercent(nextPercent) {
    const clamped = Math.max(-50, Math.min(50, Number(nextPercent) || 0));
    const semitones = 12 * Math.log2(1 + (clamped / 100));
    onPitchSemitonesChange(Number.isFinite(semitones) ? semitones : 0);
  }

  return (
    <div className="player-timeline-shell player-timeline-shell-wavesurfer">
      <PlayerTimelineVisual
        visualMode={visualMode}
        cursorLockEnabled={cursorLockEnabled}
        disabled={disabled}
        track={track}
        audioRef={audioRef}
        isPlaying={isPlaying}
        waveformBars={waveformBars}
        waveformKey={waveformKey}
        waveformLoading={waveformLoading}
        waveformZoom={waveformZoom}
        eqPanelOpen={eqPanelOpen}
        eqGains={eqGains}
        currentTime={currentTime}
        duration={duration || track?.duration_seconds || 0}
        spectrumLevels={spectrumLevels}
        onSeek={onSeek}
        onWaveformZoomChange={onWaveformZoomChange}
        selectionRange={selectionRange}
        onSelectionChange={onSelectionChange}
        onEqGainChange={onEqGainChange}
        onEqReset={onEqReset}
      />
      <div className="player-toolbar">
        <div className="player-toolbar-stack">
          <div className="player-timecode">
            <div className="player-timecode-group">
              <span className="player-timecode-chip">
                <strong>position</strong>
                <span>{formatClockTime(currentTime)}</span>
              </span>
              <span className="player-timecode-chip">
                <strong>{selectionRange ? 'selection' : 'duration'}</strong>
                <span>{selectionLabel}</span>
              </span>
              <span className="player-timecode-separator">|</span>
              <span className="player-timecode-chip">
                <strong>bitrate</strong>
                <span>{bitrateLabel}</span>
              </span>
              <span className="player-timecode-separator">|</span>
              <span className="player-timecode-chip">
                <strong>format</strong>
                <span>{formatLabel}</span>
              </span>
              <span className="player-timecode-separator">|</span>
            </div>
            <div className="player-toolbar-action-group">
              <button type="button" className={`player-mini-button${eqPanelOpen ? ' is-active' : ''}`} onClick={onToggleEqPanel} disabled={disabled}>
                equalizer
              </button>
              <button type="button" className={`player-mini-button${visualMode === 'spectrum' ? ' is-active' : ''}`} onClick={onToggleVisualMode} disabled={disabled}>
                Visual: {visualMode === 'spectrum' ? 'spectrum' : 'waveform'}
              </button>
              <div className="player-transport-panels player-transport-panels-tail">
                <button type="button" className={`player-mini-button${speedPanelOpen ? ' is-active' : ''}`} onClick={onToggleSpeedPanel} disabled={disabled}>
                  speed control
                </button>
                <button type="button" className={`player-mini-button${pitchPanelOpen ? ' is-active' : ''}`} onClick={onTogglePitchPanel} disabled={disabled}>
                  pitch
                </button>
              </div>
              <button
                type="button"
                className={`player-mini-button player-icon-button${cursorLockEnabled ? ' is-active' : ''}`}
                onClick={onToggleCursorLock}
                disabled={disabled || !waveformActive}
                aria-label={cursorLockEnabled ? 'Cursor locked to playhead' : 'Cursor free inspection'}
                title={cursorLockEnabled ? 'Cursor: lock on playhead' : 'Cursor: free inspection'}
              >
                {cursorLockEnabled ? <LockIcon /> : <LockOpenIcon />}
              </button>
              <button type="button" className="player-mini-button" onClick={() => onWaveformZoomChange(Math.min(waveformZoom * 2, 64))} disabled={disabled || !waveformActive}>
                +
              </button>
              <button type="button" className="player-mini-button" onClick={() => onWaveformZoomChange(Math.max(waveformZoom / 2, 1))} disabled={disabled || !waveformActive}>
                -
              </button>
              <button type="button" className="player-mini-button" onClick={onClearSelection} disabled={disabled || !selectionRange}>
                Clear Sel
              </button>
            </div>
          </div>
          <div className={`player-toolbar-trays${speedPanelOpen || pitchPanelOpen ? ' is-open' : ''}`}>
            {speedPanelOpen ? (
              <div className="player-speed-panel player-speed-panel-tray">
                <div className="player-speed-steps">
                  <button type="button" className="player-mini-button" onClick={() => onPlaybackSpeedChange(Math.max(0.1, playbackSpeed - 0.1))}>- 10%</button>
                  <strong>{Math.round(playbackSpeed * 100)}%</strong>
                  <button type="button" className="player-mini-button" onClick={() => onPlaybackSpeedChange(Math.min(4, playbackSpeed + 0.1))}>+ 10%</button>
                  <button type="button" className="player-mini-button" onClick={() => onPlaybackSpeedChange(1)}>reset</button>
                </div>
              </div>
            ) : null}
            {pitchPanelOpen ? (
              <div className="player-pitch-panel player-pitch-panel-tray">
                <label className="player-pitch-percent">
                  <span>%</span>
                  <input
                    type="number"
                    min="-50"
                    max="50"
                    step="1"
                    value={Math.round(pitchPercent)}
                    onChange={(event) => setPitchPercent(event.target.value)}
                  />
                </label>
                <div className="player-pitch-steps">
                  <button type="button" className="player-mini-button" onClick={() => onPitchSemitonesChange(pitchSemitones - 1)}>-1 st</button>
                  <strong>{pitchSemitones >= 0 ? '+' : ''}{pitchSemitones.toFixed(2)} st</strong>
                  <button type="button" className="player-mini-button" onClick={() => onPitchSemitonesChange(pitchSemitones + 1)}>+1 st</button>
                  <button type="button" className="player-mini-button" onClick={() => onPitchSemitonesChange(0)}>reset</button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
