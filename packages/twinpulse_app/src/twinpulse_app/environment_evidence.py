# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Verify original local photos independently of preview transport/renderer."""
import hashlib


def verify_overlay_photos(root,environment):
    for overlay in environment.get('overlays',[]):
        evidence=overlay['evidence']
        if evidence['basis']!='photo_estimate':continue
        folder=root/'overlay-photos'/evidence['sha256'];path=folder/'source.image'
        if (any(p.is_symlink() for p in (path,folder,folder.parent,root)) or not path.is_file() or
                path.stat().st_size>5*1024*1024 or hashlib.sha256(path.read_bytes()).hexdigest()!=evidence['sha256']):
            raise ValueError('ENVIRONMENT_PHOTO_CHANGED_OR_MISSING')
