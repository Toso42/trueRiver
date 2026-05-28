export default function MetadataSearchGroupsPanel({ searchGroups = {} }) {
  return (
    <div className="metadata-model-search-groups">
      {Object.entries(searchGroups || {}).map(([groupKey, members]) => (
        <article key={groupKey} className="metadata-model-search-group">
          <div className="metadata-model-search-group-head">
            <strong>{groupKey}</strong>
            <span>{members.length}</span>
          </div>
          <div className="metadata-model-search-group-tags">
            {members.map((member) => <span key={member}>{member}</span>)}
          </div>
        </article>
      ))}
    </div>
  );
}
