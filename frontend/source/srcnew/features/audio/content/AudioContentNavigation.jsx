import { useEffect, useMemo, useRef, useState } from 'react';

const CONTENT_JUMP_KEYS = ['#', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'];

function PreviousIcon() {
  return (
    <svg className="tree-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M11 7l-5 5l5 5" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M18 7l-5 5l5 5" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function NextIcon() {
  return (
    <svg className="tree-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M13 7l5 5l-5 5" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 7l5 5l-5 5" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg className="tree-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20 11a8 8 0 1 0 -2.34 5.66" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M20 4v7h-7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg className="tree-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M10.5 18a7.5 7.5 0 1 1 5.3 -2.2" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M16 16l5 5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function HighlightedText({ text, query }) {
  const source = String(text || '');
  const needle = String(query || '').trim();
  if (!needle) {
    return source;
  }

  const sourceLower = source.toLowerCase();
  const needleLower = needle.toLowerCase();
  const matchIndex = sourceLower.indexOf(needleLower);
  if (matchIndex < 0) {
    return source;
  }

  return (
    <>
      {source.slice(0, matchIndex)}
      <strong className="search-match">{source.slice(matchIndex, matchIndex + needle.length)}</strong>
      {source.slice(matchIndex + needle.length)}
    </>
  );
}

function AlphaJumpNav({ activeKey, onJump, onClear }) {
  const [isOpen, setIsOpen] = useState(false);
  const closeTimerRef = useRef(null);

  function cancelClose() {
    if (closeTimerRef.current) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    setIsOpen(true);
  }

  function closeLater() {
    if (closeTimerRef.current) {
      window.clearTimeout(closeTimerRef.current);
    }
    closeTimerRef.current = window.setTimeout(() => {
      setIsOpen(false);
      closeTimerRef.current = null;
    }, 520);
  }

  useEffect(() => () => {
    if (closeTimerRef.current) {
      window.clearTimeout(closeTimerRef.current);
    }
  }, []);

  return (
    <div
      className={`app-content-alpha-jump${isOpen ? ' is-open' : ''}`}
      aria-label="Quick alphabetical jump"
      onMouseEnter={cancelClose}
      onMouseLeave={closeLater}
      onFocus={cancelClose}
      onBlur={closeLater}
    >
      <span className="app-content-alpha-jump-trigger">A/Z</span>
      <div className="app-content-alpha-jump-strip">
        {activeKey ? (
          <button type="button" className="app-content-alpha-jump-clear" onClick={onClear} aria-label="Clear letter filter">
            ×
          </button>
        ) : null}
        {CONTENT_JUMP_KEYS.map((key) => (
          <button key={key} type="button" className={activeKey === key ? 'is-active' : ''} onClick={() => onJump(key)} aria-label={`Jump to ${key}`}>
            {key}
          </button>
        ))}
      </div>
    </div>
  );
}

function FilterMenu({
  label,
  value = 'all',
  options = [],
  disabled = false,
  multiple = false,
  onChange = () => {},
}) {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef(null);
  const values = useMemo(() => {
    const rawValues = multiple ? (Array.isArray(value) ? value : [value]) : [value];
    return rawValues.filter(Boolean).length ? rawValues.filter(Boolean) : ['all'];
  }, [multiple, value]);
  const selectedOptions = options.filter((option) => values.includes(option.value));
  const summary = selectedOptions.length
    ? selectedOptions.map((option) => option.label).join(', ')
    : (options[0]?.label || 'All');

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }
    function handlePointerDown(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    window.addEventListener('pointerdown', handlePointerDown);
    return () => window.removeEventListener('pointerdown', handlePointerDown);
  }, [isOpen]);

  function handleOptionClick(nextValue) {
    if (!multiple) {
      onChange(nextValue);
      setIsOpen(false);
      return;
    }

    if (nextValue === 'all') {
      onChange(['all']);
      return;
    }

    const currentValues = values.filter((item) => item !== 'all');
    const nextValues = currentValues.includes(nextValue)
      ? currentValues.filter((item) => item !== nextValue)
      : [...currentValues, nextValue];
    onChange(nextValues.length ? nextValues : ['all']);
  }

  return (
    <div ref={menuRef} className={`app-content-filter${disabled ? ' is-disabled' : ''}${isOpen ? ' is-open' : ''}`}>
      <span>{label}</span>
      <button
        type="button"
        className="app-content-filter-trigger"
        disabled={disabled}
        onClick={() => setIsOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
      >
        <span className="app-content-filter-summary">{summary}</span>
        <span className="app-content-filter-caret" aria-hidden="true">v</span>
      </button>
      {isOpen ? (
        <div className="app-content-filter-menu" role="menu">
          {options.map((option) => {
            const isSelected = values.includes(option.value);
            return (
              <button
                key={option.value}
                type="button"
                className={isSelected ? 'is-selected' : ''}
                role="menuitemcheckbox"
                aria-checked={isSelected}
                onClick={() => handleOptionClick(option.value)}
              >
                <span className="app-content-filter-mark" aria-hidden="true" />
                <span>{option.label}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function TagsSelectorMenu({
  values = null,
  options = [],
  disabled = false,
  onChange = () => {},
}) {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef(null);
  const optionValues = useMemo(() => options.map((option) => option.value).filter(Boolean), [options]);
  const hasExplicitSelection = Array.isArray(values);
  const selectedValues = useMemo(() => {
    const selectedSet = new Set(hasExplicitSelection ? values.filter(Boolean) : []);
    return optionValues.filter((value) => selectedSet.has(value));
  }, [hasExplicitSelection, optionValues, values]);
  const selectedSet = useMemo(() => new Set(selectedValues), [selectedValues]);
  const noFilter = !hasExplicitSelection;
  const allSelected = hasExplicitSelection && optionValues.length > 0 && selectedValues.length === optionValues.length;
  const noneSelected = hasExplicitSelection && selectedValues.length === 0;
  const summary = noFilter
    ? 'Any genre'
    : allSelected
    ? 'All genres'
    : noneSelected
      ? 'No genres'
      : `${selectedValues.length}/${optionValues.length} genres`;

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }
    function handlePointerDown(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    window.addEventListener('pointerdown', handlePointerDown);
    return () => window.removeEventListener('pointerdown', handlePointerDown);
  }, [isOpen]);

  function toggleTag(nextValue) {
    const nextSet = new Set(selectedValues);
    if (nextSet.has(nextValue)) {
      nextSet.delete(nextValue);
    } else {
      nextSet.add(nextValue);
    }
    onChange(optionValues.filter((value) => nextSet.has(value)));
  }

  return (
    <div ref={menuRef} className={`app-content-filter app-content-tag-selector${disabled ? ' is-disabled' : ''}${isOpen ? ' is-open' : ''}`}>
      <button
        type="button"
        className="app-content-filter-trigger"
        disabled={disabled}
        onClick={() => setIsOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
      >
        <span className="app-content-filter-summary">Genre: {summary}</span>
        <span className="app-content-filter-caret" aria-hidden="true">v</span>
      </button>
      {isOpen ? (
        <div className="app-content-filter-menu" role="menu">
          <button
            type="button"
            className={noFilter ? 'is-selected' : ''}
            role="menuitemcheckbox"
            aria-checked={noFilter}
            onClick={() => onChange(null)}
          >
            <span className="app-content-filter-mark" aria-hidden="true" />
            <span>Any genre</span>
          </button>
          <button
            type="button"
            className={allSelected ? 'is-selected' : ''}
            role="menuitemcheckbox"
            aria-checked={allSelected}
            onClick={() => onChange(optionValues)}
          >
            <span className="app-content-filter-mark" aria-hidden="true" />
            <span>All genres</span>
          </button>
          <button
            type="button"
            className={noneSelected ? 'is-selected' : ''}
            role="menuitemcheckbox"
            aria-checked={noneSelected}
            onClick={() => onChange([])}
          >
            <span className="app-content-filter-mark" aria-hidden="true" />
            <span>No genres</span>
          </button>
          {options.map((option) => {
            const isSelected = selectedSet.has(option.value);
            return (
              <button
                key={option.value}
                type="button"
                className={isSelected ? 'is-selected' : ''}
                role="menuitemcheckbox"
                aria-checked={isSelected}
                onClick={() => toggleTag(option.value)}
              >
                <span className="app-content-filter-mark" aria-hidden="true" />
                <span>{option.label}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export default function AudioContentNavigation({
  pathLabel,
  pagination,
  searchTerm,
  activeJumpKey,
  domainFilterLabel = '',
  domainFilterValue = '',
  domainFilterOptions = [],
  selectedTagKeys = [],
  tagOptions = [],
  onSearchTermChange,
  searchResults = [],
  onSelectSearchResult,
  onJumpToKey,
  onClearJumpKey,
  onDomainFilterChange = () => {},
  onTagChange = () => {},
  onRefreshCurrent,
  onRefreshGlobal,
}) {
  const totalPages = pagination ? Math.max(1, Math.ceil((pagination.totalCount || 0) / pagination.pageSize)) : 1;
  const hasPagination = Boolean(pagination && pagination.totalCount > pagination.pageSize);
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [isRefreshMenuOpen, setIsRefreshMenuOpen] = useState(false);
  const searchBlurTimerRef = useRef(null);
  const refreshMenuRef = useRef(null);
  const showSearchResults = isSearchFocused && searchResults.length > 0;
  const tagMenuOptions = useMemo(() => (
    tagOptions.map((option) => ({ value: option.value || option.key, label: option.label || option.value || option.key }))
  ), [tagOptions]);

  useEffect(() => () => {
    if (searchBlurTimerRef.current) {
      window.clearTimeout(searchBlurTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (!isRefreshMenuOpen) {
      return undefined;
    }
    function handlePointerDown(event) {
      if (refreshMenuRef.current && !refreshMenuRef.current.contains(event.target)) {
        setIsRefreshMenuOpen(false);
      }
    }
    window.addEventListener('pointerdown', handlePointerDown);
    return () => window.removeEventListener('pointerdown', handlePointerDown);
  }, [isRefreshMenuOpen]);

  function openSearchResults() {
    if (searchBlurTimerRef.current) {
      window.clearTimeout(searchBlurTimerRef.current);
      searchBlurTimerRef.current = null;
    }
    setIsSearchFocused(true);
  }

  function closeSearchResultsSoon() {
    if (searchBlurTimerRef.current) {
      window.clearTimeout(searchBlurTimerRef.current);
    }
    searchBlurTimerRef.current = window.setTimeout(() => {
      setIsSearchFocused(false);
      searchBlurTimerRef.current = null;
    }, 120);
  }

  function handleSelectSearchResult(result) {
    if (searchBlurTimerRef.current) {
      window.clearTimeout(searchBlurTimerRef.current);
      searchBlurTimerRef.current = null;
    }
    setIsSearchFocused(false);
    onSelectSearchResult(result);
  }

  return (
    <div className="app-content-nav">
      <div className="app-content-nav-paging" aria-label="Content pagination">
        <button
          type="button"
          className="app-content-nav-arrow"
          disabled={!hasPagination || pagination.page <= 1}
          onClick={() => pagination.onPageChange(Math.max(1, pagination.page - 1))}
          aria-label="Previous page"
        >
          <PreviousIcon />
        </button>
        <button
          type="button"
          className="app-content-nav-arrow"
          disabled={!hasPagination || pagination.page >= totalPages}
          onClick={() => pagination.onPageChange(Math.min(totalPages, pagination.page + 1))}
          aria-label="Next page"
        >
          <NextIcon />
        </button>
        <div className="app-content-page-status">
          {hasPagination ? `Page ${pagination.page} / ${totalPages}` : 'Page 1 / 1'}
        </div>
      </div>
      <div ref={refreshMenuRef} className={`app-content-nav-refresh-shell${isRefreshMenuOpen ? ' is-open' : ''}`}>
        <button
          type="button"
          className="app-content-nav-refresh"
          onClick={() => setIsRefreshMenuOpen((current) => !current)}
          aria-label="Refresh options"
          title="Refresh"
        >
          <RefreshIcon />
        </button>
        {isRefreshMenuOpen ? (
          <div className="app-content-nav-refresh-menu" role="menu">
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setIsRefreshMenuOpen(false);
                onRefreshCurrent();
              }}
            >
              Refresh current
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setIsRefreshMenuOpen(false);
                onRefreshGlobal();
              }}
            >
              Refresh global
            </button>
          </div>
        ) : null}
      </div>
      <AlphaJumpNav activeKey={activeJumpKey} onJump={onJumpToKey} onClear={onClearJumpKey} />
      <div className="app-content-filter-cluster">
        {domainFilterOptions.length ? (
          <FilterMenu
            label={domainFilterLabel || 'Filter'}
            value={domainFilterValue}
            options={domainFilterOptions}
            multiple
            onChange={onDomainFilterChange}
          />
        ) : null}
        <TagsSelectorMenu
          values={selectedTagKeys}
          options={tagMenuOptions}
          disabled={!tagMenuOptions.length}
          onChange={onTagChange}
        />
      </div>
      <div className="app-content-path" aria-label="Current location">
        {pathLabel}
      </div>
      <div className="app-content-search">
        <SearchIcon />
        <input
          type="search"
          value={searchTerm}
          onChange={(event) => onSearchTermChange(event.target.value)}
          onFocus={openSearchResults}
          onBlur={closeSearchResultsSoon}
          placeholder="Search"
          aria-label="Search current content"
        />
        {showSearchResults ? (
          <div
            className="app-content-search-results"
            onMouseEnter={openSearchResults}
            onMouseLeave={() => setIsSearchFocused(false)}
          >
            {searchResults.map((result) => (
              <button
                key={`${result.kind}-${result.id}`}
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => handleSelectSearchResult(result)}
              >
                <span>{result.label}</span>
                <small>
                  {result.kind}
                  {result.subtitle ? ` · ${result.subtitle}` : ''}
                  {result.matchedValue ? (
                    <>
                      {' · '}
                      {result.matchedField}: <HighlightedText text={result.matchedValue} query={searchTerm} />
                    </>
                  ) : null}
                </small>
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
