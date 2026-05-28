import { getJson, writeJson } from './client';

export function fetchDedupState() {
  return Promise.all([
    getJson('/api/track-dedup-jobs/latest/', 'Unable to read dedup job').catch((error) => {
      if (String(error.message || '').includes('[404]')) {
        return null;
      }
      throw error;
    }),
    getJson('/api/track-dedup-candidates/pending/', 'Unable to read dedup candidates'),
  ]).then(([latestJob, candidates]) => ({
    latest_job: latestJob,
    candidates: Array.isArray(candidates) ? candidates : [],
  }));
}

export function startDedupScan() {
  return writeJson('/api/track-dedup-jobs/start-scan/', 'POST', {}, 'Unable to start dedup scan');
}

export function cancelDedupJob(jobId) {
  return writeJson(`/api/track-dedup-jobs/${jobId}/cancel/`, 'POST', {}, 'Unable to cancel dedup job');
}

export function fullThrottleDedupJob(jobId, durationSeconds = 600) {
  return writeJson(
    `/api/track-dedup-jobs/${jobId}/full-throttle/`,
    'POST',
    { duration_seconds: durationSeconds },
    'Unable to update dedup throttle',
  );
}

export function acceptDedupCandidateAsVersions(candidateId) {
  return writeJson(
    `/api/track-dedup-candidates/${candidateId}/accept-as-versions/`,
    'POST',
    {},
    'Unable to accept dedup candidate',
  );
}

export function rejectDedupCandidate(candidateId) {
  return writeJson(`/api/track-dedup-candidates/${candidateId}/reject/`, 'POST', {}, 'Unable to reject dedup candidate');
}
