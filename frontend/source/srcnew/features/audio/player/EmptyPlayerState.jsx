import PlayerHeader from './PlayerHeader';
import PlayerTimeline from './PlayerTimeline';
import PlayerTransport from './PlayerTransport';

export default function EmptyPlayerState({ pagination = null }) {
  return (
    <section className="player-bar player-bar-wavesurfer is-empty">
      <div className="player-main">
        <PlayerHeader />
        <div className="player-transport player-transport-wavesurfer">
          <PlayerTransport disabled pagination={pagination} />
          <PlayerTimeline />
        </div>
      </div>
    </section>
  );
}
