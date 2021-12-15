#!/usr/bin/python3
# Copyright © 2012 Bart Massey
# [This program is licensed under the "MIT License"]
# Please see the file COPYING in the source
# distribution of this software for license terms.

# Create a new upstream git repository. This is a Python
# rewrite of a shell script loosely based on an earlier
# script by Julian Kongslie

import argparse, sys

# Process arguments.
ap = argparse.ArgumentParser()
ap.add_argument(
    "-p",
    "--private",
    help="make new repo private",
    action="store_true",
)
ap.add_argument(
    "-d",
    "--description",
    help="description line for new repo",
)
ap.add_argument(
    "-X",
    "--site",
    help="site for new repo (--help-sites)",
)
ap.add_argument(
    "--help-sites",
    help="help on site options",
    action="store_true",
)
ap.add_argument(
    "-F",
    "--fork",
    help="instead of a new repo, make a new upstream fork",
    action="store_true",
)
ap.add_argument(
    "repo-name",
    help="name of repository (with or without .git)",
    nargs="?",
)
args = ap.parse_args()

if args.help_sites:
    print("site options:", file=sys.stderr)
    options = [
        "github[-<org>]",
        "gitlab[-<org>]",
    ]
    for s in options:
        print("    " + s, file=sys.stderr)
    exit(0)

