"""Temporal selection of observations, without modifying Stage 10 inputs."""
from dataclasses import replace
from fractions import Fraction

from .inputs import ContractError, number, read_json, safe_file


def select_interval(source, start, end):
    """Select whole windows: a <= window.start and window.end <= b, [a,b)."""
    source.verify()
    a, b = number(start), number(end)
    series = source.series
    width = series.window_size_seconds
    if a < 0 or b <= a:
        raise ContractError('Invalid/empty fit_interval')
    if any(Fraction(x) % Fraction(width) for x in (a, b)):
        raise ContractError('fit_interval boundaries must align with Stage 10 grid')
    observations = series.observations
    if not observations or a < observations[0].window_start_seconds or b > observations[-1].window_end_seconds:
        raise ContractError('fit_interval outside feature horizon')
    manifest = read_json(safe_file(source.root, 'feature_manifest.json'))
    selected = tuple(o for o in observations if a <= o.window_start_seconds and o.window_end_seconds <= b)
    if not selected:
        raise ContractError('Empty fit_interval selection')
    valid = sum(o.value is not None for o in selected)
    record = dict(selection_schema_version=1, run_id=series.run_id,
                  fit_start_seconds=str(a), fit_end_seconds=str(b),
                  inclusion_policy='whole_windows_contained_in_half_open_interval',
                  feature_horizon_start_seconds=str(observations[0].window_start_seconds),
                  feature_horizon_end_seconds=str(observations[-1].window_end_seconds),
                  planned_duration_seconds=manifest['window'].get('planned_duration_seconds'),
                  candidate_windows=len(selected), valid_observations=valid,
                  nulls_excluded=len(selected)-valid, excluded_windows=len(observations)-len(selected),
                  selected_window_indices=[o.window_index for o in selected],
                  support_semantics='Stage10 support unchanged; full physical coverage not proven')
    return replace(series, observations=selected), record
