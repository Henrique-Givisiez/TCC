"""Scientific selection after Stage 10; never truncates inputs or resets state."""
from .inputs import ContractError, number
from .protocol import load_protocol


def select_campaign_records(records, protocol_reference, partition):
    """Select aligned observations/scores/decisions, retaining null/unavailable.

    This pure selection confers no TEST release or data-loading capability.
    Callers must perform their normal partition gates before input access.
    """
    doc, ref = load_protocol(protocol_reference['path'], expected_hash=protocol_reference['protocol_hash'])
    if ref != protocol_reference or doc['protocol_version'] != 2:
        raise ContractError('Temporal selection requires bound protocol V2')
    if partition not in ('baseline', 'calibration', 'test'):
        raise ContractError('Unknown temporal selection partition')
    a, b = map(number, doc['frozen']['temporal_selections'][partition])
    records = tuple(records)
    def window(row):
        return row.score if hasattr(row, 'decision') else row
    for row in records:
        w = window(row)
        if w.window_end_seconds <= w.window_start_seconds:
            raise ContractError('Invalid observation window')
    chosen = tuple(row for row in records if a <= window(row).window_start_seconds
                   and window(row).window_end_seconds <= b)
    return chosen, dict(protocol=ref, partition=partition, start_seconds=str(a), end_seconds=str(b),
        inclusion='whole_windows_contained_in_half_open_interval',
        supplied_windows=len(records), selected_windows=len(chosen),
        selected_window_indices=[window(row).window_index for row in chosen],
        nominal_exposure_seconds=str(b-a),
        causal_history='preserved_from_run_start_no_reset_at_selection_start',
        nulls_and_unavailable='preserved; not zero, not imputed')
