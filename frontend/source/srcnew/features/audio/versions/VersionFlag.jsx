function openVersionHandling() {
  window.history.pushState({}, '', '/audio/settings#version-handling');
  window.dispatchEvent(new PopStateEvent('popstate'));
  window.requestAnimationFrame(() => {
    document.getElementById('version-handling')?.scrollIntoView({ block: 'start' });
  });
}

export function versionCountForItem(item) {
  const explicitCount = Number(item?.version_count) || 0;
  if (explicitCount > 0) {
    return explicitCount;
  }
  return (item?.version_summary || []).reduce((maxCount, membership) => (
    Math.max(maxCount, Number(membership?.group_member_count) || 0)
  ), 0);
}

export default function VersionFlag({ item, className = '' }) {
  const count = versionCountForItem(item);
  if (count <= 1) {
    return null;
  }
  return (
    <button
      type="button"
      className={`version-flag${className ? ` ${className}` : ''}`}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        openVersionHandling();
      }}
      onContextMenu={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
    >
      {count} versions
    </button>
  );
}

export { openVersionHandling };
