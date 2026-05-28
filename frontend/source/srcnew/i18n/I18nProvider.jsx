import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { DEFAULT_LANGUAGE, LANGUAGES, normalizeLanguage, translateText } from './translations';

const STORAGE_KEY = 'triver.interfaceLanguage';
const I18nContext = createContext(null);
const TRANSLATABLE_ATTRIBUTES = ['aria-label', 'title', 'placeholder', 'alt'];

function initialLanguage() {
  if (typeof window === 'undefined') {
    return DEFAULT_LANGUAGE;
  }
  return normalizeLanguage(window.localStorage.getItem(STORAGE_KEY) || window.navigator.language?.slice(0, 2));
}

function shouldSkipNode(node) {
  const parent = node.parentElement;
  if (!parent) {
    return true;
  }
  return Boolean(parent.closest('[data-i18n-skip], script, style, code, pre, textarea'));
}

function translateElementAttributes(element, language) {
  TRANSLATABLE_ATTRIBUTES.forEach((attribute) => {
    if (!element.hasAttribute(attribute)) {
      return;
    }
    const current = element.getAttribute(attribute);
    const next = translateText(current, language);
    if (next !== current) {
      element.setAttribute(attribute, next);
    }
  });
}

function translateDom(root, language) {
  if (!root || typeof document === 'undefined') {
    return;
  }

  if (root.nodeType === Node.ELEMENT_NODE) {
    translateElementAttributes(root, language);
  }

  const textWalker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (shouldSkipNode(node) || !String(node.nodeValue || '').trim()) {
        return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });

  const textNodes = [];
  while (textWalker.nextNode()) {
    textNodes.push(textWalker.currentNode);
  }

  textNodes.forEach((node) => {
    const current = node.nodeValue;
    const next = translateText(current, language);
    if (next !== current) {
      node.nodeValue = next;
    }
  });

  const elementWalker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, {
    acceptNode(node) {
      return node.closest('[data-i18n-skip]') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
    },
  });

  const elements = [];
  while (elementWalker.nextNode()) {
    elements.push(elementWalker.currentNode);
  }
  elements.forEach((element) => translateElementAttributes(element, language));
}

export function I18nProvider({ children }) {
  const [language, setLanguageState] = useState(initialLanguage);

  const setLanguage = useCallback((nextLanguage) => {
    const normalized = normalizeLanguage(nextLanguage);
    setLanguageState(normalized);
    window.localStorage.setItem(STORAGE_KEY, normalized);
  }, []);

  const t = useCallback((value) => translateText(value, language), [language]);

  useEffect(() => {
    document.documentElement.lang = language;
    translateDom(document.body, language);
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.type === 'characterData') {
          const node = mutation.target;
          if (!shouldSkipNode(node)) {
            const current = node.nodeValue;
            const next = translateText(current, language);
            if (next !== current) {
              node.nodeValue = next;
            }
          }
          return;
        }
        mutation.addedNodes.forEach((node) => translateDom(node, language));
        if (mutation.type === 'attributes') {
          translateElementAttributes(mutation.target, language);
        }
      });
    });
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: TRANSLATABLE_ATTRIBUTES,
      childList: true,
      characterData: true,
      subtree: true,
    });
    return () => observer.disconnect();
  }, [language]);

  const value = useMemo(() => ({
    language,
    languages: LANGUAGES,
    setLanguage,
    t,
  }), [language, setLanguage, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error('useI18n must be used inside I18nProvider');
  }
  return context;
}

export function useT() {
  return useI18n().t;
}

export function LanguageSelector({ id = 'triver-language-selector' }) {
  const { language, languages, setLanguage, t } = useI18n();
  return (
    <label className="language-selector" htmlFor={id}>
      <span>{t('Interface Language')}</span>
      <select id={id} value={language} onChange={(event) => setLanguage(event.target.value)}>
        {languages.map((item) => (
          <option key={item.code} value={item.code}>
            {item.nativeLabel}
          </option>
        ))}
      </select>
    </label>
  );
}
