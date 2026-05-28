import { LinkButton } from '../../app/simpleRouter';

const audioNavItems = [
  { to: '/audio/tracks', label: 'Tracks' },
  { to: '/audio/albums', label: 'Albums' },
  { to: '/audio/artists', label: 'Artists' },
  { to: '/audio/source-folders', label: 'SourceFolders' },
  { to: '/audio/metadata', label: 'Metadata' },
  { to: '/audio/settings', label: 'Settings' },
];

export default function Sidebar() {
  return (
    <aside className="sidebar-region">
      <div className="sidebar-panel">
        <span className="sidebar-kicker">Audio Navigation</span>
        <h2>Sidebar</h2>
        <nav className="sidebar-nav">
          {audioNavItems.map((item) => (
            <LinkButton key={item.to} to={item.to} className="sidebar-link">
              {item.label}
            </LinkButton>
          ))}
        </nav>
      </div>
    </aside>
  );
}
