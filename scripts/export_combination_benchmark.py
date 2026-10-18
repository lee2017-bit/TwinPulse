# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Export metrics-only GitHub report; never copies images, raw or geometry."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_model_combination_benchmark import public_summary,exposure,read


LABELS={'deepseek-ai/DeepSeek-V4.1-Flash':'DeepSeek Flash',
        'Qwen/Qwen3.8-27B':'Qwen 3.8 27B','gpt-6-luna':'GPT-6 Luna',
        'nvidia/Nemotron-3_5-Lightning':'Nemotron Lightning'}


def render(campaign):
    data=public_summary(campaign)
    lines=['# Actual model-combination integration benchmark — 2026-10-10','',
        'Status: '+campaign['status']+'. This is a private, single-image integration pilot, not a general model leaderboard.',
        'No physical robot was connected. PASS means the bounded ordinary App → actual Isaac SIM workflow completed; it does not mean measured photo reconstruction or collision-safe physical deployment.','',
        '## Protocol','',
        '- Fresh ordinary chat approvals and actual HTTP; no substituted model outputs or shared observation cache.',
        '- Same source photo and prompt for every fresh trial; one private bedroom, no measured dimensions or independent test set.',
        '- Each role: 20,000 output tokens, 300 s request timeout. Total active budget 900 s: initial420/repair300/final-render180. At most3 repairs,2 stalled repairs,24 HTTP per trial.',
        '- Reviewer is the observer model: source photo + candidate-bound actual Isaac frame. It is not an independent human judge.',
        '- Luna uses structured reasoning=none; Nemotron Lightning thinking is disabled. Provider-native preprocessing differs, with equivalent host constraints.',
        '- Geometric checks, candidate/plan/frame identity, final save, current rendered 3D, explicit PhysX arrival≤0.04 m, next-goal/chat Stop,1 s stationary hold, reload/reset and closed-backend saved-project reopen are required for full PASS.',
        '- Output-length exhaustion/unknown result stops new inference. Recorded rejected HTTP keeps unverified billing reserved; five consecutive distinct configurations with the same failure also stop.',
        '- Code cohorts are separate. Failed trials stay in the denominator; no-call harness preflight failures are reported separately.',
        '- Conservative per-trial financial grants vary from USD0.82 to USD1 as the campaign reservation decreases; request/token/time/repair caps remain fixed. No local financial grant exhaustion occurred.',
        '- p50/p95 use linear interpolation. With these small samples, p95 and Wilson95 intervals are descriptive, not evidence of production reliability.','',
        '## Results by role and code cohort','',
        '| Observer / critic | Planner / repair | Code SHA | Full PASS / trials | Wilson95 | Requests | Repairs / recovered trials | Saved objects | End-to-end p50 / p95 s | Usage estimate USD | Held billing USD |',
        '|---|---|---|---:|---|---:|---:|---|---:|---:|---:|']
    number=lambda value:'—' if value is None else f'{value:.2f}'
    for row in data['cohorts']:
        cost=sum((Decimal(v) for v in row['estimated_usd'].values()),Decimal(0))
        held=sum((Decimal(v) for v in row['held_without_usage_usd'].values()),Decimal(0))
        interval='–'.join(f'{100*v:.1f}%' for v in row['wilson_95_interval'])
        objects=', '.join(str(v) for v in row['saved_item_counts'])
        wall=row['end_to_end_wall']
        lines.append(f"| {LABELS.get(row['observer_model'],row['observer_model'])} | {LABELS.get(row['planner_model'],row['planner_model'])} | `{row['code_sha256'][:12]}` | {row['full_journey_pass']}/{row['samples']} | {interval} | {row['requests']} | {row['repair_requests']}/{row['natural_repair_recovery_samples']} | {objects} | {number(wall['p50_s'])} / {number(wall['p95_s'])} | {cost:.6f} | {held:.6f} |")
    lines += ['', 'Saved-object count is the model-declared inventory, not recognition recall. More objects can make packing harder; fewer objects can omit real obstacles. Zero saved objects in a failed trial does not mean its observation was empty.', '',
        '## Failure and current-render verdicts','']
    if data['blocked_providers']:
        lines += ['Provider-side HTTP402 blocked further paid inference for: '+', '.join(data['blocked_providers'])+'. User-approved spending caps are not provider account balances. No top-up, key switch or automatic paid retry was attempted.','']
    if data['deferred_cases']:
        lines += ['Deferred repeats (NOT_RUN, excluded from model trial denominators): '+', '.join(row['id']+' / '+row['reason'] for row in data['deferred_cases'])+'.','']
    for row in data['cohorts']:
        name=f"{LABELS.get(row['observer_model'],row['observer_model'])} / {LABELS.get(row['planner_model'],row['planner_model'])} · {row['code_sha256'][:12]}"
        lines.append(f"- {name}: terminal failures {row['failure_codes']}; local root codes {row['root_failure_codes']}; origins {row['failure_origins']}; render verdicts {row['current_render_verdicts']}.")
    lines += ['', 'An `uncertain` critique permits only the explicitly labelled approximate-Twin workflow. It is not photo-fidelity PASS. Any claimed natural repair recovery requires an actual repair request followed by the complete path; an injected offline regression is not counted.', '',
        '## Timing boundaries','',
        'End-to-end wall time includes isolated launch/preflight, browser actions, inference, Isaac, diagnostics, cleanup and reopen. Active generation time is separately bounded. Request time is the recorded HTTP wall time, not GPU compute time. Thread-CPU function profiles do not include network waiting and their cumulative nested times must not be summed as total wall time.',
        f"CPU-profile consistency warning: {data['cpu_profile_anomalous_trials']} trials contain at least one retained top function row with self time greater than cumulative time. Those CPU snapshots are not used for bottleneck ranking; timer/profiler calibration remains unverified. HTTP and end-to-end wall timings are separate measurements.",'']
    for row in data['cohorts']:
        lines.append(f"- {row['code_sha256'][:12]} {LABELS.get(row['observer_model'],row['observer_model'])}/{LABELS.get(row['planner_model'],row['planner_model'])}: generation active p50/p95 {number(row['generation_active']['p50_s'])}/{number(row['generation_active']['p95_s'])} s; request p50/p95 {number(row['request_latency']['p50_s'])}/{number(row['request_latency']['p95_s'])} s.")
    totals=exposure(campaign)
    lines += ['', '## Accounting and reproducibility','',
        f"No-call preflight failures: {data['preflight_failures']}. Conservative current exposure: Nebius USD{totals['nebius']}, OpenAI USD{totals['openai']}; caps USD5/USD1. These are usage-rate estimates plus retained unverified billing reservations, not invoices or account balances.",
        'Full model IDs, per-trial aliases, cohort SHA, stage timing distributions and failure categories are in the accompanying metrics JSON. Source-code SHA identifies the inference/compiler path, not a clean committed release; the working tree contains pre-existing changes.',
        'Reproduction requires a separately approved dataset, registered credentials and actual Isaac runtime. The campaign runner uses frozen reviewed cases and separate cost ledgers; refresh/report commands send no inference.',
        'Private raw dispatch/response/validation records, usage ledgers, checkpoint revisions and plan/frame hashes are retained locally. This report excludes the source image, private room geometry/coordinates, original user text, credentials and raw responses. Nothing was committed or pushed.','',
        '## Limits and remaining acceptance','',
        'One photograph repeated on one host cannot demonstrate other-room generalization, furniture-size accuracy, support realism, obstacle recall, independent visual quality, long autonomous loops or physical safety. Only the stated generated SIM routes are exercised. An earlier hardware snapshot was below recommended Isaac VRAM/RAM; a current hardware probe was permission-denied and not bypassed. These bounded successes are not a complex-scene capacity certification.','']
    return '\n'.join(lines),data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();destination=args.output.resolve()
    if destination.parent!=ROOT/'docs'/'benchmarks':raise ValueError('Export target must be the canonical docs/benchmarks directory')
    destination.parent.mkdir(exist_ok=True)
    report,data=render(read(args.campaign))
    destination.write_text(report,encoding='utf-8')
    destination.with_suffix('.json').write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(dict(status=data['status'],cohorts=len(data['cohorts']),source_images_included=False,raw_responses_included=False)))


if __name__=='__main__':main()
