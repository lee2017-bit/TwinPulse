"""Run the three M2-C images through the saved OpenAI Responses credential once each.

The script never prints or serializes the API key. It writes only validated scene
tool plans, compiled TwinPulse bundles, provenance, and sanitized failures.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = REPO_ROOT / "packages" / "twinpulse_core" / "src"
PROVIDER_SRC = REPO_ROOT / "packages" / "twinpulse_provider" / "src"
for source in (CORE_SRC, PROVIDER_SRC):
    sys.path.insert(0, str(source))

from twinpulse_core import bundle_to_json  # noqa: E402
from twinpulse_provider import (  # noqa: E402
    GenerationRequest,
    GenerationService,
    ImageInput,
    OpenAIResponsesProvider,
    ProviderCapabilities,
    ProviderConfig,
)


def _load_saved_api_key() -> str | None:
    module_path = (
        REPO_ROOT
        / "extensions"
        / "twinpulse.extension"
        / "twinpulse"
        / "extension"
        / "credential_store.py"
    )
    spec = importlib.util.spec_from_file_location("twinpulse_credential_store", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("credential store module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.WindowsCredentialStore().load()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sanitized_error(error: Exception) -> dict[str, str]:
    detail = " ".join(str(error).split()) or type(error).__name__
    return {"type": type(error).__name__, "message": detail[:500]}


async def _run(args: argparse.Namespace) -> int:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    key = _load_saved_api_key()
    if not key:
        raise RuntimeError("TwinPulse API key is not present in Windows Credential Manager")
    print("credential_status=SAVED_KEY_PRESENT")

    config = ProviderConfig(
        base_url="https://api.openai.com/v1/",
        endpoint_path="responses",
        model_id=args.model,
        api_key_env="OPENAI_API_KEY",
        capabilities=ProviderCapabilities(
            supports_images=True,
            supports_structured_output=True,
            max_images=1,
            accepted_mime_types=("image/jpeg", "image/png", "image/webp"),
        ),
        timeout_s=args.timeout,
        max_attempts=1,
    )
    service = GenerationService(
        OpenAIResponsesProvider(lambda: key, reasoning_effort=args.reasoning_effort),
        config,
    )
    report: dict[str, object] = {
        "schema_version": "1.0",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "OpenAI Responses",
        "model_id": args.model,
        "reasoning_effort": args.reasoning_effort,
        "automatic_retries": 0,
        "fixtures": [],
    }
    passed = 0
    for index, fixture in enumerate(manifest["fixtures"], start=1):
        fixture_id = str(fixture["id"])
        image_path = args.image_dir / str(fixture["local_filename"])
        item: dict[str, object] = {
            "fixture_id": fixture_id,
            "source_page": fixture["source_page"],
            "license": fixture["license"],
            "author": fixture["author"],
            "image_filename": image_path.name,
            "image_sha256": _sha256(image_path),
            "prompt": fixture["prompt"],
            "provider_attempts": 1,
        }
        if item["image_sha256"] != fixture["sha256"]:
            item.update({"status": "FAIL", "error": {"type": "HashMismatch", "message": "fixture SHA-256 mismatch"}})
            report["fixtures"].append(item)
            print(f"fixture={index}/3 id={fixture_id} status=FAIL reason=HashMismatch", flush=True)
            continue
        request_id = str(uuid.uuid4())
        print(f"fixture={index}/3 id={fixture_id} status=REQUESTING", flush=True)
        try:
            result = await service.generate(
                GenerationRequest(
                    request_id=request_id,
                    prompt=str(fixture["prompt"]),
                    images=(ImageInput(image_path.name, "image/jpeg", image_path.read_bytes()),),
                )
            )
            item.update(
                {
                    "status": "PASS",
                    "request_id": result.request_id,
                    "scene_id": result.plan.scene_id,
                    "image_observations": result.plan.image_observations,
                    "summary": result.plan.summary,
                    "tool_call_count": len(result.plan.calls),
                    "expanded_object_count": len(result.bundle.scene.objects),
                    "tool_names": [call.tool for call in result.plan.calls],
                    "plan": result.plan.to_dict(),
                    "bundle": json.loads(bundle_to_json(result.bundle)),
                }
            )
            passed += 1
            print(
                f"fixture={index}/3 id={fixture_id} status=PASS "
                f"scene={result.plan.scene_id} tools={len(result.plan.calls)} "
                f"objects={len(result.bundle.scene.objects)}",
                flush=True,
            )
        except Exception as error:  # one paid attempt; preserve failure without retry
            item.update({"status": "FAIL", "request_id": request_id, "error": _sanitized_error(error)})
            print(f"fixture={index}/3 id={fixture_id} status=FAIL reason={type(error).__name__}", flush=True)
        report["fixtures"].append(item)

    report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["passed_fixtures"] = passed
    report["failed_fixtures"] = len(manifest["fixtures"]) - passed
    report["status"] = "PASS" if passed == len(manifest["fixtures"]) else "FAIL"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report={args.output}")
    print(f"status={report['status']} passed={passed}/{len(manifest['fixtures'])}")
    return 0 if report["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "fixtures" / "m2c" / "warehouse_images.json",
    )
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high"), default="low")
    parser.add_argument("--timeout", type=float, default=120.0)
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
