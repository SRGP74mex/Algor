#!/usr/bin/env python3
"""Compara evidencia de guardado LCD offline; no abre dispositivos USB."""
import argparse
import hashlib
import json
from pathlib import Path
from analyze_lcd_capture import packets


def inspect(capture):
    stats = dict(packets=0, truncated_packets=0, short_payloads=0)
    pending = {}
    queries = []
    finalizers = []
    for timestamp, uid, event, transfer, ep, device, bus, status, size, data, setup in packets(capture, stats):
        if transfer != 2:
            continue
        if event == 'S' and setup[:2] == b'\xa1\x01':
            pending[uid] = int.from_bytes(setup[2:4], 'little')
        elif event == 'C' and uid in pending:
            report = pending.pop(uid)
            queries.append(dict(report=hex(report), status=status, data=data.hex()))
        elif event == 'S' and setup[:2] == b'\x21\x09' and data[:2] in (b'\x03\x1c', b'\x03\x1b'):
            finalizers.append(dict(command=data[:2].hex(), data=data.hex()))
    return dict(capture=str(capture), capture_sha256=hashlib.sha256(capture.read_bytes()).hexdigest(),
                queries=queries, finalizers=finalizers, statistics=stats)


def compare(captures):
    results = [inspect(path) for path in captures]
    matches = []
    for i, result in enumerate(results):
        for finalizer in result['finalizers']:
            if finalizer['command'] != '031c':
                continue
            candidate = bytes.fromhex(finalizer['data'])[2:6]
            for j, other in enumerate(results):
                for query in other['queries']:
                    if query['report'] == '0x30f' and query['status'] == 0:
                        response = bytes.fromhex(query['data'])
                        if len(response) >= 5 and response[1:5] == candidate:
                            matches.append(dict(finalizer_capture=i, query_capture=j, bytes=candidate.hex()))
    return dict(captures=results, matching_four_bytes=matches,
                interpretation='Byte equality only: neither token semantics nor safe replay is established.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures', type=Path, nargs='+')
    args = parser.parse_args()
    print(json.dumps(compare(args.captures), indent=2))
