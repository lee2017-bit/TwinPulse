# DP0 source prepare through the existing App route — 2026-09-30

Robot OFF. The declared `source_prepare` operation was compared with the existing authenticated `POST /v1/product/robot/physical/start` path using `mode=prepare`. The DP0 manifest now names that route, its explicit confirmation/fresh expiry, the saved result, and a matching HTTP integration test. This was a connection of the existing product path, not a new way to deploy or bypass its operator confirmation.

The HTTP fixture rejects unauthenticated and missing-CSRF requests. With an explicit confirmed prepare request, a finished fake owned child returns `PREPARED`, `physical_verified=false`, selects only `prepare`, and receives no motion input. It does not invoke `prepare_robot.py` or contact the robot. The existing offline bundle test separately checks reproducible source packaging and excludes keys; neither fixture proves a real target transfer, install, board state or release identity.

Focused HTTP 1/1 PASS. Related contract/physical-controller/robot-preparation/offline-operation Python regression **94/94 PASS**; after clarifying that source transfer requires an explicit prepare request, contract-only **6/6 PASS**. The audit reports this operation with no product or integration mapping reason. Overall counts moved from product 7→6 and integration 7→6 unmapped; physical 14 remains. `pc_demo_ready=false`, and the audit still exits nonzero. Existing stop failures and live mission lock are unchanged.

Next DP0/DP1 work must connect the remaining six product/integration paths and preserve the difference between script source preparation, actual source transfer and hardware validation. This increment does not authorize running prepare on a robot.
