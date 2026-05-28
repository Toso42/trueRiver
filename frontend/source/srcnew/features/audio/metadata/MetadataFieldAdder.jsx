import { useMemo, useState } from 'react';
import { METADATA_MANIFEST_EXAMPLES } from './metadataManifest';

export default function MetadataFieldAdder({
  label = 'Add field',
  fields = [],
  existingFields = [],
  onAddField = () => {},
}) {
  const [selectedField, setSelectedField] = useState('');

  const availableFields = useMemo(() => {
    const canonicalNames = Object.keys(METADATA_MANIFEST_EXAMPLES);
    const fieldByName = new Map((fields || []).map((field) => [field.name, field]));
    const existing = new Set((existingFields || []).map((field) => String(field || '').toLowerCase()));
    return canonicalNames
      .map((fieldName) => (
        fieldByName.get(fieldName) || {
          id: fieldName,
          name: fieldName,
          display_name: fieldName,
        }
      ))
      .filter((field) => !existing.has(String(field.name || '').toLowerCase()));
  }, [existingFields, fields]);

  if (!availableFields.length) {
    return null;
  }

  return (
    <div className="metadata-field-adder">
      <select
        value={selectedField}
        onChange={(event) => setSelectedField(event.target.value)}
        aria-label={label}
      >
        <option value="">{label}</option>
        {availableFields.map((field) => (
          <option key={field.id || field.name} value={field.name}>
            {field.display_name || field.name}
          </option>
        ))}
      </select>
      <button
        type="button"
        className="metadata-inline-button"
        onClick={() => {
          const nextField = availableFields.find((field) => field.name === selectedField);
          if (!nextField) {
            return;
          }
          onAddField(nextField);
          setSelectedField('');
        }}
        disabled={!selectedField}
      >
        Add Field
      </button>
    </div>
  );
}
