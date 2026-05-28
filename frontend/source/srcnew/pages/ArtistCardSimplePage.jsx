import { useState } from 'react';
import { PlayerPlayIcon, PlusIcon } from '../shared/ui/TablerIcons';

const sampleArtist = {
  id: 'bd44aa84-a78d-4b13-b64d-f738cf03cff0',
  name: 'Aidan Coffey',
  track_count: 18,
  cover_url: '/api/artists/bd44aa84-a78d-4b13-b64d-f738cf03cff0/cover/',
};

function SimpleArtistActions() {
  return (
    <div className="simple-artist-actions">
      <button type="button" className="album-play-pill" aria-label="Play artist">
        <PlayerPlayIcon />
      </button>
      <button type="button" className="album-queue-pill" aria-label="Add artist to queue">
        <PlusIcon />
      </button>
    </div>
  );
}

function ArtistCopyText({ artist = sampleArtist }) {
  return (
    <>
      <h3>{artist.name}</h3>
      <p>Artist index</p>
      <span>{artist.track_count} linked tracks</span>
    </>
  );
}

function SimpleArtistCopy({ artist = sampleArtist }) {
  return (
    <div className="simple-artist-copy">
      <div className="simple-artist-copy-transform">
        <ArtistCopyText artist={artist} />
      </div>
      <div className="simple-artist-copy-crossfade">
        <div className="simple-artist-copy-layer simple-artist-copy-layer-rest">
          <ArtistCopyText artist={artist} />
        </div>
        <div className="simple-artist-copy-layer simple-artist-copy-layer-hover" aria-hidden="true">
          <ArtistCopyText artist={artist} />
        </div>
      </div>
    </div>
  );
}

function SimpleArtistCard({ artist = sampleArtist }) {
  return (
    <article className="simple-artist-card">
      <span className="simple-artist-card-surface" aria-hidden="true" />
      <div className="simple-artist-media">
        <div className="simple-artist-portrait">
          <span className="simple-artist-ring" aria-hidden="true" />
          <span className="simple-artist-image-frame">
            <img className="simple-artist-image" src={artist.cover_url} alt="" loading="lazy" />
          </span>
        </div>
        <SimpleArtistActions />
      </div>
      <SimpleArtistCopy artist={artist} />
    </article>
  );
}

function PartPanel({ label, children }) {
  return (
    <figure className="simple-artist-part-panel">
      <div className="simple-artist-part-preview">
        {children}
      </div>
      <figcaption>{label}</figcaption>
    </figure>
  );
}

const partPanels = [
  {
    label: '.simple-artist-card',
    render: () => <SimpleArtistCard />,
  },
  {
    label: '.simple-artist-card-surface',
    render: () => <span className="simple-artist-card-surface simple-artist-part-card-surface" aria-hidden="true" />,
  },
  {
    label: '.simple-artist-media',
    render: () => (
      <div className="simple-artist-media simple-artist-part-media">
        <div className="simple-artist-portrait">
          <span className="simple-artist-ring" aria-hidden="true" />
          <span className="simple-artist-image-frame">
            <img className="simple-artist-image" src={sampleArtist.cover_url} alt="" loading="lazy" />
          </span>
        </div>
        <SimpleArtistActions />
      </div>
    ),
  },
  {
    label: '.simple-artist-portrait',
    render: () => <div className="simple-artist-portrait simple-artist-part-portrait" />,
  },
  {
    label: '.simple-artist-image',
    render: () => <img className="simple-artist-image simple-artist-part-image" src={sampleArtist.cover_url} alt="" loading="lazy" />,
  },
  {
    label: '.simple-artist-image-frame',
    render: () => (
      <span className="simple-artist-image-frame simple-artist-part-image-frame">
        <img className="simple-artist-image" src={sampleArtist.cover_url} alt="" loading="lazy" />
      </span>
    ),
  },
  {
    label: '.simple-artist-ring',
    render: () => <span className="simple-artist-ring simple-artist-part-ring" aria-hidden="true" />,
  },
  {
    label: '.simple-artist-actions',
    render: () => (
      <div className="simple-artist-actions simple-artist-part-actions">
        <button type="button" className="album-play-pill" aria-label="Play artist">
          <PlayerPlayIcon />
        </button>
        <button type="button" className="album-queue-pill" aria-label="Add artist to queue">
          <PlusIcon />
        </button>
      </div>
    ),
  },
  {
    label: '.album-play-pill',
    render: () => (
      <button type="button" className="album-play-pill simple-artist-part-pill" aria-label="Play artist">
        <PlayerPlayIcon />
      </button>
    ),
  },
  {
    label: '.album-queue-pill',
    render: () => (
      <button type="button" className="album-queue-pill simple-artist-part-pill" aria-label="Add artist to queue">
        <PlusIcon />
      </button>
    ),
  },
  {
    label: '.simple-artist-copy',
    render: () => <SimpleArtistCopy />,
  },
];

export default function ArtistCardSimplePage() {
  const [hoveringCard, setHoveringCard] = useState(false);
  const [copyMode, setCopyMode] = useState('shift');
  const copyModes = ['scale', 'crossfade', 'font-size', 'shift'];
  const pageClassName = [
    'simple-artist-page',
    `is-copy-${copyMode}`,
    hoveringCard ? 'is-card-hovered' : '',
  ].filter(Boolean).join(' ');

  return (
    <main className={pageClassName}>
      <div className="simple-artist-mode-switch" role="group" aria-label="Copy animation mode">
        {copyModes.map((mode) => (
          <button
            key={mode}
            type="button"
            className={copyMode === mode ? 'is-active' : ''}
            onClick={() => setCopyMode(mode)}
            aria-pressed={copyMode === mode}
          >
            {mode}
          </button>
        ))}
      </div>

      <section className="simple-artist-stage" aria-label="Simple artist card specimen">
        <div
          className="simple-artist-stage-hitbox"
          onMouseEnter={() => setHoveringCard(true)}
          onMouseLeave={() => setHoveringCard(false)}
          onFocus={() => setHoveringCard(true)}
          onBlur={() => setHoveringCard(false)}
        >
          <SimpleArtistCard />
        </div>
        <div className="simple-artist-stage-caption">.simple-artist-card</div>
      </section>

      <section className="simple-artist-parts-board" aria-label="Simple artist card parts">
        {partPanels.map((panel) => (
          <PartPanel key={panel.label} label={panel.label}>
            {panel.render()}
          </PartPanel>
        ))}
      </section>
    </main>
  );
}
