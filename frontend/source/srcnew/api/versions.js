import { getJson, writeJson } from './client';

export async function fetchVersionHandlingState() {
  return getJson('/api/track-version-groups/candidates/', 'Unable to read version candidates');
}

export async function acceptVersionCandidate(candidate) {
  return writeJson(
    '/api/track-version-groups/accept-candidate/',
    'POST',
    {
      fingerprint: candidate.fingerprint,
      title: candidate.title,
      track_ids: (candidate.tracks || []).map((track) => track.id),
    },
    'Unable to accept version candidate',
  );
}

export async function rejectVersionCandidate(candidate) {
  return writeJson(
    '/api/track-version-groups/reject-candidate/',
    'POST',
    { fingerprint: candidate.fingerprint },
    'Unable to reject version candidate',
  );
}

export async function deleteVersionTrack(trackId) {
  return writeJson(
    '/api/track-version-groups/delete-track/',
    'POST',
    { track_id: trackId, confirm: true },
    'Unable to delete version track',
  );
}
