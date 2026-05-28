import CoverThumb from '../../../shared/ui/CoverThumb';
import { getArtistLabel } from './playerUtils';

export default function PlayerHeader({ track = null }) {
  if (!track) {
    return (
      <div className="player-header">
        <CoverThumb kind="track" />
        <div className="player-header-text">
          <strong>No track playing</strong>
          <span>Select a track or album to begin.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="player-header">
      <CoverThumb coverUrl={track.cover_url} alt="" kind="track" />
      <div className="player-header-text">
        <strong>{track.canonical_title}</strong>
        <span>{getArtistLabel(track)} · {track.album_title || 'Unknown Album'}</span>
      </div>
    </div>
  );
}
