import { useMemo } from 'react';
import { METADATA_MANIFEST_EXAMPLES } from './metadataManifest';

export default function MetadataManifestTable({ fields = [], loading = false }) {
  const manifestFieldNames = useMemo(() => Object.keys(METADATA_MANIFEST_EXAMPLES), []);
  const canonicalFields = useMemo(() => {
    const byName = new Map((fields || []).map((field) => [field.name, field]));
    return manifestFieldNames.map((fieldName) => (
      byName.get(fieldName) || {
        id: fieldName,
        name: fieldName,
        normalized_name: fieldName.toLowerCase(),
      }
    ));
  }, [fields, manifestFieldNames]);

  if (loading) {
    return <p className="metadata-model-note">Loading fields...</p>;
  }

  return (
    <>
      <div className="metadata-manifest-table" role="table" aria-label="trueRiver canonical metadata">
        <div className="metadata-manifest-row metadata-manifest-row-head" role="row">
          <span role="columnheader">Meta Name</span>
          <span role="columnheader">Explanation</span>
          <span role="columnheader">Example</span>
        </div>
        {canonicalFields.map((field) => (
          <div key={field.id || field.name} className="metadata-manifest-row" role="row">
            <strong role="cell">{field.name}</strong>
            <span role="cell">
              {METADATA_MANIFEST_EXAMPLES[field.name]?.usage || 'Canonical metadata field used by trueRiver.'}
              {field.name === 'Artist' ? (
                <>
                  {' '}
                  <a href="#metadata-separators-and-escapes" className="metadata-inline-link">
                    See Separators and Escapes.
                  </a>
                </>
              ) : null}
            </span>
            <code role="cell">{METADATA_MANIFEST_EXAMPLES[field.name]?.example || 'n/a'}</code>
          </div>
        ))}
      </div>
      <section id="metadata-separators-and-escapes" className="metadata-model-note metadata-model-note-detail">
        <strong className="metadata-note-title">Separators and Escapes</strong>
        <span>
          Artist splitting in catalog projection uses the canonical separators <strong className="metadata-inline-emphasis">&lt;&amp;&gt;</strong> <strong className="metadata-inline-emphasis">&lt;,&gt;</strong> <strong className="metadata-inline-emphasis">&lt;;&gt;</strong> and <strong className="metadata-inline-emphasis">&lt; - &gt;</strong>. The word and is not treated as a separator. Use <strong className="metadata-inline-emphasis">&lt;\&gt;</strong> to keep a separator literal inside a single artist name.
        </span>
      </section>
    </>
  );
}
