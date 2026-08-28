#!/usr/bin/env python3
"""
dataShield.py — CLI entrypoint.

Routes three commands to whichever Engine matches the file's extension:
    inspect  <file>                     -> parse, print a Report
    repair   <file> --output <file>     -> parse, fix, write corrected file
    convert  <file> --to <format>       -> not implemented yet (Day 2)

Standard library only. No pip packages.
"""

import argparse
import sys

from engine import get_engine


def cmd_inspect(args):
    engine = get_engine(args.file)
    _, report = engine.parse(args.file)
    report.source = args.file
    report.print_report()
    return 1 if report.has_errors() else 0


def cmd_repair(args):
    engine = get_engine(args.file)
    report = engine.repair(args.file, args.output)
    report.source = args.file
    report.print_report()
    return 0


def cmd_convert(args):
    print(f"convert: not implemented yet ({args.file} -> {args.to})")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="dataShield",
        description="Inspect, repair, and convert messy data files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_inspect = subparsers.add_parser("inspect", help="Parse a file and report issues")
    p_inspect.add_argument("file", help="Path to the file to inspect")
    p_inspect.set_defaults(func=cmd_inspect)

    p_repair = subparsers.add_parser("repair", help="Parse a file, fix issues, write output")
    p_repair.add_argument("file", help="Path to the file to repair")
    p_repair.add_argument("--output", required=True, help="Path to write the repaired file")
    p_repair.set_defaults(func=cmd_repair)

    p_convert = subparsers.add_parser("convert", help="Convert a file to another format")
    p_convert.add_argument("file", help="Path to the input file")
    p_convert.add_argument("--to", required=True, help="Target format, e.g. sqlite, json, csv")
    p_convert.set_defaults(func=cmd_convert)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    exit_code = args.func(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
