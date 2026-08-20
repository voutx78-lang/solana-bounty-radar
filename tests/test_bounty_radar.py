import unittest
from datetime import datetime, timezone

import bounty_radar as radar


class BountyRadarTests(unittest.TestCase):
    def test_deadline_filter(self):
        now = datetime(2026, 8, 13, tzinfo=timezone.utc)
        self.assertTrue(radar.is_live("2026-08-14T00:00:00.000Z", now=now))
        self.assertFalse(radar.is_live("2026-08-12T23:59:59.000Z", now=now))
        self.assertTrue(radar.is_live(None, now=now))

    def test_superteam_is_autonomous(self):
        item = {
            "id": "abc",
            "slug": "agent-bounty",
            "title": "Build a useful agent",
            "rewardAmount": 500,
            "token": "USDC",
            "deadline": "2026-09-01T00:00:00.000Z",
            "type": "bounty",
            "status": "OPEN",
            "sponsor": {"name": "Verified Sponsor"},
        }
        result = radar.normalize_superteam(item)
        self.assertTrue(result.autonomous)
        self.assertEqual(result.submission_mode, "official_agent_api")
        self.assertEqual(result.reward_amount, 500)

    def test_gibwork_flags_account_and_health_risks(self):
        item = {
            "id": "task-1",
            "title": "Example task",
            "remainingAmount": 60,
            "deadline": "2026-09-01T00:00:00.000Z",
            "status": "CREATED",
            "type": "tasks",
            "tags": ["Development"],
            "asset": {"symbol": "USDC"},
            "user": {"username": "sponsor"},
        }
        detail = {
            **item,
            "health": {"status": "paused"},
            "allowOnlyVerifiedSubmissions": True,
            "taskSubmissionsPendingCount": 111,
        }
        result = radar.normalize_gibwork(item, detail)
        self.assertFalse(result.autonomous)
        self.assertIn("health_paused", result.risk_flags)
        self.assertIn("verified_account_required", result.risk_flags)
        self.assertIn("crowded_50_plus_pending", result.risk_flags)

    def test_extract_reward(self):
        self.assertEqual(radar.extract_reward("[Bounty: 23 USDC] Fix it"), (23.0, "USDC"))
        self.assertEqual(radar.extract_reward("Reward 0.5 SOL"), (0.5, "SOL"))
        self.assertEqual(radar.extract_reward("$2k security bounty"), (2000.0, "USD"))
        self.assertEqual(radar.extract_reward("Prize: $25,000 USDC"), (25000.0, "USDC"))
        self.assertEqual(radar.extract_reward("Reward 1,250.50 USDT"), (1250.5, "USDT"))

    def test_deduplicates_bounty_mirrors_and_keeps_original(self):
        original = radar.Opportunity(
            provider="github",
            id="original",
            title="[3 USDC] Build a useful corpus",
            url="https://github.com/example/project/issues/1",
            risk_flags=["escrow_unverified", "payment_terms_require_review"],
        )
        mirror = radar.Opportunity(
            provider="github",
            id="mirror",
            title="[Bounty] [3 USDC] Build a useful corpus",
            url="https://github.com/example/bounty-plaza/issues/2",
            risk_flags=["escrow_unverified", "payment_terms_require_review", "mirror_listing"],
        )
        self.assertEqual(radar.deduplicate_opportunities([mirror, original]), [original])

    def test_ranking_prefers_lower_friction_work(self):
        safer = radar.Opportunity(
            provider="gibwork",
            id="safer",
            title="Small verified task",
            url="https://example.com/safer",
            reward_amount=60,
            risk_flags=["platform_account_required"],
        )
        unverified = radar.Opportunity(
            provider="github",
            id="unverified",
            title="Huge unverified promise",
            url="https://example.com/unverified",
            reward_amount=25000,
            risk_flags=["escrow_unverified", "payment_terms_require_review"],
        )
        self.assertLess(radar.ranking_key(safer), radar.ranking_key(unverified))

    def test_extracts_only_official_algora_reward_comments(self):
        comments = [
            {"user": {"login": "random-user"}, "body": "ev is offering a **$9,999** bounty"},
            {
                "user": {"login": "algora-pbc"},
                "body": "💎 **ev** is offering a **$1,250.50** bounty for this issue",
            },
        ]
        self.assertEqual(radar.extract_algora_reward(comments), 1250.5)

    def test_normalize_algora_requires_payment_profile_review(self):
        item = {
            "id": 313,
            "title": "Option to return errors as JSON",
            "html_url": "https://github.com/elysiajs/elysia/issues/313",
            "repository_url": "https://api.github.com/repos/elysiajs/elysia",
            "state": "open",
        }
        result = radar.normalize_algora(item, 100, {"stargazers_count": 1200, "fork": False})
        self.assertEqual(result.provider, "algora")
        self.assertEqual(result.reward_amount, 100)
        self.assertIn("payment_profile_required", result.risk_flags)
        self.assertFalse(result.autonomous)

    def test_low_signal_algora_repository_is_flagged(self):
        item = {
            "id": 1,
            "title": "Test bounty",
            "html_url": "https://github.com/example/repo/issues/1",
            "repository_url": "https://api.github.com/repos/example/repo",
            "state": "open",
        }
        result = radar.normalize_algora(item, 10, {"stargazers_count": 0, "fork": False})
        self.assertIn("low_signal_repository", result.risk_flags)


if __name__ == "__main__":
    unittest.main()
