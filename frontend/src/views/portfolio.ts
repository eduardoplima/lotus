// Portfolio — honest empty state. Lotus does not route orders (out of scope by
// design); there is no live NAV or positions feed to show. Nothing is mocked.

export function renderPortfolio(root: HTMLElement): void {
  root.innerHTML = `
    <div class="lo-page lo-page--dash">
      <div class="lo-label">Dashboards / Portfolio</div>
      <h2 class="lo-h2">Portfolio</h2>
      <div class="lo-panel lo-empty">
        <div class="inner">
          <p><strong>No live positions.</strong></p>
          <p>Lotus is a research and data platform — it deliberately does not route orders,
          so there is no NAV curve, position table, or exposure to display. When (and if)
          execution exists elsewhere, this view reads from it; until then, an empty panel
          is the honest state. Nothing here is mocked.</p>
        </div>
      </div>
    </div>`;
}
