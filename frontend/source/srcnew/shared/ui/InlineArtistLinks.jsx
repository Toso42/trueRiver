export default function InlineArtistLinks({ artists = [], onOpenArtistId, onOpenArtistName, className = '' }) {
  if (!artists.length) {
    return <span className={className}>Unknown Artist</span>;
  }

  return (
    <span className={`inline-artist-links ${className}`.trim()}>
      {artists.map((artist, index) => (
        <span key={`${artist.id || artist.name}-${index}`}>
          <button
            type="button"
            className="artist-link-button"
            onClick={(event) => {
              event.stopPropagation();
              if (artist.id && onOpenArtistId) {
                onOpenArtistId(artist.id, artist);
                return;
              }
              if (artist.name && onOpenArtistName) {
                onOpenArtistName(artist.name);
              }
            }}
          >
            {artist.name || artist}
          </button>
          {index < artists.length - 1 ? ', ' : ''}
        </span>
      ))}
    </span>
  );
}
