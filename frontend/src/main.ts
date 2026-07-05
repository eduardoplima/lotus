// LOTUS SPA — hash router + persistent chrome (header, gate pill, footer).

import "./app.css";
import { renderHome } from "./views/home";
import { renderInstruments } from "./views/instruments";
import { renderPortfolio } from "./views/portfolio";
import { renderStrategies } from "./views/strategies";
import { renderStrategyDetail } from "./views/strategy_detail";

const app = document.getElementById("app")!;

const NAV = [
  { label: "Home", route: "#/" },
  { label: "Portfolio", route: "#/dashboard/portfolio" },
  { label: "Instruments", route: "#/dashboard/instruments" },
  { label: "Strategies", route: "#/dashboard/strategies" },
];

function chrome(): { main: HTMLElement } {
  app.innerHTML = `
    <header class="lo-header">
      <a class="lo-brand" href="#/">
        <img src="/lotus-mark.svg" alt="" />
        <span>LOTUS</span>
      </a>
      <nav class="lo-nav" id="nav"></nav>
      <a class="lo-gate" href="#/dashboard/strategies/gate-replication" style="text-decoration:none;">
        <span class="lo-gate__dot"></span>GATE REPLICATION · RED
      </a>
    </header>
    <main id="main"></main>
    <footer class="lo-footer">
      <span>
        Research platform. Not investment advice; not an offer or solicitation.
        Figures are research output net of modeled costs; no performance is promised.
      </span>
      <span class="stamp" id="stamp">lotus-platform</span>
    </footer>`;

  const nav = app.querySelector<HTMLElement>("#nav")!;
  const hash = window.location.hash || "#/";
  for (const item of NAV) {
    const a = document.createElement("a");
    a.href = item.route;
    a.textContent = item.label;
    const active =
      item.route === "#/"
        ? hash === "#/" || hash === ""
        : hash.startsWith(item.route);
    a.classList.toggle("active", active);
    nav.appendChild(a);
  }
  const stamp = app.querySelector<HTMLElement>("#stamp")!;
  stamp.textContent = `lotus-platform · generated ${new Date().toISOString().slice(0, 19)} UTC`;
  return { main: app.querySelector<HTMLElement>("#main")! };
}

async function route(): Promise<void> {
  const { main } = chrome();
  const hash = window.location.hash || "#/";

  const detail = hash.match(/^#\/dashboard\/strategies\/(.+)$/);
  try {
    if (detail) await renderStrategyDetail(main, detail[1]);
    else if (hash.startsWith("#/dashboard/instruments")) await renderInstruments(main);
    else if (hash.startsWith("#/dashboard/strategies")) await renderStrategies(main);
    else if (hash.startsWith("#/dashboard/portfolio")) renderPortfolio(main);
    else await renderHome(main);
  } catch (err) {
    main.innerHTML = `<div class="lo-page lo-page--dash"><p>Failed to render: ${String(err)}</p></div>`;
  }
}

window.addEventListener("hashchange", () => void route());
void route();
