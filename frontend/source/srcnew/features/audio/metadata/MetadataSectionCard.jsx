export default function MetadataSectionCard({
  kicker = 'Workspace',
  title = '',
  description = '',
  children = null,
}) {
  return (
    <section className="settings-card">
      <div className="settings-card-head">
        <div>
          <p className="panel-kicker">{kicker}</p>
          <h3>{title}</h3>
        </div>
        {description ? <p className="settings-card-copy">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}
