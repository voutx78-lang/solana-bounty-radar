#!/usr/bin/env python3
"""Find public Solana/Web3 work opportunities without touching a wallet."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


WALLET = "DzXkCcqagBUBhf5xUpjVAUwVv6dhGM9GpLpjjQUqfxgx"
USER_AGENT = "solana-bounty-radar/1.0 (+https://github.com/voutx78-lang/solana-bounty-radar)"


@dataclass(slots=True)
class Opportunity:
    provider: str
    id: str
    title: str
    url: str
    reward_amount: float | None = None
    reward_token: str | None = None
    deadline: str | None = None
    sponsor: str | None = None
    category: str | None = None
    status: str | None = None
    submission_mode: str = "unknown"
    autonomous: bool = False
    risk_flags: list[str] = field(default_factory=list)
    summary: str | None = None


class RadarError(RuntimeError):
    """A provider returned an unusable response."""


def fetch_json(url: str, *, headers: dict[str, str] | None = None, timeout: int = 25) -> Any:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        **(headers or {}),
    }
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_live(deadline: str | None, *, now: datetime | None = None) -> bool:
    parsed = parse_datetime(deadline)
    if parsed is None:
        return True
    reference = now or datetime.now(timezone.utc)
    return parsed >= reference


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def normalize_superteam(item: dict[str, Any]) -> Opportunity:
    reward = item.get("rewardAmount")
    sponsor = item.get("sponsor") or {}
    return Opportunity(
        provider="superteam",
        id=str(item.get("id", "")),
        title=str(item.get("title", "Untitled opportunity")),
        url=f"https://superteam.fun/earn/listing/{item.get('slug', '')}/",
        reward_amount=float(reward) if isinstance(reward, (int, float)) else None,
        reward_token=item.get("token"),
        deadline=item.get("deadline"),
        sponsor=sponsor.get("name") if isinstance(sponsor, dict) else str(sponsor),
        category=item.get("type"),
        status=item.get("status"),
        submission_mode="official_agent_api",
        autonomous=True,
        risk_flags=[],
        summary="Agent-eligible listing from a verified Superteam sponsor.",
    )


def fetch_superteam() -> list[Opportunity]:
    params = {
        "context": "agents",
        "status": "open",
        "tab": "all",
        "category": "All",
        "sortBy": "Date",
        "order": "asc",
    }
    data = fetch_json(f"https://superteam.fun/api/listings?{urlencode(params)}")
    if not isinstance(data, list):
        raise RadarError("Superteam returned a non-list response")
    return [normalize_superteam(item) for item in data if is_live(item.get("deadline"))]


def normalize_taskbounty(item: dict[str, Any]) -> Opportunity:
    bounty_cents = item.get("bounty_cents")
    repository_url = str(item.get("github_repo_url") or "")
    sponsor = repository_url.rstrip("/").rsplit("/", 2)[-2] if repository_url else None
    slug = str(item.get("slug") or item.get("id") or "")
    return Opportunity(
        provider="taskbounty",
        id=str(item.get("id", "")),
        title=str(item.get("title", "Untitled opportunity")),
        url=f"https://www.task-bounty.com/task/{slug}",
        reward_amount=float(bounty_cents) / 100 if isinstance(bounty_cents, (int, float)) else None,
        reward_token="USD",
        deadline=item.get("submission_deadline"),
        sponsor=sponsor,
        category=item.get("category"),
        status=item.get("status"),
        submission_mode="official_agent_api_github_pr",
        autonomous=True,
        risk_flags=[
            "api_key_required",
            "first_verified_pr_wins",
            "platform_account_required",
            "platform_fee_20_percent",
        ],
        summary=(
            "Funded agent-API bounty with headless Solana USDC payout. "
            "The displayed amount is gross; the solver receives 80%."
        ),
    )


def fetch_taskbounty() -> list[Opportunity]:
    params = {"state": "open", "limit": 100}
    payload = fetch_json(f"https://www.task-bounty.com/api/v1/tasks?{urlencode(params)}")
    if not isinstance(payload, dict):
        raise RadarError("TaskBounty returned a non-object response")
    items = payload.get("data", payload.get("tasks"))
    if not isinstance(items, list):
        raise RadarError("TaskBounty returned an invalid task list")
    return [
        normalize_taskbounty(item)
        for item in items
        if str(item.get("status", "")).upper() == "OPEN"
        and str(item.get("funding_status", "")).upper() == "FUNDED"
        and (item.get("bounty_cents") or 0) > 0
        and is_live(item.get("submission_deadline"))
    ]


def gibwork_risk_flags(item: dict[str, Any], detail: dict[str, Any] | None) -> list[str]:
    source = detail or item
    flags = ["platform_account_required"]
    health = source.get("health") or {}
    if health.get("status") and health.get("status") != "healthy":
        flags.append(f"health_{health['status']}")
    if source.get("allowOnlyVerifiedSubmissions"):
        flags.append("verified_account_required")
    if source.get("allowOnlyVerifiedTwitterAccountSubmissions") or source.get("isTwitterTask"):
        flags.append("verified_x_account_required")
    if source.get("allowOnlyDiscordGuildSubmissions"):
        flags.append("discord_membership_required")
    pending = source.get("taskSubmissionsPendingCount")
    if isinstance(pending, int) and pending >= 50:
        flags.append("crowded_50_plus_pending")
    tags = {str(tag).lower() for tag in item.get("tags") or []}
    if "social media" in tags:
        flags.append("social_account_likely_required")
    return sorted(set(flags))


def normalize_gibwork(item: dict[str, Any], detail: dict[str, Any] | None = None) -> Opportunity:
    source = detail or item
    asset = source.get("asset") or item.get("asset") or {}
    amount = item.get("remainingAmount")
    if not isinstance(amount, (int, float)):
        amount = asset.get("price")
    content = strip_html(source.get("content"))
    return Opportunity(
        provider="gibwork",
        id=str(item.get("id", "")),
        title=str(item.get("title", "Untitled opportunity")),
        url=f"https://app.gib.work/tasks/{item.get('id', '')}",
        reward_amount=float(amount) if isinstance(amount, (int, float)) else None,
        reward_token=asset.get("symbol"),
        deadline=item.get("deadline") or source.get("deadline"),
        sponsor=(source.get("user") or item.get("user") or {}).get("username"),
        category=item.get("type"),
        status=item.get("status") or source.get("status"),
        submission_mode="platform_account",
        autonomous=False,
        risk_flags=gibwork_risk_flags(item, detail),
        summary=content[:240] if content else None,
    )


def fetch_gibwork(*, max_pages: int = 5, details: bool = True) -> list[Opportunity]:
    candidates: dict[str, dict[str, Any]] = {}
    empty_live_pages = 0
    for page in range(1, max_pages + 1):
        data = fetch_json(f"https://app.gib.work/api/explore?page={page}")
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            raise RadarError("Gibwork returned an invalid explore response")
        live_on_page = 0
        for item in results:
            if (
                item.get("isOpen")
                and item.get("status") != "CLOSED"
                and (item.get("remainingAmount") or 0) > 0
                and is_live(item.get("deadline"))
            ):
                candidates[str(item.get("id"))] = item
                live_on_page += 1
        empty_live_pages = empty_live_pages + 1 if live_on_page == 0 else 0
        if page >= int(data.get("lastPage") or page) or empty_live_pages >= 2:
            break

    opportunities: list[Opportunity] = []
    for item in candidates.values():
        detail = None
        if details:
            try:
                detail = fetch_json(f"https://app.gib.work/api/tasks/{item['id']}")
            except Exception:
                detail = None
        opportunities.append(normalize_gibwork(item, detail))
    return opportunities


REWARD_PATTERN = re.compile(
    r"(?:(?P<currency>USDC|USDT|SOL|USDG|USD|\$)\s*)?"
    r"(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*"
    r"(?P<suffix>k)?\s*(?P<trailing>USDC|USDT|SOL|USDG|USD)?",
    re.IGNORECASE,
)


def extract_reward(text: str) -> tuple[float | None, str | None]:
    for match in REWARD_PATTERN.finditer(text):
        currency = match.group("trailing") or match.group("currency")
        if not currency:
            continue
        amount = float(match.group("amount").replace(",", ""))
        if match.group("suffix"):
            amount *= 1000
        token = "USD" if currency == "$" else currency.upper()
        return amount, token
    return None, None


def normalize_github(item: dict[str, Any]) -> Opportunity:
    text = f"{item.get('title', '')} {item.get('body') or ''}"
    reward_amount, reward_token = extract_reward(text)
    repository_url = item.get("repository_url", "")
    sponsor = repository_url.rsplit("/", 2)[-2] if "/" in repository_url else None
    risk_flags = ["escrow_unverified", "payment_terms_require_review"]
    if re.search(r"\b(?:quarantined|do not claim)\b", text, re.IGNORECASE):
        risk_flags.append("listing_quarantined")
    if "bounty-plaza" in repository_url:
        risk_flags.append("mirror_listing")
    return Opportunity(
        provider="github",
        id=str(item.get("id", "")),
        title=str(item.get("title", "Untitled issue")),
        url=str(item.get("html_url", "")),
        reward_amount=reward_amount,
        reward_token=reward_token,
        deadline=None,
        sponsor=sponsor,
        category="issue",
        status=str(item.get("state", "open")),
        submission_mode="maintainer_defined",
        autonomous=False,
        risk_flags=risk_flags,
        summary=strip_html(item.get("body"))[:240] or None,
    )


def fetch_github() -> list[Opportunity]:
    query = 'is:issue is:open label:bounty (USDC OR SOL OR USDG) in:title,body'
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    params = {"q": query, "sort": "updated", "order": "desc", "per_page": 30}
    data = fetch_json(f"https://api.github.com/search/issues?{urlencode(params)}", headers=headers)
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise RadarError("GitHub returned an invalid search response")
    return [normalize_github(item) for item in items]


ALGORA_REWARD_PATTERN = re.compile(
    r"\bis offering an?\s+\*\*\$(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\*\*\s+bounty\b",
    re.IGNORECASE,
)


def extract_algora_reward(comments: Iterable[dict[str, Any]]) -> float | None:
    for comment in reversed(list(comments)):
        user = comment.get("user") or {}
        if user.get("login") != "algora-pbc":
            continue
        match = ALGORA_REWARD_PATTERN.search(str(comment.get("body") or ""))
        if match:
            return float(match.group("amount").replace(",", ""))
    return None


def normalize_algora(
    item: dict[str, Any],
    reward_amount: float,
    repository: dict[str, Any] | None = None,
) -> Opportunity:
    repository_url = str(item.get("repository_url") or "")
    sponsor = repository_url.rsplit("/", 2)[-2] if "/" in repository_url else None
    risk_flags = ["platform_account_required", "payment_profile_required", "bounty_status_requires_review"]
    summary = "Bounty announced by Algora's official GitHub account. Verify that it remains funded and unclaimed before starting."
    if repository:
        stars = repository.get("stargazers_count")
        if isinstance(stars, int) and stars < 5:
            risk_flags.append("low_signal_repository")
        if repository.get("fork"):
            risk_flags.append("forked_repository")
        summary = f"Official Algora announcement; repository has {stars or 0:,} GitHub stars. Confirm funding and claim status before starting."
    else:
        risk_flags.append("repository_metadata_unavailable")
    return Opportunity(
        provider="algora",
        id=str(item.get("id", "")),
        title=str(item.get("title", "Untitled issue")),
        url=str(item.get("html_url", "")),
        reward_amount=reward_amount,
        reward_token="USD",
        sponsor=sponsor,
        category="issue",
        status=str(item.get("state", "open")),
        submission_mode="github_pr_plus_platform_account",
        autonomous=False,
        risk_flags=risk_flags,
        summary=summary,
    )


def fetch_algora() -> list[Opportunity]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    params = {
        "q": "is:issue is:open commenter:algora-pbc",
        "sort": "updated",
        "order": "desc",
        "per_page": 50,
    }
    data = fetch_json(f"https://api.github.com/search/issues?{urlencode(params)}", headers=headers)
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise RadarError("GitHub returned an invalid Algora issue search response")

    opportunities: list[Opportunity] = []
    for item in items:
        comments_url = item.get("comments_url")
        if not comments_url:
            continue
        try:
            comments = fetch_json(f"{comments_url}?per_page=100", headers=headers)
        except Exception:
            continue
        if not isinstance(comments, list):
            continue
        reward_amount = extract_algora_reward(comments)
        if reward_amount is not None:
            repository = None
            repository_url = item.get("repository_url")
            if repository_url:
                try:
                    repository = fetch_json(repository_url, headers=headers)
                except Exception:
                    repository = None
            if isinstance(repository, dict) and repository.get("archived"):
                continue
            opportunities.append(normalize_algora(item, reward_amount, repository))
    return opportunities


MAIAR_REWARD_PATTERN = re.compile(
    r"(?:bounty\s*:|reward\s*:\s*(?:\*\*)?)\s*"
    r"(?P<amount>\d[\d\s,]*(?:\.\d+)?)\s*(?:\*\*)?\s*\$?MAIAR\b",
    re.IGNORECASE,
)


def extract_maiar_reward(issue: dict[str, Any], comments: Iterable[dict[str, Any]]) -> float | None:
    sources = [str(issue.get("body") or "")]
    for comment in comments:
        if str(comment.get("author_association") or "").upper() not in {
            "OWNER",
            "MEMBER",
            "COLLABORATOR",
        }:
            continue
        sources.append(str(comment.get("body") or ""))
    for source in reversed(sources):
        match = MAIAR_REWARD_PATTERN.search(source)
        if match:
            return float(re.sub(r"[\s,]", "", match.group("amount")))
    return None


def normalize_maiar(item: dict[str, Any], reward_amount: float) -> Opportunity:
    return Opportunity(
        provider="maiar",
        id=str(item.get("id", "")),
        title=str(item.get("title", "Untitled issue")),
        url=str(item.get("html_url", "")),
        reward_amount=reward_amount,
        reward_token="MAIAR",
        sponsor="UraniumCorporation",
        category="issue",
        status=str(item.get("state", "open")),
        submission_mode="github_rfc_pr_auto_solana_payout",
        autonomous=True,
        risk_flags=[
            "maintainer_merge_required",
            "reward_token_low_volume",
            "reward_token_price_volatile",
            "rfc_approval_required",
        ],
        summary=(
            "Repository-native bounty with automatic on-chain payout to the Solana "
            "address in the merged PR. Reward value depends on MAIAR liquidity."
        ),
    )


def fetch_maiar() -> list[Opportunity]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    params = {"state": "open", "labels": "bounty", "per_page": 100}
    issues = fetch_json(
        f"https://api.github.com/repos/UraniumCorporation/maiar-ai/issues?{urlencode(params)}",
        headers=headers,
    )
    if not isinstance(issues, list):
        raise RadarError("MAIAR returned an invalid issue list")

    opportunities: list[Opportunity] = []
    for issue in issues:
        if issue.get("pull_request"):
            continue
        labels = {str(label.get("name") or "").casefold() for label in issue.get("labels") or []}
        if "bounty paid" in labels:
            continue
        comments: list[dict[str, Any]] = []
        comments_url = issue.get("comments_url")
        if comments_url:
            try:
                response = fetch_json(f"{comments_url}?per_page=100", headers=headers)
                if isinstance(response, list):
                    comments = response
            except Exception:
                comments = []
        reward_amount = extract_maiar_reward(issue, comments)
        if reward_amount is not None:
            opportunities.append(normalize_maiar(issue, reward_amount))
    return opportunities


PROVIDERS = {
    "taskbounty": fetch_taskbounty,
    "superteam": fetch_superteam,
    "gibwork": fetch_gibwork,
    "algora": fetch_algora,
    "maiar": fetch_maiar,
    "github": fetch_github,
}


def scan(provider_names: Iterable[str], *, max_pages: int, details: bool) -> tuple[list[Opportunity], list[str]]:
    opportunities: list[Opportunity] = []
    errors: list[str] = []
    for provider_name in provider_names:
        try:
            if provider_name == "gibwork":
                found = fetch_gibwork(max_pages=max_pages, details=details)
            else:
                found = PROVIDERS[provider_name]()
            opportunities.extend(found)
        except Exception as exc:
            errors.append(f"{provider_name}: {exc}")
    return opportunities, errors


def reward_label(item: Opportunity) -> str:
    if item.reward_amount is None:
        return "unknown"
    amount = f"{item.reward_amount:,.2f}".rstrip("0").rstrip(".")
    return f"{amount} {item.reward_token or ''}".strip()


def render_table(items: list[Opportunity]) -> str:
    if not items:
        return "No matching opportunities found."
    lines = []
    for item in items:
        mode = "AUTO" if item.autonomous else "REVIEW"
        risks = ", ".join(item.risk_flags) if item.risk_flags else "none"
        lines.append(f"[{mode}] {item.provider:9} | {reward_label(item):>12} | {item.title}")
        lines.append(f"  {item.url}")
        lines.append(f"  deadline={item.deadline or 'none'} risks={risks}")
    return "\n".join(lines)


def parse_provider_names(value: str) -> list[str]:
    if value == "all":
        return list(PROVIDERS)
    names = [part.strip().lower() for part in value.split(",") if part.strip()]
    invalid = [name for name in names if name not in PROVIDERS]
    if invalid:
        raise argparse.ArgumentTypeError(f"unknown providers: {', '.join(invalid)}")
    return names


def canonical_title(value: str) -> str:
    """Normalize common mirror prefixes so repeated bounty leads collapse."""
    return re.sub(r"^\s*\[bounty\]\s*", "", value, flags=re.IGNORECASE).strip().casefold()


def deduplicate_opportunities(items: Iterable[Opportunity]) -> list[Opportunity]:
    unique: dict[tuple[str, str], Opportunity] = {}
    for item in items:
        key = (item.provider, canonical_title(item.title))
        existing = unique.get(key)
        item_quality = ("mirror_listing" in item.risk_flags, len(item.risk_flags))
        existing_quality = (
            "mirror_listing" in existing.risk_flags,
            len(existing.risk_flags),
        ) if existing else None
        if existing is None or item_quality < existing_quality:
            unique[key] = item
    return list(unique.values())


def ranking_key(item: Opportunity) -> tuple[bool, bool, int, float, str]:
    """Prefer executable, lower-friction work over eye-catching unverified prizes."""
    provider_requires_manual_payment_review = item.provider == "github"
    return (
        not item.autonomous,
        provider_requires_manual_payment_review,
        len(item.risk_flags),
        -(item.reward_amount or 0),
        item.title.casefold(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="all", help="all or comma-separated provider names")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--min-reward", type=float, default=0.0)
    parser.add_argument("--autonomous-only", action="store_true")
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--no-details", action="store_true")
    parser.add_argument("--stable", action="store_true", help="omit changing timestamps from JSON")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        provider_names = parse_provider_names(args.provider)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    opportunities, errors = scan(
        provider_names,
        max_pages=max(1, args.max_pages),
        details=not args.no_details,
    )
    opportunities = deduplicate_opportunities([
        item
        for item in opportunities
        if (item.reward_amount or 0) >= args.min_reward
        and (not args.autonomous_only or item.autonomous)
    ])
    opportunities.sort(key=ranking_key)

    if args.format == "json" or args.output:
        payload = {
            "generated_at": None if args.stable else datetime.now(timezone.utc).isoformat(),
            "tip_wallet": WALLET,
            "opportunity_count": len(opportunities),
            "opportunities": [asdict(item) for item in opportunities],
            "provider_errors": errors,
        }
        output = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    else:
        output = render_table(opportunities) + "\n"
        if errors:
            output += "\nProvider errors:\n" + "\n".join(f"- {error}" for error in errors) + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
