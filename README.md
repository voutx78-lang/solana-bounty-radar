# Solana Bounty Radar

Solana Bounty Radar is a zero-dependency Python CLI that finds public Web3 work opportunities and separates agent-ready jobs from listings that still require an account, social profile, wallet signature, or manual payment review.

**[Open the live bounty dashboard](https://voutx78-lang.github.io/solana-bounty-radar/)** — filter current opportunities by reward, provider, autonomy, and risk before opening a listing.

It currently scans:

- TaskBounty's funded agent-API queue, including headless Solana USDC payout support
- Superteam Earn's official agent-eligible listing feed
- Gibwork's public escrow marketplace feed and task health metadata
- Algora bounties announced by its official GitHub account
- MAIAR's repository-native bounties with automatic Solana payout after merge
- recently updated GitHub issues that mention a crypto-denominated bounty

The radar never connects to a wallet, signs a transaction, asks for a seed phrase, or spends funds.

## Quick start

Python 3.10 or newer is sufficient; there are no third-party dependencies.

```bash
python bounty_radar.py
python bounty_radar.py --autonomous-only
python bounty_radar.py --provider taskbounty,superteam,gibwork --min-reward 50
python bounty_radar.py --format json --output data/latest.json
```

Example classification:

```text
[AUTO] superteam | 500 USDC | Agent-compatible bounty
  submission mode: official_agent_api

[REVIEW] gibwork | 60 USDC | Development task
  risks: platform_account_required
```

`AUTO` means the listing advertises an official agent submission path. It does **not** guarantee acceptance or payment. `REVIEW` means a human must verify the rules and complete at least one platform or identity step.

## Safety model

The scanner deliberately treats unverified GitHub promises as risky. A bounty label or amount in an issue is not proof of escrow. Before doing work, verify:

1. the deadline is still open;
2. the sponsor and repository are authentic;
3. funds are escrowed or the sponsor has a credible payment history;
4. AI-generated work is allowed and disclosed;
5. the payout route supports your jurisdiction and wallet.

Never pay to unlock a bounty and never share a wallet seed phrase or private key.

## Automated snapshot

The scheduled GitHub workflow refreshes [`data/latest.json`](data/latest.json) and the live dashboard once a day. Provider failures are recorded instead of silently hiding incomplete scans.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Optional support

If this project saved you time, optional Solana tips can be sent to:

```text
DzXkCcqagBUBhf5xUpjVAUwVv6dhGM9GpLpjjQUqfxgx
```

Gibwork referral link: [browse Gibwork](https://app.gib.work?ref=DzXkCcqagBUBhf5xUpjVAUwVv6dhGM9GpLpjjQUqfxgx). This is disclosed because successful referrals may generate a small reward; referral status never affects rankings in the radar.

## Provenance

The first version was built by an AI coding agent under human direction. Sources are normalized and ranked independently; no other participant submissions are copied.

## License

MIT
