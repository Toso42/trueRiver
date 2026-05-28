export default function PlayerAdjustmentPanels({
  speedOpen = false,
  pitchOpen = false,
  playbackSpeed = 1,
  pitchSemitones = 0,
  onPlaybackSpeedChange = () => {},
  onPitchSemitonesChange = () => {},
}) {
  if (!speedOpen && !pitchOpen) {
    return null;
  }

  return (
    <section className="player-adjustment-panels" aria-label="Playback adjustments">
      {speedOpen ? (
        <label className="player-adjustment-panel">
          <span>Speed</span>
          <input
            type="range"
            min="0.5"
            max="2"
            step="0.05"
            value={playbackSpeed}
            onChange={(event) => onPlaybackSpeedChange(Number(event.target.value))}
          />
          <strong>{playbackSpeed.toFixed(2)}x</strong>
        </label>
      ) : null}
      {pitchOpen ? (
        <label className="player-adjustment-panel">
          <span>Pitch</span>
          <input
            type="range"
            min="-12"
            max="12"
            step="1"
            value={pitchSemitones}
            onChange={(event) => onPitchSemitonesChange(Number(event.target.value))}
          />
          <strong>{pitchSemitones > 0 ? '+' : ''}{pitchSemitones} st</strong>
        </label>
      ) : null}
    </section>
  );
}
