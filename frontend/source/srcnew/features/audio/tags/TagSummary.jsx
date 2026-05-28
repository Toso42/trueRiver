export default function TagSummary({ tags = [], className = '', onTagClick = null }) {
  const visibleTags = (tags || [])
    .filter((tag) => String(tag?.value || '').trim())
    .slice()
    .sort((left, right) => {
      const leftOrder = Number(left.display_order) || 0;
      const rightOrder = Number(right.display_order) || 0;
      if (leftOrder !== rightOrder) {
        return leftOrder - rightOrder;
      }
      return String(left.value || '').localeCompare(String(right.value || ''), undefined, { sensitivity: 'base' });
    })
    .slice(0, 4);

  if (!visibleTags.length) {
    return null;
  }

  return (
    <div className={`content-tag-row${className ? ` ${className}` : ''}`}>
      {visibleTags.map((tag) => {
        const tagKey = `${tag.definition}:${tag.normalized_key || tag.value_id || tag.value}`;
        if (!onTagClick) {
          return (
            <span key={tagKey} className="content-tag-chip">
              {tag.value}
            </span>
          );
        }
        return (
          <button
            key={tagKey}
            type="button"
            className="content-tag-chip"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onTagClick(tag);
            }}
            onContextMenu={(event) => {
              event.preventDefault();
              event.stopPropagation();
            }}
          >
            {tag.value}
          </button>
        );
      })}
    </div>
  );
}
