# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Honest product identity for outbound provider HTTP.

The User-Agent names only the product and release: no user, machine or browser
identity, and never an attempt to look like another client. A network filter
that still blocks it is reported by the typed provider errors (its page title).
"""
import os
import re


def user_agent() -> str:
    version = os.environ.get('TWINPULSE_RELEASE_VERSION', '')
    return 'TwinPulse/' + (version if re.fullmatch(r'[0-9A-Za-z.+-]{1,40}', version) else 'dev')


def json_headers() -> dict[str, str]:
    """Default request headers; callers add Authorization/Content-Type and never log headers."""
    return {'User-Agent': user_agent(), 'Accept': 'application/json'}
