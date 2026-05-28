export function aggregateTrackMetadata(mediaFiles, tracksByMediaFileId = new Map()) {
  const rowsByField = new Map();

  for (const mediaFile of mediaFiles || []) {
    const relatedTrack = tracksByMediaFileId.get(mediaFile.id) || null;
    const mediaPayload = {
      id: mediaFile.id,
      filename: mediaFile.filename,
      display_path: mediaFile.display_path,
      item_id: relatedTrack?.id || '',
      item_label: relatedTrack?.canonical_title || relatedTrack?.title || mediaFile.filename,
    };

    const rowGroups = [
      ['triver', mediaFile.editable_metadata?.triver || []],
      ['source', mediaFile.editable_metadata?.source || mediaFile.editable_metadata?.raw || []],
    ];

    for (const [fallbackSection, groupedRows] of rowGroups) {
      for (const row of groupedRows) {
      const fieldRow = rowsByField.get(row.field) || {
        section: row.section || fallbackSection,
        field: row.field,
        display_field: row.display_field || row.field,
        read_only: Boolean(row.read_only),
        source_family: row.source_family || '',
        source_name: row.source_name || '',
        source_label: row.source_label || '',
        values: new Map(),
      };

      for (const value of row.values || []) {
        const valueText = value.value || '';
        const bucket = fieldRow.values.get(valueText) || { value: valueText, media_files: [] };
        bucket.media_files.push(mediaPayload);
        fieldRow.values.set(valueText, bucket);
      }

      if (!row.values?.length) {
        fieldRow.values.set('', fieldRow.values.get('') || { value: '', media_files: [] });
      }

      rowsByField.set(row.field, fieldRow);
    }
    }
  }

  return Array.from(rowsByField.values())
    .map((row) => ({
      field: row.field,
      section: row.section || 'source',
      display_field: row.display_field || row.field,
      read_only: row.read_only,
      source_family: row.source_family || '',
      source_name: row.source_name || '',
      source_label: row.source_label || '',
      values: Array.from(row.values.values()).sort((left, right) => left.value.localeCompare(right.value)),
    }))
    .sort((left, right) => left.field.localeCompare(right.field));
}

export function buildArtistDiscography(artist, tracks) {
  const albumsMap = new Map();
  const featuresMap = new Map();

  (tracks || []).forEach((track) => {
    if (!track?.album) {
      return;
    }

    const matchingCredit = (track.artist_summary || []).find((credit) => credit.artist_id === artist.id);
    if (!matchingCredit) {
      return;
    }

    const roleLabel = String(matchingCredit.role || '').toLowerCase();
    const isPrimaryArtist = Boolean(matchingCredit.is_primary) || roleLabel === 'artist';
    const targetMap = isPrimaryArtist ? albumsMap : featuresMap;
    const relatedArtists = [];

    (track.artist_summary || []).forEach((credit) => {
      if (!credit?.artist_id || !credit?.name) {
        return;
      }
      if (!relatedArtists.some((entry) => entry.id === credit.artist_id)) {
        relatedArtists.push({
          id: credit.artist_id,
          name: credit.name,
        });
      }
    });

    const existing = targetMap.get(track.album) || {
      id: track.album,
      title: track.album_title || 'Unknown Album',
      cover_url: track.cover_url || '',
      release_year: track.release_year || '',
      artists: [],
      trackIds: new Set(),
      roleSet: new Set(),
    };

    existing.cover_url = existing.cover_url || track.cover_url || '';
    existing.release_year = existing.release_year || track.release_year || '';
    relatedArtists.forEach((relatedArtist) => {
      if (!existing.artists.some((entry) => entry.id === relatedArtist.id)) {
        existing.artists.push(relatedArtist);
      }
    });
    existing.trackIds.add(track.id);
    if (matchingCredit.role) {
      existing.roleSet.add(matchingCredit.role);
    }
    targetMap.set(track.album, existing);
  });

  const normalize = (map) => Array.from(map.values())
    .map((entry) => ({
      id: entry.id,
      title: entry.title,
      cover_url: entry.cover_url,
      release_year: entry.release_year,
      artists: entry.artists,
      track_count: entry.trackIds.size,
      roles: Array.from(entry.roleSet),
    }))
    .sort((left, right) => {
      const leftYear = Number(left.release_year || 0);
      const rightYear = Number(right.release_year || 0);
      if (leftYear !== rightYear) {
        return rightYear - leftYear;
      }
      return left.title.localeCompare(right.title);
    });

  return {
    albums: normalize(albumsMap),
    features: normalize(featuresMap),
  };
}
