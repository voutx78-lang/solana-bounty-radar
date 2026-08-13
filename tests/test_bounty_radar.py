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


if __name__ == "__main__":
    unittest.main()
