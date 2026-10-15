"""Exact finite-sample moments; only final divisions/square roots are rounded.

Fraction avoids cancellation (large offsets/small variation) and false zero means.
Decimal results use a private context, independent of caller settings.
"""
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction

from ..inputs import ContractError

PRECISION = 50
CONTEXT = Context(prec=PRECISION, rounding=ROUND_HALF_EVEN)


def finite_fraction(value):
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ContractError('Expected finite Decimal observation')
    return Fraction(value)


def sample_moments(values):
    """Return exact mean and sample variance (ddof=1), with equal sample weights."""
    samples = [finite_fraction(v) for v in values]
    if len(samples) < 2:
        raise ContractError('insufficient_baseline_observations: ddof=1 needs n>=2')
    mean = sum(samples, Fraction(0)) / len(samples)
    variance = sum(((v - mean) ** 2 for v in samples), Fraction(0)) / (len(samples) - 1)
    return mean, variance


def decimal_ratio(value):
    with localcontext(CONTEXT):
        return Decimal(value.numerator) / Decimal(value.denominator)


def standard_deviation(variance):
    with localcontext(CONTEXT):
        return decimal_ratio(variance).sqrt()


def fraction_record(value):
    return dict(numerator=str(value.numerator), denominator=str(value.denominator))


def read_fraction(record):
    try:
        numerator, denominator = record['numerator'], record['denominator']
        if not isinstance(numerator, str) or not isinstance(denominator, str):
            raise ValueError('Exact moments must use integer strings')
        if int(denominator) <= 0:
            raise ValueError('Nonpositive denominator')
        return Fraction(int(numerator), int(denominator))
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError('Invalid exact moment parameter') from exc
