const state = {
  opportunities: [],
  filtered: [],
};

const elements = {
  results: document.querySelector("#results"),
  resultCount: document.querySelector("#result-count"),
  search: document.querySelector("#search"),
  provider: document.querySelector("#provider"),
  minReward: document.querySelector("#min-reward"),
  autonomous: document.querySelector("#autonomous"),
  totalCount: document.querySelector("#total-count"),
  autonomousCount: document.querySelector("#autonomous-count"),
  rewardTotal: document.querySelector("#reward-total"),
  copyWallet: document.querySelector("#copy-wallet"),
};

const riskLabels = {
  platform_account_required: "Account required",
  payment_terms_require_review: "Review payout terms",
  escrow_unverified: "Escrow unverified",
  verified_account_required: "Verified account",
  verified_x_account_required: "Verified X account",
  social_account_likely_required: "Social profile likely",
  discord_membership_required: "Discord required",
  crowded_50_plus_pending: "50+ submissions",
  health_paused: "Paused",
  health_stale: "Stale",
  health_competitive: "Competitive",
  health_overcrowded: "Overcrowded",
  listing_quarantined: "Do not claim",
  mirror_listing: "Mirror listing",
  payment_profile_required: "Payment profile required",
  bounty_status_requires_review: "Confirm still funded",
  low_signal_repository: "Low-signal repository",
  forked_repository: "Forked repository",
  repository_metadata_unavailable: "Repository metadata unavailable",
};

function formatReward(item) {
  if (item.reward_amount === null || item.reward_amount === undefined) return "Reward unknown";
  const amount = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(item.reward_amount);
  return `${amount} ${item.reward_token || ""}`.trim();
}

function compactMoney(value) {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function flagMarkup(item) {
  if (item.autonomous) return '<span class="flag safe">Agent-ready submission</span>';
  const flags = (item.risk_flags || []).slice(0, 3);
  if (!flags.length) return '<span class="flag">Manual review</span>';
  return flags
    .map((flag) => `<span class="flag">${escapeHtml(riskLabels[flag] || flag.replaceAll("_", " "))}</span>`)
    .join("");
}

function render() {
  const query = elements.search.value.trim().toLowerCase();
  const provider = elements.provider.value;
  const minimum = Number(elements.minReward.value || 0);
  const autonomousOnly = elements.autonomous.checked;

  state.filtered = state.opportunities.filter((item) => {
    const searchable = `${item.title} ${item.summary || ""} ${item.sponsor || ""}`.toLowerCase();
    return (!query || searchable.includes(query))
      && (!provider || item.provider === provider)
      && (Number(item.reward_amount || 0) >= minimum)
      && (!autonomousOnly || item.autonomous);
  });

  elements.resultCount.textContent = `${state.filtered.length} ${state.filtered.length === 1 ? "opportunity" : "opportunities"}`;

  if (!state.filtered.length) {
    elements.results.innerHTML = '<div class="empty">No opportunities match these filters. Try lowering the minimum reward or showing review-required work.</div>';
    return;
  }

  elements.results.innerHTML = state.filtered.map((item) => `
    <article class="card">
      <div>
        <div class="reward">${escapeHtml(formatReward(item))}</div>
        <div class="provider">${escapeHtml(item.provider)}</div>
      </div>
      <div>
        <h2>${escapeHtml(item.title)}</h2>
        ${item.summary ? `<p class="summary">${escapeHtml(item.summary)}</p>` : ""}
        <div class="flags">${flagMarkup(item)}</div>
      </div>
      <a class="open-link" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer nofollow">Inspect ↗</a>
    </article>
  `).join("");
}

function populateProviders(items) {
  const providers = [...new Set(items.map((item) => item.provider))].sort();
  elements.provider.insertAdjacentHTML(
    "beforeend",
    providers.map((provider) => `<option value="${escapeHtml(provider)}">${escapeHtml(provider)}</option>`).join(""),
  );
}

async function loadData() {
  try {
    const response = await fetch("data/latest.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.opportunities = Array.isArray(payload.opportunities) ? payload.opportunities : [];
    populateProviders(state.opportunities);

    const autonomousCount = state.opportunities.filter((item) => item.autonomous).length;
    const dollarTokens = new Set(["USD", "USDC", "USDT", "USDG"]);
    const rewardTotal = state.opportunities.reduce(
      (sum, item) => sum + (dollarTokens.has(item.reward_token) ? Number(item.reward_amount || 0) : 0),
      0,
    );
    elements.totalCount.textContent = state.opportunities.length.toLocaleString("en-US");
    elements.autonomousCount.textContent = autonomousCount.toLocaleString("en-US");
    elements.rewardTotal.textContent = `$${compactMoney(rewardTotal)}`;

    if (Array.isArray(payload.provider_errors) && payload.provider_errors.length) {
      elements.results.insertAdjacentHTML("beforebegin", '<div class="error">One or more providers could not be refreshed. Visible results may be incomplete.</div>');
    }
    render();
  } catch (error) {
    elements.resultCount.textContent = "Unavailable";
    elements.results.innerHTML = `<div class="error">Could not load the latest snapshot. The CLI remains available on GitHub. (${escapeHtml(error.message)})</div>`;
  }
}

[elements.search, elements.provider, elements.minReward, elements.autonomous].forEach((element) => {
  element.addEventListener("input", render);
  element.addEventListener("change", render);
});

elements.copyWallet.addEventListener("click", async () => {
  const wallet = elements.copyWallet.dataset.wallet;
  try {
    await navigator.clipboard.writeText(wallet);
    elements.copyWallet.textContent = "Copied";
    window.setTimeout(() => { elements.copyWallet.textContent = "Copy"; }, 1600);
  } catch {
    elements.copyWallet.textContent = "Select address";
  }
});

loadData();
