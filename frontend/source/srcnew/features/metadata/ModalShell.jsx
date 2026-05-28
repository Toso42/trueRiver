export default function ModalShell({ title, children, footer = null }) {
  return (
    <section className="placeholder-panel metadata-modal-shell">
      <span className="placeholder-kicker">Modal Shell</span>
      <h2>{title}</h2>
      <div className="metadata-modal-shell-body">{children}</div>
      {footer ? <div className="metadata-modal-shell-footer">{footer}</div> : null}
    </section>
  );
}
