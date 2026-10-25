# SPDX-License-Identifier: Apache-2.0
"""Original lossless-recorder PTS/DTS contract, before output-timebase conversion."""
def strictly_increasing_packet_times(packets):
    if not isinstance(packets, list) or len(packets)<2:
        return False
    for field in ('pts', 'dts'):
        values = [row.get(field) if isinstance(row,dict) else None for row in packets]
        if any(type(v) is not int for v in values) or any(b<=a for a,b in zip(values,values[1:])):
            return False
    return True
