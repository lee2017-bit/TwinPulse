# Photo observer benchmark, 2026-10-28: which model finds the objects in a room photo?

**Question.** TwinPulse's photo step asks a vision model to list the floor objects a room photo shows that the twin is missing. Until now the only evidence for the choice of model was pass/fail counts (Oct 10 and 11 pilots) and a two-photo look by eye (Oct 26–27). This benchmark scores the models against a hand-made ground-truth object list, the way the planner size benchmark scored plans with the app's validator.

**Method.** `scripts/benchmark_photo_observers.py` sends the request the installed app builds for **Analyze photo** (`twinpulse_provider/environment_photo.py`): the observer instruction (the script checks its copy against the source at start-up), the scene-name context the app itself sent for the Oct 28 photo job (`request.json` of that job: no existing props, 8 scanned objects: Chair0, Chair1, Refrigerator0, Sofa0, Storage0, Storage1, Storage2, Table0), the photo as a data URL with the app's `detail: auto`, `response_format: json_schema` (strict) from `photo_candidate_schema(context)`, temperature 0, the app's 40,000-token output cap, then the two steps the app's transport adds: the guidance text of the harness profile bound to the observer stage (the saved profiles on the demo PC, which equal the built-in observer text; the built-in default profile for the two models the app has never been routed to) and the compact schema copy appended by `explicit_json_contract`. Every answer is validated with `checked_photo_candidates(fresh=True, context=...)`, the function the app uses, so "valid" means the app would have shown the candidates.

**Ground truth.** Two photos of the same living room, taken by the operator on Oct 28 (2576×1932):
- `room-placed-20261028.jpg`, with the three objects placed for the repeat runs. Primary objects (must find): the cardboard box (A), the black bag (C) and the wooden stool with two plant pots (B). Secondary objects (correct if proposed, not required): the robot vacuum on its dock, a cordless stick vacuum on its stand, a wicker basket, the plant pots and small items by the window, a white coiled cable by the left wall, a cable and charger on the floor beside the sofa, the black TV cable hanging to the floor, the power strip at the wall outlet.
- `room-initial-20261028.jpg`, the same room before the objects were placed (the photo the app analysed at 16:05 UTC). Primary: the white coiled cable by the left wall, the cable and charger beside the sofa, a black bag on the floor at the end of the sofa, a yellow box under the sofa. Secondary: the stick vacuum, the robot vacuum, the stool with plant pots, the plant pots and basket by the window, the TV cable, the power adapter at the outlet, a tall white air conditioner by the window.

Each object has a normalized image region, a set of acceptable kinds from the app's vocabulary and a few label words (for example the stool may come back as `chair`, `unknown` or `small_equipment`, or as a label containing "stool"). The regions and lists were written by hand from the photos before any call was made and are in `GROUND_TRUTH` in the script. A candidate matches an object when its bbox centre lies inside the object's region widened by 0.05, or the boxes overlap with IoU ≥ 0.1, and its kind is acceptable or its label or description names the object. A second candidate on an already matched object is a duplicate. A candidate that matches nothing is a false positive; the summary lists every one so a reader can judge whether it is a real object the list lacks, a wrong box or an invention. Candidates naming the sofa, the TV, the window or the robot itself are false positives by the instruction's own rules.

**Metrics per call.** Valid (schema and contract), number of candidates, which primary and secondary objects were found, primary recall (found primary / all primary), precision ((primary + secondary found) / candidates), false positives, duplicates, latency, completion and reasoning tokens. Per model and photo the tables give valid/N, the medians and means, and a per-object detection count out of the valid calls.

**Models.** The account's image-capable models on Nebius Token Factory: `nvidia/Nemotron-3.5-Super-VL` (the app's observer since Oct 27), `deepseek-ai/DeepSeek-V4.1-Flash` (the observer before that), `Qwen/Qwen3.8-27B` and `google/gemma-3-27b-it` (observers in the Oct 10 pilot). GPT-6 Luna is an OpenAI model and was not sent the photos. 5 trials per model and photo, sequential, 40 scored calls plus 2 one-call probes; run from the PC with the app's own key on 2026-10-28/29.

## Results

Run from the PC on 2026-10-28 23:12–23:21 UTC: 2 one-call probes (Qwen 17.1 s, Gemma 62.9 s, both valid) and then 40 scored calls, all HTTP 200, no 402 or 504, **40 of 40 schema-valid**. Raw log: PC `outputs\bench-photo-20261029\calls.jsonl`, `context.json`, `summary.md`.

| Model | Photo | Valid | Latency s min / median / max | Completion tokens median | Reasoning tokens median | Candidates mean | Primary recall | Precision | False positives | Duplicates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nvidia/Nemotron-3.5-Super-VL | placed | 5/5 | 8.6 / 12.0 / 12.3 | 2989 | 2616 | 3.2 | 0.67 | 0.95 | 0.0 | 0.2 |
| nvidia/Nemotron-3.5-Super-VL | initial | 5/5 | 12.5 / 12.8 / 14.9 | 3843 | 3244 | 5.0 | 0.75 | 1.00 | 0.0 | 0.0 |
| deepseek-ai/DeepSeek-V4.1-Flash | placed | 5/5 | 10.1 / 10.9 / 12.3 | 1572 | 977 | 5.4 | 0.80 | 0.96 → 1.00* | 0.2 → 0.0* | 0.0 |
| deepseek-ai/DeepSeek-V4.1-Flash | initial | 5/5 | 11.9 / 12.9 / 18.0 | 2202 | 1488 | 5.8 | 0.70 | 0.87 | 0.0 | 0.8 |
| Qwen/Qwen3.8-27B | placed | 5/5 | 10.8 / 11.3 / 13.0 | 2926 | 2539 | 3.0 | 0.67 | 1.00 | 0.0 | 0.0 |
| Qwen/Qwen3.8-27B | initial | 5/5 | 14.8 / 14.9 / 16.2 | 4796 | 4197 | 6.0 | 0.75 | 1.00 | 0.0 | 0.0 |
| google/gemma-3-27b-it | placed | 5/5 | 12.6 / 14.2 / 15.3 | 488 | - | 5.2 | 0.60 | 0.38 | 3.0 | 0.2 |
| google/gemma-3-27b-it | initial | 5/5 | 9.0 / 12.5 / 19.4 | 512 | - | 5.4 | 0.00 | 0.12 | 4.8 | 0.0 |

\* First scoring pass, then after the manual review below added one real object to the ground truth (re-scored with `--score-only`).

Per-object detection, placed-object photo (of 5 valid calls per model; primary objects in bold):

| Model | **Box A** | **Bag C** | **Stool B** | Robot vacuum | Stick vacuum | Basket | Pots by window | White cable | Cable + charger by sofa | TV cable | Power strip | Purple roll* |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Nemotron-3.5-Super-VL | 5/5 | 5/5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 5/5 | 0/5 | 0/5 | 0/5 |
| DeepSeek-V4.1-Flash | 5/5 | 5/5 | 2/5 | 3/5 | 2/5 | 3/5 | 0/5 | 0/5 | 5/5 | 0/5 | 1/5 | 1/5 |
| Qwen3.8-27B | 5/5 | 5/5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 5/5 | 0/5 | 0/5 | 0/5 |
| gemma-3-27b-it | 5/5 | 0/5 | 4/5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 1/5 | 0/5 | 0/5 | 0/5 |

Per-object detection, initial photo:

| Model | **White cable** | **Cable + charger** | **Black bag** | **Yellow box** | Stick vacuum | Robot vacuum | Stool + pots | Pots + basket | TV cable | Power adapter | Air conditioner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Nemotron-3.5-Super-VL | 0/5 | 5/5 | 5/5 | 5/5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 5/5 | 5/5 |
| DeepSeek-V4.1-Flash | 1/5 | 3/5 | 5/5 | 5/5 | 5/5 | 0/5 | 0/5 | 0/5 | 1/5 | 0/5 | 5/5 |
| Qwen3.8-27B | 0/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 0/5 | 0/5 | 5/5 | 0/5 | 0/5 |
| gemma-3-27b-it | 0/5 | 0/5 | 0/5 | 0/5 | 2/5 | 0/5 | 0/5 | 1/5 | 0/5 | 0/5 | 0/5 |

**Manual review of every unmatched candidate** (the script lists them all):
- Nemotron VL: one duplicate, a second candidate ("small white device") on the charger beside the sofa.
- DeepSeek Flash: in 4 of 5 initial-photo trials a second candidate on the air conditioner ("white folding panel / screen", kind unknown), counted as a duplicate; one "purple floor mat" on the placed photo at [0.74, 0.12, 0.79, 0.18]. That one is real: a purple foam roll lies on the floor by the sofa arm in both photos and the ground truth had missed it. It was added as a secondary object for both photos (no other model proposed it), which turns that call's false positive into a hit.
- Gemma: 3–5 unmatched candidates per call. The labels are generic ("Bag", "Cable Bundle", "Floor Lamp", "Small Floor Fan") and the boxes are 0.10-wide cells that do not land on the objects (its "Black Bag" on the placed photo sits on empty floor 0.3 of the image height below the bag); there is no floor fan or floor lamp in the room. Valid JSON, wrong content.

## Reading the numbers

- **Nemotron 3.5 Super VL** (the app's observer) is deterministic at temperature 0 (the same candidates in all 5 trials on each photo), precise (no false positives) and incomplete: it never proposed the stool with plant pots on the placed photo, nor the white coiled cable on the initial photo. The stool miss is probably a prompt effect rather than a vision one: the context lists two scanned chairs and the instruction says not to propose a listed type unless the photo clearly shows more of it. Median 12.4 s and about 3,400 completion tokens per photo, 2,900 of them hidden reasoning (about USD 0.003 of output at list price).
- **DeepSeek V4.1 Flash** found the most objects: the stool in 2 of 5 trials, the robot vacuum, stick vacuum and basket in some, the purple roll once, at about half Nemotron's output tokens and similar latency. Its weakness is repetition: a second candidate on the air conditioner in 4 of 5 initial-photo trials, which costs one of the six slots.
- **Qwen 3.8 27B** matched Nemotron's recall with no false positives, used all six slots on the initial photo, and wrote the most tokens (median 3,900).
- **Gemma 3 27B** shows why schema validity is not quality: 10 of 10 valid answers, 0.12 and 0.38 precision. The app's validator cannot see a wrong box; only a ground truth can.
- **LiDAR and photo cover each other's blind spots.** In the Oct 28 runs the LiDAR found the box 4/4 and the stool 4/4 but the soft bag 0/4; the photo step (Nemotron VL) found the box 5/5 and the bag 5/5 but the stool 0/5. The twin needs both.
- **Decision.** Keep Nemotron 3.5 Super VL as the observer: it is as precise as any model here, repeatable, and keeps the pipeline on one open NVIDIA family. Say plainly that DeepSeek Flash is the more complete choice on these photos. A later change could tell the observer the scanned chairs' positions, so a stool next to the window is not mistaken for one of them.

## What this does not show

- One room, two photos, one operator's ground truth. The regions and the acceptable kinds are judgement calls; the per-candidate match table is published so they can be challenged.
- The photo step proposes image regions only; the app places each accepted object beside the named neighbour and the robot's LiDAR refines it. Recognition here says nothing about metric accuracy.
- Latency and tokens are single-call figures from one evening; Token Factory load varies.

## Reproduce

```
.venv\Scripts\python.exe scripts\benchmark_photo_observers.py --repo . --discover
.venv\Scripts\python.exe scripts\benchmark_photo_observers.py --repo . --context <app photo job request.json> ^
    --photos room-placed-20261028.jpg room-initial-20261028.jpg --models nvidia/Nemotron-3.5-Super-VL ^
    --harness <saved observer profile json> --trials 5 --out outputs\bench-photo-20261029
.venv\Scripts\python.exe scripts\benchmark_photo_observers.py --repo . --score-only outputs\bench-photo-20261029
```

The photos are the operator's own living room and are not in the repository.
