import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  createTextTagAssignment,
  deleteTagAssignment,
  ensureCoreTagDefinitions,
  ensureTagValue,
  fetchTagAssignments,
  fetchTagValues,
} from '../../../api/tags';

function normalizeKey(value = '') {
  return String(value || '').trim().toLowerCase();
}

function groupAssignments(assignmentsByTarget = []) {
  const grouped = new Map();

  assignmentsByTarget.forEach(({ targetId, assignments = [] }) => {
    assignments.forEach((assignment) => {
      const definitionId = String(assignment?.tag_value?.definition || '');
      const valueText = String(assignment?.tag_value?.value_text || '').trim();
      const key = `${definitionId}:${normalizeKey(assignment?.tag_value?.normalized_key || valueText)}`;
      if (!grouped.has(key)) {
        grouped.set(key, {
          key,
          definitionId,
          valueText,
          assignmentIds: [],
          targetIds: new Set(),
        });
      }
      const bucket = grouped.get(key);
      bucket.assignmentIds.push(assignment.id);
      bucket.targetIds.add(targetId);
    });
  });

  return Array.from(grouped.values()).sort((left, right) => left.valueText.localeCompare(right.valueText, undefined, { sensitivity: 'base' }));
}

function filterTagValues(values = [], query = '') {
  const needle = String(query || '').trim().toLowerCase();
  if (!needle) {
    return values;
  }
  return values.filter((value) => String(value?.value_text || '').toLowerCase().includes(needle));
}

function nextDisplayOrder(values = []) {
  return values.reduce((maxOrder, value) => Math.max(maxOrder, Number(value?.display_order) || 0), -1) + 1;
}

function DefinitionSection({
  definition,
  query,
  onQueryChange,
  groupedAssignments,
  selectedCount,
  suggestions,
  onAssignValue,
  onRemoveGroup,
  busy,
}) {
  const title = definition?.label || 'Tag';

  return (
    <section className="track-tag-modal-section">
      <header className="track-tag-modal-section-header">
        <strong>{title}</strong>
      </header>

      <div className="track-tag-modal-input-row">
        <input
          type="text"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={`Write or filter ${title.toLowerCase()}s`}
        />
        <button
          type="button"
          disabled={busy || !String(query || '').trim()}
          onClick={() => onAssignValue(query)}
        >
          Assign
        </button>
      </div>

      <div className="track-tag-modal-chip-list">
        {groupedAssignments.length ? groupedAssignments.map((group) => (
          <button
            key={group.key}
            type="button"
            className="track-tag-modal-chip is-active"
            disabled={busy}
            onClick={() => onRemoveGroup(group)}
          >
            <span>{group.valueText}</span>
            <span>{group.targetIds.size}/{selectedCount}</span>
            <span aria-hidden="true">x</span>
          </button>
        )) : <span className="track-tag-modal-empty">No assigned tags</span>}
      </div>

      <div className="track-tag-modal-suggestions">
        {suggestions.length ? suggestions.map((value) => (
          <button
            key={value.id}
            type="button"
            className="track-tag-modal-chip"
            disabled={busy}
            onClick={() => onAssignValue(value.value_text)}
          >
            {value.value_text}
          </button>
        )) : <span className="track-tag-modal-empty">No matching existing tags</span>}
      </div>
    </section>
  );
}

export default function TrackTagAssignmentModal({
  scope = 'track',
  tracks = [],
  items = null,
  definitionKeys = null,
  onClose = () => {},
  onSaved = () => {},
}) {
  const targets = items || tracks;
  const [sections, setSections] = useState([]);
  const [valuesByDefinition, setValuesByDefinition] = useState({});
  const [assignmentsByDefinition, setAssignmentsByDefinition] = useState({});
  const [queriesByDefinition, setQueriesByDefinition] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const selectedCount = targets.length;

  const loadState = useCallback(async () => {
    if (!targets.length) {
      return;
    }
    setBusy(true);
    setError('');
    try {
      const allowedDefinitionKeys = Array.isArray(definitionKeys) && definitionKeys.length
        ? new Set(definitionKeys)
        : null;
      const ensuredSections = (await ensureCoreTagDefinitions(scope))
        .filter(({ definition }) => !allowedDefinitionKeys || allowedDefinitionKeys.has(definition.key));
      const nextValuesByDefinition = {};
      const nextAssignmentsByDefinition = {};

      await Promise.all(ensuredSections.map(async ({ definition }) => {
        const values = await fetchTagValues(definition.id);
        const perTargetAssignments = await Promise.all(targets.map(async (target) => ({
          targetId: target.id,
          assignments: await fetchTagAssignments(scope, target.id, definition.id),
        })));
        nextValuesByDefinition[definition.id] = values;
        nextAssignmentsByDefinition[definition.id] = groupAssignments(perTargetAssignments);
      }));

      setSections(ensuredSections);
      setValuesByDefinition(nextValuesByDefinition);
      setAssignmentsByDefinition(nextAssignmentsByDefinition);
    } catch (loadError) {
      setError(loadError.message || 'Unable to load tag assignment state.');
    } finally {
      setBusy(false);
    }
  }, [definitionKeys, scope, targets]);

  useEffect(() => {
    loadState();
  }, [loadState]);

  const suggestionsByDefinition = useMemo(() => {
    const next = {};
    sections.forEach(({ definition }) => {
      next[definition.id] = filterTagValues(valuesByDefinition[definition.id] || [], queriesByDefinition[definition.id] || '');
    });
    return next;
  }, [sections, valuesByDefinition, queriesByDefinition]);

  function setQuery(definitionId, value) {
    setQueriesByDefinition((current) => ({
      ...current,
      [definitionId]: value,
    }));
  }

  async function assignValue(definition, query) {
    const nextValue = String(query || '').trim();
    if (!definition?.id || !nextValue || !targets.length) {
      return;
    }
    const existingValues = valuesByDefinition[definition.id] || [];
    try {
      setBusy(true);
      setError('');
      const tagValue = await ensureTagValue({
        definitionId: definition.id,
        valueText: nextValue,
        existingValues,
        displayOrder: nextDisplayOrder(existingValues),
      });
      const normalizedKey = normalizeKey(tagValue.normalized_key || tagValue.value_text || nextValue);
      const existingGroup = (assignmentsByDefinition[definition.id] || [])
        .find((group) => group.key === `${definition.id}:${normalizedKey}`);
      const alreadyAssigned = existingGroup?.targetIds || new Set();
      const missingTargets = targets.filter((target) => !alreadyAssigned.has(target.id));
      await Promise.all(missingTargets.map((target) => createTextTagAssignment(scope, target.id, definition.id, nextValue)));
      setQuery(definition.id, '');
      onSaved();
      await loadState();
    } catch (saveError) {
      setError(saveError.message || 'Unable to assign tag.');
      setBusy(false);
    }
  }

  async function removeGroup(group) {
    try {
      setBusy(true);
      setError('');
      await Promise.all(group.assignmentIds.map((assignmentId) => deleteTagAssignment(scope, assignmentId)));
      onSaved();
      await loadState();
    } catch (removeError) {
      setError(removeError.message || 'Unable to remove tag assignment.');
      setBusy(false);
    }
  }

  return createPortal(
    <div className="track-tag-modal-backdrop" onClick={onClose} role="presentation">
      <div className="track-tag-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <header className="track-tag-modal-header">
          <div>
            <strong>Assign Tags</strong>
            <span>{selectedCount} selected item{selectedCount === 1 ? '' : 's'}</span>
          </div>
          <button type="button" className="track-tag-modal-close" onClick={onClose}>x</button>
        </header>

        {error ? <div className="track-tag-modal-error">{error}</div> : null}

        <div className="track-tag-modal-body">
          {sections.map(({ key, definition }) => (
            <DefinitionSection
              key={key}
              definition={definition}
              query={queriesByDefinition[definition.id] || ''}
              onQueryChange={(value) => setQuery(definition.id, value)}
              groupedAssignments={assignmentsByDefinition[definition.id] || []}
              selectedCount={selectedCount}
              suggestions={suggestionsByDefinition[definition.id] || []}
              busy={busy}
              onAssignValue={(value) => assignValue(definition, value)}
              onRemoveGroup={removeGroup}
            />
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}
