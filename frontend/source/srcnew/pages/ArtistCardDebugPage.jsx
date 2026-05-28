import CoverThumb from '../shared/ui/CoverThumb';
import { PlayerPlayIcon, PlusIcon } from '../shared/ui/TablerIcons';

const sampleArtist = {
  id: 'bd44aa84-a78d-4b13-b64d-f738cf03cff0',
  name: 'Aidan Coffey',
  track_count: 18,
  cover_url: '/api/artists/bd44aa84-a78d-4b13-b64d-f738cf03cff0/cover/',
};

function ArtistAperture({ artist = sampleArtist, coverOnly = false }) {
  return (
    <div className="album-aperture-cover">
      <div className="album-aperture-viewport artist-aperture-viewport">
        <button type="button" className="album-aperture-underlay artist-aperture-underlay" aria-label={artist.name}>
          <CoverThumb coverUrl={artist.cover_url} alt="" kind="artist" />
        </button>
      </div>
      <span className="album-aperture-mask artist-aperture-mask" aria-hidden="true">
        <span className="album-aperture-window artist-aperture-window" />
      </span>
      {coverOnly ? null : (
        <div className="artist-aperture-actions">
          <button type="button" className="album-play-pill" aria-label="Play artist">
            <PlayerPlayIcon />
          </button>
          <button type="button" className="album-queue-pill" aria-label="Add artist to queue">
            <PlusIcon />
          </button>
        </div>
      )}
    </div>
  );
}

function ArtistCopy({ artist = sampleArtist }) {
  return (
    <div className="album-copy">
      <h3>{artist.name}</h3>
      <p>Artist index</p>
      <span>{artist.track_count} linked tracks</span>
    </div>
  );
}

function ArtistCard({ artist = sampleArtist }) {
  return (
    <article className="album-card artist-card">
      <ArtistAperture artist={artist} />
      <ArtistCopy artist={artist} />
    </article>
  );
}

function DefaultCoverArtSpecimen() {
  return (
    <svg className="default-cover-art" viewBox="0 0 120 120" aria-hidden="true">
      <rect x="0" y="0" width="120" height="120" rx="60" fill="rgba(73,160,123,0.08)" stroke="transparent" />
      <text
        x="26"
        y="84"
        fontFamily="Georgia, 'Times New Roman', serif"
        fontStyle="italic"
        fontSize="30"
        fill="currentColor"
        opacity="0.9"
      >
        tR
      </text>
    </svg>
  );
}

function IsolatedElement({ children, tone = '' }) {
  return (
    <div className={`artist-card-debug-isolate ${tone}`.trim()}>
      {children}
    </div>
  );
}

function LayerPanel({ classNameLabel, children }) {
  return (
    <figure className="artist-card-debug-panel">
      <div className="artist-card-debug-panel-preview">
        {children}
      </div>
      <figcaption>{classNameLabel}</figcaption>
    </figure>
  );
}

const layerPanels = [
  {
    label: '.album-aperture-cover - static',
    render: () => (
      <IsolatedElement>
        <div className="album-aperture-cover artist-card-debug-single-cover" />
      </IsolatedElement>
    ),
  },
  {
    label: '.album-aperture-viewport.artist-aperture-viewport - static',
    render: () => (
      <IsolatedElement>
        <div className="album-aperture-viewport artist-aperture-viewport artist-card-debug-single-viewport" />
      </IsolatedElement>
    ),
  },
  {
    label: '.album-aperture-underlay.artist-aperture-underlay - animates inset',
    render: () => (
      <IsolatedElement>
        <button type="button" className="album-aperture-underlay artist-aperture-underlay artist-card-debug-single-underlay" aria-label={sampleArtist.name} />
      </IsolatedElement>
    ),
  },
  {
    label: '.cover-thumb.cover-thumb-artist - static',
    render: () => (
      <IsolatedElement>
        <span className="cover-thumb cover-thumb-artist artist-card-debug-single-cover-thumb" />
      </IsolatedElement>
    ),
  },
  {
    label: '.default-cover-art - static',
    render: () => (
      <IsolatedElement>
        <DefaultCoverArtSpecimen />
      </IsolatedElement>
    ),
  },
  {
    label: '.cover-thumb img - static',
    render: () => (
      <IsolatedElement>
        <img className="artist-card-debug-single-img" src={sampleArtist.cover_url} alt="" loading="lazy" />
      </IsolatedElement>
    ),
  },
  {
    label: '.album-aperture-mask.artist-aperture-mask - animates inset',
    render: () => (
      <IsolatedElement tone="artist-card-debug-mask-slot">
        <span className="album-aperture-mask artist-aperture-mask artist-card-debug-single-mask" aria-hidden="true" />
      </IsolatedElement>
    ),
  },
  {
    label: '.album-aperture-window.artist-aperture-window - animates aperture',
    render: () => (
      <IsolatedElement tone="artist-card-debug-mask-slot">
        <span className="album-aperture-window artist-aperture-window artist-card-debug-single-window" aria-hidden="true" />
      </IsolatedElement>
    ),
  },
];

export default function ArtistCardDebugPage() {
  return (
    <main className="artist-card-debug-page">
      <section className="artist-card-debug-shell">
        <section className="artist-card-debug-stage" aria-label="Artist card specimen">
          <ArtistCard />
          <div className="artist-card-debug-stage-caption">.album-card.artist-card</div>
        </section>

        <section className="artist-card-debug-board" aria-label="Artist card layers">
          {layerPanels.map((panel) => (
            <LayerPanel key={panel.label} classNameLabel={panel.label}>
              {panel.render()}
            </LayerPanel>
          ))}
        </section>
      </section>
    </main>
  );
}
