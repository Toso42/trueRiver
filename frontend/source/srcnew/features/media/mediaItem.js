export function getMediaKind(item = null) {
  const explicitKind = String(item?.media_kind || item?.kind || item?.type || '').toLowerCase();
  if (explicitKind === 'video' || explicitKind === 'audio') {
    return explicitKind;
  }

  const mimeType = String(item?.mime_type || item?.media_mime_type || '').toLowerCase();
  if (mimeType.startsWith('video/')) {
    return 'video';
  }
  if (mimeType.startsWith('audio/')) {
    return 'audio';
  }

  const format = String(item?.video_format || item?.audio_format || item?.format || item?.container || '').toLowerCase();
  if (['mp4', 'mkv', 'webm', 'mov', 'avi', 'mpeg', 'mpg'].includes(format)) {
    return 'video';
  }
  if (['mp3', 'flac', 'ogg', 'opus', 'aac', 'wav', 'm4a'].includes(format)) {
    return 'audio';
  }

  const hasVideoMarkers = Boolean(
    item?.poster_url
    || item?.video_stream_url
    || item?.video_codec
    || item?.width
    || item?.height
    || item?.fps
  );
  if (hasVideoMarkers) {
    return 'video';
  }

  return 'audio';
}

export function isVideoItem(item = null) {
  return getMediaKind(item) === 'video';
}
