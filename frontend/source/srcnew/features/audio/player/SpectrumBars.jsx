import { EQ_BANDS } from './audioAnalysis';

export default function SpectrumBars({
  levels = [],
  className = '',
  showLabels = true,
  showValues = false,
  overlay = false,
}) {
  return (
    <div className={`player-spectrum-bars${overlay ? ' is-overlay' : ''}${className ? ` ${className}` : ''}`}>
      {EQ_BANDS.map((band, index) => {
        const level = Math.max(0.03, Math.min(Number(levels[index]) || 0, 1));
        return (
          <div className="player-spectrum-band" key={band.frequency}>
            {showLabels ? <strong>{band.label}</strong> : null}
            <span className="player-spectrum-column">
              <span className="player-spectrum-fill" style={{ transform: `scaleY(${level})` }} />
            </span>
            {showValues ? <span>{Math.round(level * 100)}%</span> : null}
          </div>
        );
      })}
    </div>
  );
}
