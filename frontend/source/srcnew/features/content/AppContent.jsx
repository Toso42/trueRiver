import TracksView from './views/TracksView';
import AlbumsView from './views/AlbumsView';
import ArtistsView from './views/ArtistsView';
import SourceFoldersView from './views/SourceFoldersView';
import MetadataView from './views/MetadataView';
import SettingsView from './views/SettingsView';

const viewRegistry = {
  tracks: TracksView,
  albums: AlbumsView,
  artists: ArtistsView,
  'source-folders': SourceFoldersView,
  metadata: MetadataView,
  settings: SettingsView,
};

export default function AppContent({ currentView = 'tracks' }) {
  const CurrentView = viewRegistry[currentView] || TracksView;

  return (
    <main className="app-content-region">
      <CurrentView />
    </main>
  );
}
