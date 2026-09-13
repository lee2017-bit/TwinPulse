# TwinPulse Product / Implementation Specification v1.2

> **Working title:** TwinPulse  
> **Positioning:** An installable Physical AI playground for NVIDIA Isaac Sim  
> **Core promise:** Make it easy to build, calibrate, optimize, and run robot simulations with natural language and images, then connect the same workflow to a real AGV when available.

---

## 1. Product Goal

TwinPulse is not a new simulator. It is an **easy-to-use product layer on top of NVIDIA Isaac Sim / Isaac Lab**.

The intended product experience is:

1. Install/enable TwinPulse as an Isaac Sim Extension.
2. Optionally select or bind a robot.
3. Describe a simulation environment in natural language and/or attach an image.
4. TwinPulse creates an **executable simulation scenario**, not just static geometry.
5. If a physical AGV is connected, perform a calibration run to align the approximate simulated scene with reality.
6. Set start / waypoint(s) / goal and optimization criteria.
7. Run simulation / optimization using Isaac Lab, preferably using Nebius GPU infrastructure for the hackathon path.
8. Apply the optimized mission / route / parameters to the real AGV through ROS2.
9. Stream real AGV telemetry back to TwinPulse so Isaac Sim stays synchronized with reality.

### Product tagline candidates

- **Build. Optimize. Deploy.**
- **From natural language to Physical AI.**
- **Build a robot simulation without becoming a simulation expert.**

---

## 2. Product Principles

### 2.1 Easy before powerful

The user should not need to understand USD hierarchy, Isaac Sim property panels, physics material configuration, ROS2 topic wiring, or Isaac Lab reward config files to create a useful first simulation.

### 2.2 Human-readable and inspectable

AI-generated results should expose structured intermediate representations such as:

- `SceneSpec`
- `RobotProfile`
- `TaskSpec`
- `OptimizationSpec`
- `CalibrationResult`

### 2.3 LLM-provider independent

TwinPulse must not hard-code one LLM vendor.

```text
LLMProvider
├── Nebius / NVIDIA Nemotron
├── Enterprise provider (A.dot Biz)
├── OpenAI-compatible provider
└── Future providers
```

### 2.4 Physical robot is optional

TwinPulse must support:

- simulation-only mode
- simulation + physical robot mode

---

## 3. High-Level User Flow

```text
0. SETUP (Optional)
   ├── Bind Physical Robot
   ├── Select Existing Asset
   └── Skip
          ↓
1. BUILD
   Text + Image
          ↓
   Executable Simulation Scenario
          ↓
2. CALIBRATE (Physical robot only)
          ↓
3. OPTIMIZE
   Start + Waypoint(s) + Goal
   + scoring / reward criteria
          ↓
4. DEPLOY & RUN
          ↓
   Physical Robot (optional)
          ↓
   Live Telemetry
          ↓
   Isaac Sim Digital Twin
```

---

## 4. Step 0 — SETUP (Optional Robot Setup)

SETUP is **not mandatory**.

### Option A — Bind a Physical AGV

Register an actual physical AGV.

Example profile:

```yaml
robot_id: MiniAGV_01
drive_type: differential
dimensions:
  width_m: 0.21
  length_m: 0.27
wheelbase_m: 0.18
max_speed_mps: 0.5

sensors:
  wheel_encoder: true
  front_range: true
  left_range: true
  right_range: true

ros2:
  cmd_vel: /cmd_vel
  odom: /odom
  front_range: /range/front
  left_range: /range/left
  right_range: /range/right
```

### Option B — Select an Existing Robot Asset

Use an Isaac Sim/NVIDIA asset, TwinPulse asset, or user asset. Drag-and-drop should be supported where practical.

### Option C — Skip

Proceed without choosing a robot. During BUILD the user may request one naturally:

> “Create a small AGV at the entrance and make it patrol between A and B.”

Natural-language robot creation should map to **supported parameterized templates**, not arbitrary LLM-invented physics.

---

## 5. Step 1 — BUILD

### 5.1 MVP inputs

- **Text**
- **Image**

PDF and video are future extensions.

### 5.2 User experience

Example:

> “Make a warehouse similar to this image. Put three racks on the left, leave a 1.2 m center aisle, and place an AGV near the entrance. Make the AGV patrol between Station A and Station B.”

### 5.3 Output

BUILD must create an **executable simulation scenario**, including:

- environment geometry
- semantic objects
- robot(s)
- spawn position
- named stations/zones
- robot task/behavior
- simulation configuration

Example:

```json
{
  "environment": {
    "type": "warehouse",
    "width_m": 8.0,
    "length_m": 5.0
  },
  "objects": [
    {
      "id": "rack_01",
      "type": "rack",
      "position": [1.2, 2.0, 0.0],
      "size": [1.0, 0.5, 2.0]
    }
  ],
  "robots": [
    {
      "id": "AGV_01",
      "profile": "generic_diff_agv",
      "spawn": [1.0, 1.5, 0.0]
    }
  ],
  "tasks": [
    {
      "robot": "AGV_01",
      "type": "patrol",
      "start": "Station_A",
      "goal": "Station_B"
    }
  ]
}
```

### 5.4 Accuracy target

The target is **AI-assisted simulation-ready scene generation**, not photorealistic reconstruction.

---

## 6. Step 2 — CALIBRATE

Calibration exists **only when a physical robot is bound**.

### 6.1 Why

Text and images alone cannot reliably recover true metric scale, exact obstacle positions, real robot initial pose, or motion mismatch.

> **AI creates the first approximation. The robot aligns the simulation with reality.**

### 6.2 Flow

```text
Approximate BUILD scene
        ↓
Connect physical AGV
        ↓
Calibration Run
        ↓
Measure real environment
        ↓
Estimate mismatch
        ↓
Correct scene scale / obstacle distance / robot pose
```

### 6.3 MVP sensors

- wheel encoder / odometry
- low-cost distance sensors

This is not full SLAM. The first claim is limited to simple planar environments.

Future plugins may support LiDAR, camera, depth camera, Visual SLAM, AprilTag, etc.

---

## 7. Step 3 — OPTIMIZE

### 7.1 User inputs

- Start
- Waypoint(s)
- Goal
- optimization/scoring criteria

Input via scene clicks, natural language, or both.

### 7.2 Scoring example

```text
Safety       50%
Travel Time  30%
Distance     20%

Minimum Clearance: 0.5 m
```

### 7.3 Isaac Lab role

```text
TwinPulse UI
      ↓
OptimizationSpec
      ↓
Observation / Action / Reward / Termination
      ↓
Isaac Lab
      ↓
Training / Policy Evaluation
```

For MVP, use one supported algorithm such as PPO.

### 7.4 Real-world deployment target

Initial architecture:

```text
Simulation optimization
        ↓
Best route / waypoints / navigation parameters
        ↓
ROS2 navigation logic
        ↓
Physical AGV
```

This is closer to **RL-assisted / simulation-assisted route optimization** than direct neural motor control.

---

## 8. Step 4 — DEPLOY & RUN

### 8.1 Mission deployment

```text
Best Route / Mission / Parameters
             ↓
ROS2 navigation layer
             ↓
Move robot to initial pose
             ↓
Execute optimized mission
```

### 8.2 Real-to-Sim telemetry

Minimum telemetry from physical AGV to TwinPulse/Isaac Sim:

**Pose / Odometry**
- x
- y
- yaw

**Wheel / motor state**
- left/right wheel velocity, or encoder counts

**Distance sensors**
- front
- left
- right

**System**
- timestamp
- heartbeat

Possible ROS2 topics:

```text
/odom
/joint_states
/range/front
/range/left
/range/right
```

### 8.3 Communication philosophy

**AGV → TwinPulse:** continuous telemetry required.  
**TwinPulse → AGV:** mission/waypoints/navigation params/start-stop; avoid continuous cloud motor control.

---

## 9. TwinPulse Extension Architecture

TwinPulse should be an **installable Isaac Sim Extension**, not a one-off hackathon script.

Suggested responsibilities:

```text
TwinPulse/
├── extensions/
│   └── twinpulse.extension/
│       ├── UI
│       ├── scene builder
│       ├── robot setup
│       ├── calibration controls
│       ├── optimization controls
│       └── telemetry visualization
│
├── twinpulse_core/
│   ├── schemas/
│   │   ├── scene_spec.py
│   │   ├── robot_profile.py
│   │   ├── task_spec.py
│   │   ├── optimization_spec.py
│   │   └── calibration_result.py
│   │
│   ├── llm/
│   │   ├── provider.py
│   │   ├── nemotron_provider.py
│   │   └── enterprise_provider.py
│   │
│   ├── isaac/
│   ├── ros2/
│   └── optimization/
│
├── cloud/
│   └── nebius/
├── tests/
└── docs/
```

---

## 10. LLM Architecture

### 10.1 Provider abstraction

Example conceptual interface:

```python
class LLMProvider:
    def generate_scene_spec(self, text, images):
        ...

    def interpret_simulation_command(self, command, scene_state):
        ...

    def generate_task_spec(self, request, scene_state):
        ...
```

Implementations should include Nebius/Nemotron and the future A.dot Biz provider.

### 10.2 Hackathon role of Nemotron

Preferred role:

```text
Natural language / image-derived information
               ↓
        NVIDIA / Nemotron
               ↓
Structured SceneSpec / TaskSpec / tool plan
               ↓
Deterministic TwinPulse execution layer
```

The LLM should not generate arbitrary Isaac Sim Python when deterministic tools/APIs exist.

### 10.3 Enterprise environment

Known so far:

- internal enterprise **A.dot Biz** LLM service
- custom Base URL
- API key
- custom model name
- not the public OpenAI endpoint

Pending company details:

- Base URL/API format
- OpenAI compatibility
- model name(s)
- auth headers
- OS/GPU
- Isaac Sim version
- Docker
- pip/apt restrictions
- ROS2 availability
- network restrictions
- whether the Isaac Sim workstation can reach A.dot Biz
- whether Nebius can be accessed from company network

**Never commit API keys. Use environment variables or secret storage.**

---

## 11. NVIDIA / Nebius Scope

### MVP/core
- NVIDIA Isaac Sim
- NVIDIA Isaac Lab
- ROS2 integration
- Nebius Token Factory and/or Nebius AI Cloud
- NVIDIA open model path, initially Nemotron
- TwinPulse Isaac Sim Extension

### Excluded from initial submission
- **GR00T**

### Future
- Cosmos
- richer sensor simulation
- PDF/video input
- multi-robot fleet optimization
- manipulation / GR00T

---

## 12. Hackathon Constraints Already Known

From official Devpost/Nebius hackathon email communications:

1. Project must run on **Nebius Token Factory or Nebius AI Cloud**.
2. Project must use at least one **NVIDIA open-source model**.
3. Physical AI stands out more when **hardware reacts live to real-world input**, rather than only a scripted demo.
4. Baseline/theme-fit pass/fail comes first, then submissions are scored 1–5 on four equally weighted criteria:
   - Technological Implementation
   - Design
   - Potential Impact
   - Quality of the Idea

---

## 13. Nebius Credits / Quotas

### Confirmed Token Factory promo

Hackathon activation code:

```text
NEBIUS-DEVPOST-GLOBAL26
```

Official hackathon email says:

- **$25 Token Factory credit** using this activation code
- **another $25 Token Factory credit** by joining the Nebius Builders Program

### Tavily

Promo code from the Devpost build-session email:

```text
BBDEVPOST
```

### AI Cloud

**Free AI Cloud credit amount is not yet confirmed.**

Nebius welcome email confirms **default quota**, not free spend:

- up to **8 × NVIDIA H200**
- up to **16 × NVIDIA H100**
- up to **2 × NVIDIA L40S**

The same email says billing setup requires a **minimum $25 payment**, deposited to the account.

Therefore:

> **GPU quota != free AI Cloud credit**

Open question:

- Was extra AI Cloud/GPU promo credit provided at the Seoul Builders & Brews meetup?
- If yes: amount, activation method, expiry, eligible services/GPU types.

---

## 14. Minimum Physical Robot Requirements

Initial low-cost demo robot:

- differential drive
- wheel encoders
- ESP32-class controller acceptable
- Wi-Fi
- ROS2/micro-ROS bridge or equivalent
- front/left/right distance sensing
- enough deck space for a small object

Not required initially:

- Jetson
- Raspberry Pi
- LiDAR
- onboard camera
- automatic loading/unloading
- industrial payload rating

---

## 15. MVP Acceptance Criteria

1. Isaac Sim 6.0.1 starts.
2. TwinPulse Extension can be enabled.
3. User may bind/select a robot or skip.
4. User enters text and optionally an image.
5. TwinPulse generates a validated `SceneSpec`.
6. TwinPulse builds an executable Isaac Sim scene.
7. Simulated AGV executes a generated task.
8. User selects Start / Waypoint / Goal.
9. User sets optimization weights.
10. Isaac Lab optimization/training starts.
11. Best result is returned and visualized.
12. With a physical AGV:
    - telemetry is received
    - calibration can run
    - optimized mission can be sent via ROS2
    - real robot motion is reflected in Isaac Sim

---

## 16. Development Priority

### Milestone 1 — Extension Skeleton
TwinPulse Extension loads in Isaac Sim 6.0.1.

### Milestone 2 — Natural Language → SceneSpec
Provider abstraction, strong model first, Nebius/Nemotron path verified.

### Milestone 3 — SceneSpec → Isaac Sim
Floor/walls/racks/obstacles/stations/robot template/task.

### Milestone 4 — Image + Text BUILD
Image context + approximate semantic geometry + review/edit.

### Milestone 5 — Optimization UI
Start / Waypoint / Goal + scoring criteria.

### Milestone 6 — Isaac Lab
One AGV, one simple environment, one algorithm, measurable improvement.

### Milestone 7 — Physical Robot Bridge
ROS2 connection, odometry, range sensors, Sim sync.

### Milestone 8 — Calibration
Simple planar environment with encoder + range correction.

### Milestone 9 — Deploy
Optimized mission → ROS2 → real robot → live telemetry.

### Milestone 10 — Hackathon Packaging
Public repo, README, license, demo video, Devpost submission.

---

## 17. Explicit Non-Goals for Initial Version

- perfect 3D reconstruction
- PDF/CAD ingestion
- video reconstruction
- full SLAM
- fleet optimization
- multi-AGV traffic
- automatic loading/unloading
- GR00T
- robot-arm manipulation
- end-to-end vision-to-motor policy
- industrial safety certification
- photorealistic asset generation

---

## 18. Open Questions

### Nebius
- [ ] AI Cloud promo credit amount
- [ ] activation method
- [ ] expiry
- [ ] eligible GPU types
- [ ] preferred Isaac Lab cloud execution path
- [ ] spend limit vs GPU quota

### Physical AGV
- [ ] exact chassis
- [ ] encoder protocol
- [ ] distance sensor model
- [ ] micro-ROS vs custom bridge
- [ ] initial localization method
- [ ] test-area size

### Company environment
- [ ] A.dot Biz Base URL format
- [ ] API compatibility
- [ ] model name
- [ ] authentication
- [ ] OS/GPU
- [ ] Isaac Sim version
- [ ] Docker
- [ ] ROS2
- [ ] package-install restrictions
- [ ] network restrictions

### Product UX
- [ ] exact Extension panel layout
- [ ] asset-browser integration
- [ ] scene review/edit UX
- [ ] calibration visualization
- [ ] optimization result comparison

---

## 19. Guidance for Codex

1. Treat this file as the product requirement source of truth.
2. Do not silently change product scope.
3. Before coding, inspect the local Isaac Sim 6.0.1 environment and identify supported extension APIs.
4. Prefer official Isaac Sim / Isaac Lab / Nebius APIs over GUI automation.
5. Keep LLM, Isaac, ROS2, cloud, and UI layers separate.
6. Never commit secrets.
7. Every milestone needs an executable acceptance test.
8. Prefer a small working vertical slice over broad unfinished functionality.
9. Report assumptions when version/API details are uncertain.
10. Do not add GR00T unless explicitly requested.

---

## 20. Suggested First Codex Prompt

> Read `TWINPULSE_PRODUCT_SPEC_v1_2.md` completely.  
> Do not implement the whole product yet.  
> First inspect this Windows machine and the installed Isaac Sim 6.0.1 environment, identify the officially supported extension-development workflow and Python/API paths, then propose:
>
> 1. repository structure,
> 2. extension skeleton,
> 3. dependency strategy,
> 4. milestone-by-milestone implementation plan,
> 5. automated acceptance tests,
> 6. known risks around Isaac Sim 6.0.1, Isaac Lab, ROS2, and Nebius.
>
> Keep the architecture compatible with both Nebius/Nemotron and a future enterprise A.dot Biz LLM endpoint.  
> Do not modify system-wide dependencies or install packages until the plan is reviewed.
