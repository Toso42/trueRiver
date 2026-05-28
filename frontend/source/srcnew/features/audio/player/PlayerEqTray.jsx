import SpectrumBars from './SpectrumBars';
import { EQ_BANDS } from './audioAnalysis';

function buildEqWavePath(levels = []) {
  if (!levels.length) {
    return '';
  }
  const width = Math.max(levels.length - 1, 1);
  const points = levels.map((value, index) => {
    const clamped = Math.max(0, Math.min(Number(value) || 0, 1));
    const x = (index / width) * 100;
    const y = 76 - (clamped * 52);
    return `${index === 0 ? 'M' : 'L'} ${x} ${y}`;
  });
  return points.join(' ');
}

export default function PlayerEqTray({
  open = false,
  overlay = false,
  gains = [],
  spectrumLevels = [],
  onGainChange = () => {},
  onReset = () => {},
}) {
  if (!open) {
    return null;
  }

  const bands = EQ_BANDS.map((band, index) => ({
    ...band,
    gain: Number(gains[index]) || 0,
  }));
  const eqWavePath = buildEqWavePath(spectrumLevels);

  return (
    <section className={`player-eq-tray${overlay ? ' player-eq-tray-overlay' : ''}`} aria-label="Equalizer">
      <div className="player-eq-tray-layout">
        <div className="player-eq-tray-controls">
          <strong>EQ</strong>
          <button type="button" className="player-mini-button" onClick={onReset}>reset</button>
        </div>
        <div className="player-eq-bands-shell">
          <svg className="player-eq-waveform-underlay" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            <path d={eqWavePath} />
          </svg>
          <SpectrumBars levels={spectrumLevels} className="player-eq-spectrum-underlay" overlay />
          <div className="player-eq-vertical-bands">
            {bands.map((band, index) => (
              <label key={band.frequency} className="player-eq-vertical-band">
                <strong>{band.label}</strong>
                <input
                  type="range"
                  min="-12"
                  max="12"
                  step="0.5"
                  value={band.gain}
                  onChange={(event) => onGainChange(index, Number(event.target.value))}
                />
                <span>{band.gain > 0 ? '+' : ''}{band.gain.toFixed(1)}</span>
              </label>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
