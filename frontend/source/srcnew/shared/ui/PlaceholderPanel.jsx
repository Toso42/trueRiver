export default function PlaceholderPanel({ title, body, kicker = 'View' }) {
  return (
    <section className="placeholder-panel">
      <span className="placeholder-kicker">{kicker}</span>
      <h2>{title}</h2>
      <p>{body}</p>
    </section>
  );
}
