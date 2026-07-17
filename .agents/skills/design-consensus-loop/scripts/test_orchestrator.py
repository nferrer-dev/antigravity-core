import unittest
from orchestrator import ConsensusOrchestrator

class TestConsensusOrchestrator(unittest.TestCase):
    def test_deadlock_yield(self):
        orchestrator = ConsensusOrchestrator(max_rounds=5)
        # Simulate 5 rounds of rejection
        for _ in range(5):
            orchestrator.submit_review("REJECT", "Still not good enough.")
        
        status = orchestrator.get_status()
        self.assertEqual(status, "DEADLOCK_ADJUDICATOR_FALLBACK")
        self.assertTrue(orchestrator.requires_llm_adjudication())

if __name__ == '__main__':
    unittest.main()
