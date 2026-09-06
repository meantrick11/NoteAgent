"""Offline prompt eval: L1 scoring, reports, in-process ChatAgent runs.

Chat must not import this package. Scoring never writes notes/ or calls review.
"""

from noteagent.prompt_eval.cases import EvalCase, load_cases
from noteagent.prompt_eval.score import NoteScore, score_note

__all__ = ["EvalCase", "NoteScore", "load_cases", "score_note"]
