import { useEffect, useMemo, useState } from 'react';
import ContextMenu from '../../../shared/ui/ContextMenu';
import { fetchMetadataValueSuggestions } from '../../../api/metadata';

export default function MetadataEditableField({
  row,
  disabled = false,
  onApply = () => Promise.resolve(),
}) {
  const normalizedValues = useMemo(() => (
    (row.values || []).map((entry) => ({
      value: typeof entry === 'string' ? entry : entry.value || '',
      media_files: typeof entry === 'string' ? [] : entry.media_files || [],
    }))
  ), [row.values]);
  const [isEditing, setIsEditing] = useState(false);
  const [draftValues, setDraftValues] = useState([]);
  const [newValue, setNewValue] = useState('');
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState('');
  const [contextMenu, setContextMenu] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);

  useEffect(() => {
    if (!isEditing) {
      setDraftValues([]);
      setNewValue('');
      setError('');
      setSuggestions([]);
    }
  }, [isEditing]);

  useEffect(() => {
    let cancelled = false;
    const query = newValue.trim();
    if (!isEditing || !query || row.read_only) {
      setSuggestions([]);
      setSuggestionsLoading(false);
      return undefined;
    }
    setSuggestionsLoading(true);
    const timeoutId = window.setTimeout(() => {
      fetchMetadataValueSuggestions(row.field, query, 8)
        .then((items) => {
          if (!cancelled) {
            const existing = new Set(draftValues.map((value) => value.toLowerCase()));
            setSuggestions(items.filter((item) => !existing.has(String(item.value || '').toLowerCase())));
          }
        })
        .catch(() => {
          if (!cancelled) {
            setSuggestions([]);
          }
        })
        .finally(() => {
          if (!cancelled) {
            setSuggestionsLoading(false);
          }
        });
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [draftValues, isEditing, newValue, row.field, row.read_only]);

  function beginEdit() {
    setDraftValues(normalizedValues.map((entry) => entry.value).filter(Boolean));
    setNewValue('');
    setError('');
    setIsEditing(true);
  }

  function addDraftValue() {
    const cleanValue = newValue.trim();
    if (!cleanValue) {
      return;
    }
    setDraftValues((current) => (
      current.some((value) => value.toLowerCase() === cleanValue.toLowerCase())
        ? current
        : [...current, cleanValue]
    ));
    setNewValue('');
    setSuggestions([]);
  }

  function addSuggestedValue(value) {
    const cleanValue = String(value || '').trim();
    if (!cleanValue) {
      return;
    }
    setDraftValues((current) => (
      current.some((entry) => entry.toLowerCase() === cleanValue.toLowerCase())
        ? current
        : [...current, cleanValue]
    ));
    setNewValue('');
    setSuggestions([]);
  }

  async function applyDraftValues() {
    setIsApplying(true);
    setError('');
    try {
      await onApply(draftValues);
      setIsEditing(false);
    } catch (applyError) {
      setError(applyError.message || 'Apply failed');
    } finally {
      setIsApplying(false);
    }
  }

  async function appendValue(nextValue) {
    const cleanValue = String(nextValue || '').trim();
    if (!cleanValue) {
      return;
    }
    const baseValues = isEditing
      ? draftValues
      : normalizedValues.map((entry) => entry.value).filter(Boolean);
    const mergedValues = baseValues.some((value) => value.toLowerCase() === cleanValue.toLowerCase())
      ? baseValues
      : [...baseValues, cleanValue];
    if (isEditing) {
      setDraftValues(mergedValues);
      return;
    }
    setIsApplying(true);
    setError('');
    try {
      await onApply(mergedValues);
    } catch (applyError) {
      setError(applyError.message || 'Paste failed');
    } finally {
      setIsApplying(false);
    }
  }

  const visibleValues = isEditing
    ? draftValues.map((value) => ({ value, media_files: [] }))
    : normalizedValues;

  return (
    <div className="metadata-field-editor" data-field-key={row.field}>
      <div className="metadata-field-head">
        <dt title={row.display_field || row.field}>
          {row.source_family || row.source_name || row.source_label ? (
            <span className="metadata-source-label">
              {row.source_family ? <span className="metadata-source-kind">{String(row.source_family).toUpperCase()} frame</span> : null}
              {row.source_name ? <span className="metadata-source-frame">{row.source_name}</span> : null}
              {row.source_label ? <span className="metadata-source-meaning">{row.source_label}</span> : null}
            </span>
          ) : (
            row.display_field || row.field
          )}
        </dt>
        <div className="metadata-field-actions">
          {row.read_only ? null : isEditing ? (
            <>
              <button type="button" className="metadata-inline-button" onClick={applyDraftValues} disabled={isApplying || disabled}>
                {isApplying ? 'Applying' : 'Apply'}
              </button>
              <button
                type="button"
                className="metadata-inline-button is-muted"
                onClick={() => setDraftValues([])}
                disabled={isApplying}
              >
                Clear
              </button>
              <button type="button" className="metadata-inline-button is-muted" onClick={() => setIsEditing(false)} disabled={isApplying}>
                Cancel
              </button>
            </>
          ) : (
            <>
              <button type="button" className="metadata-inline-button" onClick={beginEdit} disabled={disabled}>
                Edit
              </button>
              {visibleValues.length ? (
                <button
                  type="button"
                  className="metadata-inline-button is-muted"
                  onClick={async () => {
                    setIsApplying(true);
                    setError('');
                    try {
                      await onApply([]);
                    } catch (applyError) {
                      setError(applyError.message || 'Clear failed');
                    } finally {
                      setIsApplying(false);
                    }
                  }}
                  disabled={disabled || isApplying}
                >
                  Clear
                </button>
              ) : null}
            </>
          )}
        </div>
      </div>
      <dd
        onDragOver={(event) => {
          if (!row.read_only && !disabled) {
            event.preventDefault();
          }
        }}
        onDrop={(event) => {
          if (row.read_only || disabled) {
            return;
          }
          event.preventDefault();
          const droppedValue = event.dataTransfer.getData('text/triver-metadata-value')
            || event.dataTransfer.getData('text/plain');
          appendValue(droppedValue);
        }}
        onContextMenu={(event) => {
          event.preventDefault();
          setContextMenu({
            x: event.clientX,
            y: event.clientY,
            value: '',
          });
        }}
      >
        <div className="metadata-value-tags">
          {visibleValues.length ? visibleValues.map((entry, index) => (
            <span
              key={`${row.field}:${entry.value}:${index}`}
              className="metadata-value-tag"
              draggable={Boolean(entry.value)}
              onDragStart={(event) => {
                event.dataTransfer.effectAllowed = 'copy';
                event.dataTransfer.setData('text/triver-metadata-value', entry.value || '');
                event.dataTransfer.setData('text/plain', entry.value || '');
              }}
            >
              <span
                className="metadata-value-label"
                onContextMenu={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  setContextMenu({
                    x: event.clientX,
                    y: event.clientY,
                    value: entry.value || '',
                  });
                }}
              >
                {entry.value || <span className="metadata-empty-value">empty</span>}
              </span>
              {isEditing ? (
                <button
                  type="button"
                  className="metadata-remove-value"
                  onClick={() => setDraftValues((current) => current.filter((_, valueIndex) => valueIndex !== index))}
                  aria-label={`Remove ${entry.value}`}
                >
                  ×
                </button>
              ) : null}
            </span>
          )) : (
            <span className="metadata-empty-value">empty</span>
          )}
        </div>
        {isEditing ? (
          <div className="metadata-value-add">
            <input
              type="text"
              value={newValue}
              placeholder="Add value"
              onChange={(event) => setNewValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  addDraftValue();
                }
              }}
            />
            <button type="button" className="metadata-inline-button" onClick={addDraftValue}>
              Add
            </button>
            {suggestions.length || suggestionsLoading ? (
              <div className="metadata-suggestion-list">
                {suggestionsLoading ? <span className="metadata-suggestion-empty">Loading</span> : null}
                {suggestions.map((suggestion) => (
                  <button
                    key={`${suggestion.source}:${suggestion.value}`}
                    type="button"
                    className="metadata-suggestion-chip"
                    onClick={() => addSuggestedValue(suggestion.value)}
                  >
                    <span>{suggestion.value}</span>
                    <small>{suggestion.source}</small>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        {error ? <p className="metadata-error">{error}</p> : null}
      </dd>
      {contextMenu ? (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          items={[
            {
              key: 'copy-value',
              label: 'Copy',
              onSelect: async () => {
                const selectedText = window.getSelection?.()?.toString?.().trim?.() || '';
                const textToCopy = selectedText || contextMenu.value || '';
                if (textToCopy && navigator.clipboard?.writeText) {
                  await navigator.clipboard.writeText(textToCopy);
                }
              },
            },
            {
              key: 'paste-value',
              label: 'Paste',
              onSelect: async () => {
                if (!navigator.clipboard?.readText || row.read_only || disabled) {
                  return;
                }
                const pastedText = await navigator.clipboard.readText();
                await appendValue(pastedText);
              },
            },
          ]}
        />
      ) : null}
    </div>
  );
}
