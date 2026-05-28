export const VIDEO_METADATA_FIELDS = [
  { name: 'SeriesTitle', label: 'SeriesTitle', trackKey: 'series_title' },
  { name: 'SeasonNumber', label: 'SeasonNumber', trackKey: 'season_number' },
  { name: 'EpisodeNumber', label: 'EpisodeNumber', trackKey: 'episode_number' },
  { name: 'EpisodeTitle', label: 'EpisodeTitle', trackKey: 'episode_title' },
  { name: 'AbsoluteEpisodeNumber', label: 'AbsoluteEpisodeNumber', trackKey: 'absolute_episode_number' },
];

function normalizeValue(value) {
  if (value == null) {
    return '';
  }
  return String(value).trim();
}

function readTrackField(track, field) {
  return normalizeValue(track?.[field.trackKey]);
}

export function buildSingleVideoMetadataRows(baseRows = [], track = null) {
  const rowsByField = new Map((baseRows || []).map((row) => [row.field, row]));
  return VIDEO_METADATA_FIELDS.map((field) => {
    const existingRow = rowsByField.get(field.name);
    if (existingRow) {
      return {
        ...existingRow,
        section: 'triver',
        display_field: field.label,
        read_only: false,
      };
    }
    const value = readTrackField(track, field);
    return {
      section: 'triver',
      field: field.name,
      display_field: field.label,
      read_only: false,
      values: value ? [{ value }] : [],
    };
  });
}

export function buildMultiVideoMetadataRows(baseRows = [], tracks = []) {
  const rowsByField = new Map((baseRows || [])
    .filter((row) => row.section === 'triver')
    .map((row) => [row.field, row]));

  return VIDEO_METADATA_FIELDS.map((field) => {
    const existingRow = rowsByField.get(field.name);
    if (existingRow) {
      return {
        ...existingRow,
        section: 'triver',
        display_field: field.label,
        read_only: false,
      };
    }

    const valuesByText = new Map();
    for (const track of tracks || []) {
      const value = readTrackField(track, field);
      if (!value) {
        continue;
      }
      const bucket = valuesByText.get(value) || { value, media_files: [] };
      bucket.media_files.push({
        id: track.primary_file,
        item_id: track.id,
        item_label: track.canonical_title || track.title || 'Video item',
      });
      valuesByText.set(value, bucket);
    }

    return {
      section: 'triver',
      field: field.name,
      display_field: field.label,
      read_only: false,
      values: Array.from(valuesByText.values()).sort((left, right) => left.value.localeCompare(right.value)),
    };
  });
}
