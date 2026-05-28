export default function AudioContentScaffold({ title, description = '', children, toolbar = null }) {
  return (
    <section className="content-stack">
      {toolbar ? (
        <header className="content-header">
          <div />
          <div className="audio-content-scaffold-toolbar">{toolbar}</div>
        </header>
      ) : null}
      <div className="audio-content-scaffold-body">{children}</div>
    </section>
  );
}
