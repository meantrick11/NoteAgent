"""Offline prompt eval: L1 scoring, reports, in-process ChatAgent runs.

Chat must not import this package. Scoring never writes notes/ or calls review.
"""

from NoteAgentEvals.Prompt.Cases import EvalCase, load_cases
from NoteAgentEvals.Prompt.Score import NoteScore, score_note

__all__ = ["EvalCase", "NoteScore", "load_cases", "score_note"]
