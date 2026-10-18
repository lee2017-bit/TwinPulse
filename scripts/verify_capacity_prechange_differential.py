# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only differential of four broad-suite failures under prior capacity rules.

This is not a checkout/source rollback or a full source bisect. Only prior
capacity, expansion version and raw-only observer validation are restored in
this isolated process; fake transports and original evidence remain unchanged.
"""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_provider/tests'))
sys.path.insert(0,str(ROOT))
import pytest
from twinpulse_provider import nebius_pipeline as pipeline,observation_instances as instances


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--xml',type=Path,required=True)
    args=parser.parse_args();output=args.xml.resolve()
    if ROOT/'outputs/photo-paste-capacity-20261012' not in output.parents or output.exists():
        raise SystemExit('SCOPED_NEW_OUTPUT_REQUIRED')
    pipeline.MAX_OBSERVATION_OBJECT_INSTANCES=24
    pipeline.MAX_DERIVED_OBSERVATION_ENTITIES=48
    instances.MAX_OBSERVATION_OBJECT_INSTANCES=24
    instances.MAX_DERIVED_OBSERVATION_ENTITIES=48
    instances.INSTANCE_REVISION='observed-instance-expansion-1.1'
    instances.checked_observation_instances=pipeline.ObservationArtifact.from_mapping
    tests=[
        'packages/twinpulse_provider/tests/test_photo_semantic_review.py::PhotoSemanticReviewTests::test_original_failed_real_packing_response_recompiles_without_source_or_model_change',
        'packages/twinpulse_provider/tests/test_rollback_revalidation.py::RollbackRevalidationTests::test_last_slot_rolls_back_revalidates_and_stops_for_quality_not_unmapped',
        'packages/twinpulse_provider/tests/test_warehouse_semantics.py::WarehouseSemanticsTests::test_real_generation_service_recovers_bad_support_without_special_ids',
        'packages/twinpulse_provider/tests/test_warehouse_semantics.py::WarehouseSemanticsTests::test_unchanged_repair_still_stops_and_keeps_the_failed_parent_relation']
    return pytest.main([*tests,'-q','--tb=short','--junitxml='+str(output)])


if __name__=='__main__':raise SystemExit(main())
