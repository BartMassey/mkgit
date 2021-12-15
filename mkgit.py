#!/usr/bin/python3
# Copyright © 2012 Bart Massey
# [This program is licensed under the "MIT License"]
# Please see the file COPYING in the source
# distribution of this software for license terms.

# Create a new upstream git repository. A Python rewrite of
# a shell script loosely based on an earlier script by
# Julian Kongslie

import argparse

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
    "repo_name",
    help="name of repository (with or without .git)",
    nargs="?",
)
args = ap.parse_args()

if args.repo_name:
    print(args.repo_name)
