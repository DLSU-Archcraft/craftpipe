"""Command line interface: craftpipe convert / inspect."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import convert, mapper, output_paths, to_minecraft
from .errors import CraftpipeError, UnmappedBlocksError
from .reader import read_schematic

EXIT_OK, EXIT_UNMAPPED, EXIT_ERROR = 0, 1, 2


def _print_unmapped(report: mapper.Report, out, target: str = "Mineclonia") -> None:
    total = sum(e.count for e in report.unmapped.values())
    print(f"{total} block(s) in {len(report.unmapped)} state(s) have no {target} mapping:", file=out)
    for state, entry in sorted(report.unmapped.items(), key=lambda kv: -kv[1].count):
        where = ", ".join(f"({x},{y},{z})" for x, y, z in entry.positions)
        more = " ..." if entry.count > len(entry.positions) else ""
        reason = f"  [{entry.reason}]" if entry.reason else ""
        print(f"  {entry.count:>6} x {state}{reason}\n           at {where}{more}", file=out)


def _print_warnings(report: mapper.Report, out) -> None:
    for message in report.warnings:
        print(f"warning: {message}", file=out)


def _write_report(path, report: mapper.Report) -> None:
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report.to_json(), fh, indent=1)
            fh.write("\n")


def cmd_convert(args) -> int:
    try:
        conv = convert(args.input, args.output, allow_unmapped=args.allow_unmapped)
    except UnmappedBlocksError as exc:
        _write_report(args.report, exc.report)
        _print_unmapped(exc.report, sys.stderr)
        print("Nothing was written. Add the missing rows to the mapping table, or pass "
              "--allow-unmapped to convert anyway with placeholders (not gradeable).",
              file=sys.stderr)
        return EXIT_UNMAPPED
    _write_report(args.report, conv.report)
    mts_path, manifest_path = output_paths(args.input, args.output)
    sx, sy, sz = conv.size
    placed = sum(conv.report.counts.values())
    print(f"{mts_path}: {sx} x {sy} x {sz}, {placed} nodes, "
          f"{len(conv.manifest['containers'])} container(s)")
    print(f"{manifest_path}: manifest")
    _print_warnings(conv.report, sys.stderr)
    if conv.report.unmapped:
        _print_unmapped(conv.report, sys.stderr)
        print(f"WARNING: not gradeable. Unmapped blocks were replaced with {mapper.PLACEHOLDER}; "
              "the circuit may behave differently from the original.", file=sys.stderr)
    return EXIT_OK


def cmd_inspect(args) -> int:
    grid = read_schematic(args.input)
    sx, sy, sz = grid.size
    print(f"size: {sx} x {sy} x {sz}  (x, y, z)")
    print(f"block entities: {len(grid.block_entities)}")
    by_name: dict[str, int] = {}
    for state, count in grid.counts().items():
        by_name[state.name] = by_name.get(state.name, 0) + count
    print("blocks:")
    for name, count in sorted(by_name.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {count:>8}  {name}")
    try:
        conv = mapper.map_grid(grid, allow_unmapped=True)
    except CraftpipeError:
        raise
    _print_warnings(conv.report, sys.stdout)
    if conv.report.unmapped:
        _print_unmapped(conv.report, sys.stdout)
        return EXIT_UNMAPPED
    print("every block has a Mineclonia mapping")
    return EXIT_OK


def cmd_to_minecraft(args) -> int:
    output = args.output or os.path.splitext(args.input)[0] + ".litematic"
    try:
        report = to_minecraft(args.input, output, allow_unmapped=args.allow_unmapped)
    except UnmappedBlocksError as exc:
        _write_report(args.report, exc.report)
        _print_unmapped(exc.report, sys.stderr, "Minecraft")
        print("Nothing was written. These Mineclonia nodes are not supported; pass "
              "--allow-unmapped to convert anyway with bedrock in their place.", file=sys.stderr)
        return EXIT_UNMAPPED
    _write_report(args.report, report)
    print(f"{output}: {sum(report.counts.values())} blocks, Minecraft Java 1.21.1")
    _print_warnings(report, sys.stderr)
    if report.unmapped:
        _print_unmapped(report, sys.stderr, "Minecraft")
        print("WARNING: unsupported nodes were replaced with bedrock; the circuit may behave "
              "differently from the original.", file=sys.stderr)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="craftpipe",
        description="Convert Minecraft redstone schematics (.litematic, .schem) to Mineclonia .mts")
    sub = parser.add_subparsers(dest="command", required=True)
    conv = sub.add_parser("convert", help="write a .mts schematic and its manifest")
    conv.add_argument("input")
    conv.add_argument("-o", "--output", help="output .mts path (default: next to the input)")
    conv.add_argument("--allow-unmapped", action="store_true",
                      help="replace unmapped blocks with a placeholder instead of failing")
    conv.add_argument("--report", metavar="FILE.json", help="write the conversion report as JSON")
    conv.set_defaults(func=cmd_convert)
    insp = sub.add_parser("inspect", help="show size, block counts and what would be unmapped")
    insp.add_argument("input")
    insp.set_defaults(func=cmd_inspect)
    back = sub.add_parser("to-minecraft",
                          help="convert a Mineclonia .mts (exported with /craftpipe_export) to Minecraft")
    back.add_argument("input")
    back.add_argument("-o", "--output", help="output .litematic or .schem (default: .litematic next to the input)")
    back.add_argument("--allow-unmapped", action="store_true",
                      help="replace unsupported nodes with bedrock instead of failing")
    back.add_argument("--report", metavar="FILE.json", help="write the conversion report as JSON")
    back.set_defaults(func=cmd_to_minecraft)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CraftpipeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
