import { useMemo } from 'react';
import { METADATA_MANIFEST_EXAMPLES } from './metadataManifest';

export default function MetadataRulesPanel({ rules = [], loading = false }) {
  const manifestFieldNames = useMemo(() => Object.keys(METADATA_MANIFEST_EXAMPLES), []);
  const rulesByFamily = useMemo(() => (
    (rules || [])
      .filter((rule) => rule.is_active !== false && manifestFieldNames.includes(rule.target_field_name || ''))
      .reduce((accumulator, rule) => {
        const key = (rule.source_family || 'any').toUpperCase();
        if (!accumulator[key]) {
          accumulator[key] = [];
        }
        accumulator[key].push(rule);
        return accumulator;
      }, {})
  ), [manifestFieldNames, rules]);

  if (loading) {
    return <p className="metadata-model-note">Loading rules...</p>;
  }

  return (
    <div className="metadata-model-rules">
      {Object.entries(rulesByFamily).map(([family, familyRules]) => (
        <section key={family} className="metadata-model-rules-group">
          <div className="metadata-model-rules-head">
            <h4>{family}</h4>
            <span>{familyRules.length}</span>
          </div>
          <div className="metadata-model-rules-list">
            {familyRules.map((rule) => (
              <div key={rule.id || `${rule.source_family}-${rule.source_name}-${rule.target_field_name || rule.target_field}`} className="metadata-model-rule-row">
                <code>{rule.source_name}</code>
                <span className="metadata-model-rule-arrow">→</span>
                <strong>{rule.target_field_name || rule.target_field_label || rule.target_field}</strong>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
