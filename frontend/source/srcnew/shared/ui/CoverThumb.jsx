function DefaultCoverArt({ kind = 'track' }) {
  const radius = kind === 'artist' ? 60 : kind === 'album' ? 22 : 28;
  const fontSize = kind === 'artist' ? 30 : kind === 'album' ? 30 : 28;
  const textX = kind === 'artist' ? 26 : 26;
  const textY = kind === 'artist' ? 84 : 84;

  return (
    <svg className="default-cover-art" viewBox="0 0 120 120" aria-hidden="true">
      <rect x="0" y="0" width="120" height="120" rx={radius} fill="rgba(73,160,123,0.08)" stroke="transparent" />
      <text
        x={textX}
        y={textY}
        fontFamily="Georgia, 'Times New Roman', serif"
        fontStyle="italic"
        fontSize={fontSize}
        fill="currentColor"
        opacity="0.9"
      >
        tR
      </text>
    </svg>
  );
}

export default function CoverThumb({ coverUrl = '', alt = '', kind = 'album' }) {
  const hasCover = Boolean(coverUrl);

  return (
    <span className={`cover-thumb cover-thumb-${kind}${hasCover ? '' : ' is-fallback'}`}>
      <DefaultCoverArt kind={kind} />
      {hasCover ? <img src={coverUrl} alt={alt} loading="lazy" /> : null}
    </span>
  );
}
