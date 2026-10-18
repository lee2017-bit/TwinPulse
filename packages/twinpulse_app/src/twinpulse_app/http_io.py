# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local HTTP body deadlines, separate from engine/model work time."""
import time


def _with_deadline(request, timeout_s, operation):
    connection=getattr(request,'connection',None)
    previous=connection.gettimeout() if connection is not None else None
    deadline=time.monotonic()+timeout_s
    def remaining():
        left=deadline-time.monotonic()
        if left<=0:raise TimeoutError('Local HTTP body deadline exceeded')
        if connection is not None:connection.settimeout(min(left,previous) if previous else left)
    try:return operation(remaining)
    finally:
        if connection is not None:
            try:connection.settimeout(previous)
            except OSError:pass


def read_body(request,length,timeout_s):
    def operation(remaining):
        parts=[];left=length
        # read1 returns available bytes; read(length) can internally retry a
        # dribbling client forever without returning to the wall-clock check.
        read=getattr(request.rfile,'read1',request.rfile.read)
        while left:
            remaining();part=read(min(65536,left))
            if not part:break
            parts.append(part);left-=len(part)
        return b''.join(parts)
    return _with_deadline(request,timeout_s,operation)


def write_body(request,payload,timeout_s):
    def operation(remaining):
        for start in range(0,len(payload),65536):
            remaining();request.wfile.write(payload[start:start+65536])
    return _with_deadline(request,timeout_s,operation)
