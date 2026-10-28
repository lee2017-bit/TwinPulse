# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
r"""Measure Nemotron sizes on the TwinPulse robot mission-planning task (the app's instruction, schema and settings).

Each call sends the installed app's planning request for "Survey the room and come back" and the other
prompts: the planner instruction from robot_task_planner.py (copied verbatim), the capability-restricted
JSON schema from twinpulse_core.robot_task_plan.plan_schema, response_format=json_schema (strict),
temperature 0, the app's planner output cap. Not reproduced: the two lines the app's transport appends to the
system prompt (the one-sentence guidance of the harness profile bound to the planner stage and a compact copy
of the schema, see stage_transport.explicit_json_contract) and the saved routing's thinking-mode flag.
Every answer is validated with checked_plan(), the same function the app uses, so "valid" here means
"the app would have executed it".

Records per call: wall latency, HTTP status, finish_reason, usage (prompt/completion/reasoning tokens),
validity (or the ROBOT_TASK_* error code), the step list, and the raw content. Writes a JSONL log and a
Markdown summary table (valid/N, latency min/median/max, completion tokens median).

Needs the repo for twinpulse_core: run from the repo root, or pass --repo. Needs a Nebius Token Factory
key: env NEBIUS_API_KEY, or on Windows the app's Credential Manager target (--credential-target, default
TwinPulse/OpenAIResponsesAPI; the Model routing keys live under TwinPulse/ProviderKeys/<profile>/<id>).

usage (PC, repo .venv):
  .venv\Scripts\python.exe benchmark_planner_sizes.py --repo . --trials 5 --out outputs\bench-planner-20261029
  .venv\Scripts\python.exe benchmark_planner_sizes.py --repo . --discover          # list Nemotron text models
  .venv\Scripts\python.exe benchmark_planner_sizes.py --repo . --dry-run           # print bodies, no calls
Calls: len(models) x len(prompts) x trials, sequential (latency is measured one call at a time).
"""
import argparse, json, os, statistics, sys, time, urllib.error, urllib.request
from pathlib import Path

BASE = 'https://api.tokenfactory.nebius.com/v1/'
DEFAULT_MODELS = [
    'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
    'nvidia/nemotron-3-super-120b-a12b',
]
PROMPTS = {
    'demo_survey': 'Survey the room and come back',
    'explicit_moves': 'Go forward 1 m, turn left 90 degrees, then return to the start and stop',
    'inspect': 'Inspect the room and report what you see, then stop',
}
# Copied verbatim from packages/twinpulse_provider/src/twinpulse_provider/robot_task_planner.py (main, 2026-10-28).
INSTRUCTION = (
    'Translate the human ROBOT goal into a bounded composition of the supplied capabilities. Output English JSON, never code. '
    'observe collects a fresh stationary LiDAR/pose pair; survey MOVES to different reachable observation locations, not a 360-degree spin. '
    'return_to_start replans a checked route to the original start, not a blind reversal. '
    'move_relative amount is metres (forward/backward) or radians (left/right); one step <=2m or 2pi. '
    'navigate approaches the nearest named object using current geometry. Do not invent coordinates, targets, sensors or evidence. '
    'You may combine, order and explicitly unroll bounded repetitions of these capabilities (max12 steps). '
    'Use survey for inspect/explore/measure a room; include return_to_start only when requested. '
    'For a loop round the room and back use observe,survey,return_to_start,stop. Never substitute an in-place full turn. '
    'The mandatory_capabilities list is a host validation constraint: every listed capability MUST occur in steps. '
    'When survey is mandatory, use the survey operation; do NOT replace it with a rectangular patrol or invented fixed moves. '
    'Do NOT add relative movements around survey merely to implement exploration: survey already chooses and moves to observation locations. '
    'move_relative is available in the schema only if the human separately requested directional actions; a distance limit is not such a request. '
    'left/right are rotations in radians, never lateral metres. The host survey chooses observation positions from current geometry. '
    'Every explicitly requested return and stop MUST appear as actual steps, not only in the explanation. '
    'Example: forward 10cm, left30 degrees, return and stop requires FOUR steps: move_relative(forward,0.1), move_relative(left,0.5235987756), return_to_start, stop. '
    'Limits cap the ENTIRE task including return: <=12m, <=600s, <=128 finite segments. Prefer 8m/300s/96 for a room survey. '
    'When the human supplies bounded total limits, preserve those limits instead of arbitrarily shrinking them. '
    'A return needs extra finite turns and translations, so never reserve segments only for the initial explicit moves. '
    'Safety, completion, coverage, current pose and permission are determined by the host, not by this JSON. '
    'Unsupported or ambiguous goals use clarify with empty steps. No automatic retry or execution follows this proposal.')


def load_core(repo):
    sys.path.insert(0, str(Path(repo) / 'packages/twinpulse_core/src'))
    from twinpulse_core import robot_task_plan as rtp  # noqa: E402
    return rtp


def api_key(args):
    key = os.environ.get('NEBIUS_API_KEY') or os.environ.get('TOKEN_FACTORY_API_KEY')
    if key:
        return key.strip()
    if os.name == 'nt':
        sys.path.insert(0, str(Path(args.repo) / 'packages/twinpulse_app/src'))
        try:
            from twinpulse_app.credentials import WindowsCredentialStore
            value = WindowsCredentialStore(args.credential_target).load()
            if value:
                return value.strip()
        except Exception as error:  # keep going to the clear message below
            print('credential store read failed:', error, file=sys.stderr)
    raise SystemExit('NO_API_KEY: set NEBIUS_API_KEY or pass --credential-target with the app key target')


def http(path, key, body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method='POST' if data else 'GET',
                                 headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
            return resp.status, payload, time.perf_counter() - started
    except urllib.error.HTTPError as error:
        text = error.read().decode(errors='replace')
        try:
            payload = json.loads(text)
        except ValueError:
            payload = {'error_text': text[:2000]}
        return error.code, payload, time.perf_counter() - started
    except Exception as error:
        return 0, {'error_text': repr(error)}, time.perf_counter() - started


def make_body(rtp, model, text, robot_kind, max_tokens):
    allowed = rtp.request_capabilities(text)
    planning_input = dict(text=text, robot_kind=robot_kind, capabilities=list(allowed),
                          mandatory_capabilities=sorted(rtp.explicit_requirements(text)))
    return {
        'model': model, 'temperature': 0, 'max_tokens': max_tokens,
        'response_format': {'type': 'json_schema', 'json_schema': {
            'name': 'twinpulse_robot_task', 'strict': True, 'schema': rtp.plan_schema(capabilities=allowed)}},
        'messages': [{'role': 'system', 'content': INSTRUCTION},
                     {'role': 'user', 'content': json.dumps(planning_input, ensure_ascii=False)}],
    }


def judge(rtp, status, payload, text):
    """Return (valid, code, steps, content, finish_reason, usage)."""
    if status != 200:
        return False, 'HTTP_%d' % status, [], json.dumps(payload)[:2000], None, {}
    try:
        choice = payload['choices'][0]
        finish = choice.get('finish_reason')
        content = choice['message'].get('content') or ''
        usage = payload.get('usage') or {}
    except (KeyError, IndexError, TypeError):
        return False, 'RESPONSE_SHAPE', [], json.dumps(payload)[:2000], None, {}
    if finish != 'stop':
        return False, 'FINISH_' + str(finish).upper(), [], content[:2000], finish, usage
    try:
        value = json.loads(content)
    except ValueError:
        return False, 'JSON_PARSE', [], content[:2000], finish, usage
    try:
        plan = rtp.checked_plan(value, request_text=text)
    except ValueError as error:
        return False, str(error), [], content[:2000], finish, usage
    return True, 'OK', [s['op'] for s in plan['steps']], content[:2000], finish, usage


def discover(key):
    status, payload, _ = http('models', key)
    if status != 200:
        raise SystemExit('models list failed: %s %s' % (status, json.dumps(payload)[:500]))
    ids = sorted(m['id'] for m in payload.get('data', []) if isinstance(m, dict) and 'id' in m)
    nemo = [i for i in ids if 'nemotron' in i.lower()]
    print('Nemotron models on this account (%d of %d):' % (len(nemo), len(ids)))
    for i in nemo:
        print('  ' + i + ('   (vision; skip for the planner)' if 'vl' in i.lower().split('-') or 'vision' in i.lower() else ''))


def summarize(rows):
    out = ['| Model | Prompt | Valid | Latency s min / median / max | Completion tokens median | Reasoning tokens median | Failure codes |',
           '| --- | --- | --- | --- | --- | --- | --- |']
    keys = sorted({(r['model'], r['prompt_id']) for r in rows})
    for model, pid in keys:
        rs = [r for r in rows if r['model'] == model and r['prompt_id'] == pid]
        lat = [r['latency_s'] for r in rs]
        comp = [r['usage'].get('completion_tokens') for r in rs if r['usage'].get('completion_tokens') is not None]
        reas = [(r['usage'].get('completion_tokens_details') or {}).get('reasoning_tokens') for r in rs]
        reas = [x for x in reas if x is not None]
        fails = sorted({r['code'] for r in rs if not r['valid']})
        out.append('| %s | %s | %d/%d | %.1f / %.1f / %.1f | %s | %s | %s |' % (
            model, pid, sum(r['valid'] for r in rs), len(rs), min(lat), statistics.median(lat), max(lat),
            ('%d' % statistics.median(comp)) if comp else '-', ('%d' % statistics.median(reas)) if reas else '-',
            ', '.join(fails) or '-'))
    return '\n'.join(out)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--repo', default=os.environ.get('TWINPULSE_REPO', '.'))
    p.add_argument('--models', nargs='*', default=DEFAULT_MODELS)
    p.add_argument('--prompts', nargs='*', default=list(PROMPTS), choices=list(PROMPTS))
    p.add_argument('--trials', type=int, default=5)
    p.add_argument('--robot-kind', default='physical', choices=['sim', 'physical'])
    p.add_argument('--max-tokens', type=int, default=40000, help='app planner cap (approved route uses 40000)')
    p.add_argument('--timeout', type=int, default=300)
    p.add_argument('--out', default='bench-planner-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    p.add_argument('--credential-target', default='TwinPulse/OpenAIResponsesAPI')
    p.add_argument('--discover', action='store_true', help='list Nemotron models on the account and exit')
    p.add_argument('--dry-run', action='store_true', help='print one request body per model/prompt, no calls')
    args = p.parse_args(argv)
    rtp = load_core(args.repo)
    if args.dry_run:
        for model in args.models:
            for pid in args.prompts:
                body = make_body(rtp, model, PROMPTS[pid], args.robot_kind, args.max_tokens)
                print(json.dumps(body, ensure_ascii=False)[:600], '...')
        return 0
    key = api_key(args)
    if args.discover:
        discover(key); return 0
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    log = out / 'calls.jsonl'
    rows = []
    total = len(args.models) * len(args.prompts) * args.trials
    n = 0
    with log.open('a', encoding='utf-8') as fh:
        for trial in range(1, args.trials + 1):
            for model in args.models:
                for pid in args.prompts:
                    n += 1
                    text = PROMPTS[pid]
                    body = make_body(rtp, model, text, args.robot_kind, args.max_tokens)
                    status, payload, latency = http('chat/completions', key, body, timeout=args.timeout)
                    valid, code, steps, content, finish, usage = judge(rtp, status, payload, text)
                    row = dict(ts=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), trial=trial, model=model, prompt_id=pid,
                               text=text, status=status, latency_s=round(latency, 2), finish_reason=finish, valid=valid, code=code,
                               steps=steps, usage=usage, request_id=payload.get('id') if isinstance(payload, dict) else None,
                               content=content)
                    rows.append(row); fh.write(json.dumps(row, ensure_ascii=False) + '\n'); fh.flush()
                    print('[%d/%d] %-44s %-15s %5.1fs %s %s' % (n, total, model, pid, latency, 'VALID ' if valid else 'FAIL  ', code if not valid else '→'.join(steps)))
    summary = summarize(rows)
    (out / 'summary.md').write_text('# Planner size benchmark %s\n\nmax_tokens %d, temperature 0, robot_kind %s, %d trials, sequential.\n\n%s\n'
                                    % (args.out, args.max_tokens, args.robot_kind, args.trials, summary), encoding='utf-8')
    print('\n' + summary + '\nwrote ' + str(out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
