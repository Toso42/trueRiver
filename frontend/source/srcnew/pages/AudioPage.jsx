import AudioLayout from '../layouts/AudioLayout';
import { usePathname } from '../app/simpleRouter';

const pathToView = {
  '/': 'home',
  '/audio': 'home',
  '/audio/home': 'home',
  '/audio/tracks': 'tracks',
  '/audio/videos': 'videos',
  '/audio/albums': 'albums',
  '/audio/artists': 'artists',
  '/audio/video-curation': 'video-curation',
  '/audio/trive-io': 'trive-io',
  '/audio/source-folders': 'source-folders',
  '/audio/metadata': 'metadata',
  '/audio/metadata-settings': 'metadata-settings',
  '/audio/dedup-manager': 'dedup-manager',
  '/audio/settings': 'settings',
  '/audio/server-settings': 'settings',
  '/audio/credits': 'credits',
  '/audio/users': 'users',
};

export default function AudioPage() {
  const pathname = usePathname();
  const currentView = pathToView[pathname] || 'tracks';

  return <AudioLayout currentView={currentView} />;
}
