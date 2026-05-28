import AudioContentScaffold from '../AudioContentScaffold';
import { noticeEntries } from '../noticeData';
import { useT } from '../../../../i18n/I18nProvider';

export default function CreditsView() {
  const t = useT();

  return (
    <AudioContentScaffold title="Credits">
      <div className="notice-shell">
        <section className="credits-note credits-support">
          <strong>{t('Support trueRiver development')}</strong>
          <p>{t('Donations are optional and do not unlock features or priority support.')}</p>
          <div className="credits-support-actions">
            <a
              className="credits-support-link"
              href="https://buymeacoffee.com/tosomalemodo"
              target="_blank"
              rel="noreferrer noopener"
            >
              {t('Buy me a coffee')}
            </a>
            <a
              className="credits-support-link"
              href="https://discord.gg/ZZg8X6Npm"
              target="_blank"
              rel="noreferrer noopener"
            >
              {t('Join the Discord')}
            </a>
          </div>
        </section>
        <section className="notice-section">
          <div className="notice-table">
            <div className="notice-row notice-row-head">
              <span>Component</span>
              <span>License</span>
              <span>Notice</span>
              <span>Source</span>
            </div>
            {noticeEntries.map((entry) => (
              <div key={entry.name} className="notice-row">
                <strong>{entry.name}</strong>
                <span>{entry.license}</span>
                <span>{entry.copyright}</span>
                <a href={entry.source} target="_blank" rel="noreferrer">{entry.source.replace(/^https?:\/\//, '')}</a>
              </div>
            ))}
          </div>
        </section>
      </div>
    </AudioContentScaffold>
  );
}
