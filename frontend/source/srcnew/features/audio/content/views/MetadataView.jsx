import { useEffect, useState } from 'react';
import AudioContentScaffold from '../AudioContentScaffold';
import { fetchMetadataModel } from '../../../../api/metadata';
import MetadataSectionCard from '../../metadata/MetadataSectionCard';
import MetadataManifestTable from '../../metadata/MetadataManifestTable';
import MetadataRulesPanel from '../../metadata/MetadataRulesPanel';
import MetadataSearchGroupsPanel from '../../metadata/MetadataSearchGroupsPanel';

export default function MetadataView() {
  const [loading, setLoading] = useState(false);
  const [pageError, setPageError] = useState('');
  const [model, setModel] = useState({
    fields: [],
    rules: [],
    searchGroups: {},
  });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setPageError('');
    fetchMetadataModel()
      .then((payload) => {
        if (!cancelled) {
          setModel(payload);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setPageError(error.message || 'Metadata workspace unavailable');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AudioContentScaffold title="Metadata" description="">
      <div className="metadata-model-stack">
        <MetadataSectionCard
          title="trueRiver Canonical Metadata"
          description="Public manifest of canonical fields. This is the shared base for editors, metadata modals, and future mapping views."
        >
          {pageError ? <p className="metadata-model-note">{pageError}</p> : <MetadataManifestTable fields={model.fields} loading={loading} />}
        </MetadataSectionCard>

        <MetadataSectionCard
          title="Automatic Conversion Rules"
          description="Active rules that convert raw metadata into canonical trueRiver fields."
        >
          {pageError ? <p className="metadata-model-note">{pageError}</p> : <MetadataRulesPanel rules={model.rules} loading={loading} />}
        </MetadataSectionCard>

        <MetadataSectionCard
          title="Search Groups"
          description="Logical groups for future filters, contextual editors, and generalized metadata modals."
        >
          {pageError ? <p className="metadata-model-note">{pageError}</p> : <MetadataSearchGroupsPanel searchGroups={model.searchGroups} />}
        </MetadataSectionCard>
      </div>
    </AudioContentScaffold>
  );
}
