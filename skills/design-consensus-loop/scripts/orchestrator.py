class ConsensusOrchestrator:
    def __init__(self, max_rounds=5):
        self.max_rounds = max_rounds
        self.current_round = 0
        self.reviews = []
    
    def submit_review(self, verdict: str, comment: str):
        self.reviews.append((self.current_round, verdict, comment))
        if verdict == "REJECT":
            self.current_round += 1

    def get_status(self):
        if self.current_round >= self.max_rounds:
            return "DEADLOCK_ADJUDICATOR_FALLBACK"
        return "IN_PROGRESS"
        
    def requires_llm_adjudication(self):
        return self.get_status() == "DEADLOCK_ADJUDICATOR_FALLBACK"
