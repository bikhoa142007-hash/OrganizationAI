interface PlaceholderPageProps {
  screen: string
  purpose: string
}

export function PlaceholderPage({ screen, purpose }: PlaceholderPageProps) {
  return (
    <section className="placeholder" aria-labelledby="screen-title">
      <span className="screen-number">Skeleton route</span>
      <h2 id="screen-title">{screen}</h2>
      <p>{purpose}</p>
      <p className="muted">Mock Data và UI behavior sẽ được bổ sung ở bước tiếp theo.</p>
    </section>
  )
}
