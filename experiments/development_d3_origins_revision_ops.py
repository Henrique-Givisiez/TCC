"""Prospective R2 one-entry operations; original attempts remain consumed."""
from contextlib import contextmanager
from experiments import development_d3_origins as origins
from experiments import development_d3_origins_ops as previous
from experiments import development_d3_origins_revision as revision


def get_plan():
    validation=revision.validate_plan();plan=origins.read(revision.DEFAULT_MANIFEST)
    revision.validate_handoff(plan)
    return plan,validation


@contextmanager
def release_context():
    old_manifest=origins.DEFAULT_MANIFEST;old_get=previous.get_plan
    try:
        origins.DEFAULT_MANIFEST=revision.DEFAULT_MANIFEST;previous.get_plan=get_plan
        yield
    finally:
        origins.DEFAULT_MANIFEST=old_manifest;previous.get_plan=old_get


def main():
    with release_context():previous.main()


if __name__=='__main__':main()
