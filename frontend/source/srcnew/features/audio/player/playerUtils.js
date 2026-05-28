export function getArtistLabel(track) {
  return track?.artist_summary?.map((artist) => artist.name).join(', ') || 'Unknown Artist';
}

export function formatClockTime(seconds = 0) {
  const safeSeconds = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(safeSeconds / 60);
  const remainingSeconds = Math.floor(safeSeconds % 60);
  return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`;
}
