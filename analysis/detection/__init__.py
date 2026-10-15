"""Stage 11: scalar, label-free detection infrastructure (no statistical methods)."""
from .inputs import load_series
from .pipeline import fit_baseline, score_run, calibrate, decide, load_scores, load_decisions
from .contracts import Component, Observation, ObservedSeries, ScoreValue

__all__ = ['load_series', 'fit_baseline', 'score_run', 'calibrate', 'decide',
           'load_scores', 'load_decisions', 'Component', 'Observation', 'ObservedSeries', 'ScoreValue']
