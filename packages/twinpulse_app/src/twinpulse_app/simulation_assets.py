# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Fixed existing local asset only; caller paths and network assets are forbidden."""
from hashlib import sha256
from pathlib import Path

from .runtime_paths import resource_root
ROOT = resource_root()
PUBLIC_ASSET_RELATIVE = 'assets/simulation/turtlebot3_burger/usd'


def asset_root(root):
    public = Path(root)/PUBLIC_ASSET_RELATIVE
    return public if public.is_dir() else Path(root)/'artifacts/robot-models/burger-isaac/usd/turtlebot3_burger_1'


ASSET_ROOT = asset_root(ROOT)

# Reviewed bundled bytes, not a digest learned from whatever files happen to
# be present at launch. Updating assets requires an explicit manifest review.
BURGER_MANIFEST = {
    'turtlebot3_burger.usda':'58af6e5f75f5cf96362f4abb175971dd555870add77c50a0baaa8028d2293b37',
    'payloads/base.usda':'750889ff799fbe55efe50af7a47e32c38d664ce50fb360aa1802d2daacfcb4f7',
    'payloads/robot.usda':'f384b6a2b53094a18e10b02b18f254f10c2c972a8b9cf8fcccbf2f0159f5ed36',
    'payloads/materials.usda':'2be307ad3d46d77b19c0bea7f229c66af8b35e3dcf7d00455f9ef44927b1328b',
    'payloads/instances.usda':'06798e126ee49d958c4201abdd8ef578eb9a6fc48eed7951c3171e005162aa55',
    'payloads/geometries.usd':'0bda8f94edce82b534d2d58013ecaf8b33d6854a99827fe6fccfbd84a47cf43d',
    'payloads/Physics/physx.usda':'218b0c0f2b82c3859d184c59b8fd36b2b8c28b633609df7325906e370307408a',
    'payloads/Physics/physics.usda':'8c1e6353f364638bd6e8d823351811a353ab5235588d395cf3f56f71c3482195',
    'payloads/Physics/mujoco.usda':'a613ea9405af764aac0b31758b7703e18f74708d238fd8ad158d81a86b65cd98',
}

PUBLIC_BURGER_MANIFEST = {
    'turtlebot3_burger.usda':'3b657533bd802d137c066728e4df1e7b225cd9d5c5738c34c178ed84b4cb1f69',
    'payloads/base.usda':'17767908c3bac46f453b00fe2c566f45f06e57e818b83315fc5e281b92888cf1',
    'payloads/robot.usda':'7de52ca7ad6471aed9fde8c6ef130436e7395dea1c2c3949aed7c952bbfdbbef',
    'payloads/materials.usda':'6d75e07acabbab8f417564dfe8713a62d8d87d2ae47a32bd41c82be70657bd12',
    'payloads/instances.usda':'c194290f05f7dfd9a9b90a8c0dacf2b436e3d4bd032106268d61a9497a20416b',
    'payloads/geometries.usd':'f9ccb9c2716a19289d6ef05e15e57e5c8dbcd1425049317ff462b29bed96d2c0',
    'payloads/Physics/physx.usda':'078530d6b2799caf6bdcb40deaff34092e6b5686b26f21a9bcbd9448eb4eace2',
    'payloads/Physics/physics.usda':'b4c6d8013f5fd7fcdddc4ff39ac769d5b13f976bee0813d8242aa28eb58f0acd',
    'payloads/Physics/mujoco.usda':'63c2a9a8834c470d1424cb4c0e406ccbb293584ee20d392a00bd3f2dded4d659',
}


def burger_inventory():
    return _inventory(ASSET_ROOT)


def _inventory(asset_root: Path):
    files = sorted(asset_root.rglob('*'))
    if not (asset_root/'turtlebot3_burger.usda').is_file():
        raise ValueError('SIM_BURGER_ASSET_MISSING')
    if asset_root.is_symlink() or any(p.is_symlink() or not p.resolve().is_relative_to(asset_root.resolve()) for p in files):
        raise ValueError('SIM_ASSET_DEPENDENCY_UNSAFE')
    expected = {'turtlebot3_burger.usda', 'payloads/base.usda', 'payloads/robot.usda',
                'payloads/materials.usda', 'payloads/instances.usda', 'payloads/geometries.usd',
                'payloads/Physics/physx.usda', 'payloads/Physics/physics.usda', 'payloads/Physics/mujoco.usda'}
    if {p.relative_to(asset_root).as_posix() for p in files if p.is_file()} != expected:
        raise ValueError('SIM_BURGER_DEPENDENCY_CLOSURE_CHANGED')
    if any(p.stat().st_size > 32*1024*1024 for p in files if p.is_file()):
        raise ValueError('SIM_BURGER_ASSET_SIZE_LIMIT')
    inventory = {p.relative_to(asset_root).as_posix(): sha256(p.read_bytes()).hexdigest()
                 for p in files if p.is_file()}
    if inventory not in (BURGER_MANIFEST, PUBLIC_BURGER_MANIFEST):
        raise ValueError('SIM_BURGER_ASSET_DIGEST_MISMATCH')
    return inventory
