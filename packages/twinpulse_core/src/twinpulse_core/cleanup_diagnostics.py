# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded safe cleanup diagnoses attached to the unchanged primary exception."""
import re


def retain_cleanup(primary, stage, failure):
    code=str(failure)
    if not re.fullmatch('[A-Z0-9_]{1,120}',code):code='NATIVE_CLEANUP_FAILED'
    notes=list(getattr(primary,'mission_cleanup_errors',()))[:7]
    notes.append({'stage':stage,'code':code,'error_type':type(failure).__name__[:80]})
    primary.mission_cleanup_errors=notes


def checked_notes(value):
    if type(value) is not list or len(value)>8:return []
    stages={'navigation_halt','mission_halt','mission_close','mission_final_record','goal_watch_join'}
    return [dict(row) for row in value if type(row) is dict and set(row)=={'stage','code','error_type'}
            and type(row['stage']) is str and row['stage'] in stages and type(row['code']) is str
            and re.fullmatch('[A-Z0-9_]{1,120}',row['code'])
            and type(row['error_type']) is str and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,79}',row['error_type'])]
