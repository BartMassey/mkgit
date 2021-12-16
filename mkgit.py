#!/usr/bin/python3
# Copyright © 2012 Bart Massey
# [This program is licensed under the "MIT License"]
# Please see the file COPYING in the source
# distribution of this software for license terms.

"""
Create a new upstream git repository. This is a Python
rewrite of a shell script loosely based on an earlier
script by Julian Kongslie.
"""

import argparse, re, subprocess, sys
from pathlib import Path

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
    "-F",
    "--fork",
    help="instead of a new repo, make a new upstream fork",
    action="store_true",
)
ap.add_argument(
    "--repo-link",
    help="directory on target site for symlinking repo",
)
ap.add_argument(
    "--list-sites",
    help="help on site options",
    action="store_true",
)
ap.add_argument(
    "site",
    help="site for new repo (--list-sites)",
    nargs="?",
)
ap.add_argument(
    "repo",
    help="name of repository (with or without .git)",
    nargs="?",
)
args = ap.parse_args()

# User home directory.
home = Path.home()
# User sites directory.
configpath = home / ".mkgit"
# Special sites.
gitlabhub = ["github", "gitlab"]

# Just list site possibilities and exit.
if args.list_sites:
    options = [s + "-<org>" for s in gitlabhub]
    for d in configpath.iterdir():
        if not re.search(".conf$", d.name):
            continue
        service = re.sub(".conf$", "", d.name)
        options.append(service)
    for s in options:
        print(s, file=sys.stderr)
    exit(0)

def fail(msg):
    """Print a failure message to stderr and exit with status 1."""
    print("mkgit:", msg, file=sys.stderr)
    exit(1)

def read_oneliner(path):
    """Return the string contents of a one-line file."""
    try:
        with open(path, "r") as f:
            result = f.read().strip()
            if len(result.splitlines()) > 1:
                fail(f"{path}: expected one line")
            return result
    except Exception as e:
        fail(f"error reading: {e}")

def git_command(*args):
    """Run a git command."""
    command = ["git", *args]
    status = subprocess.run(command, capture_output=True, text=True)
    if not status:
        fail(f"command failed: {' '.join(command)}")
    if status.returncode != 0:
        print(status.stderr, file=sys.stderr)
        fail(f"command failed: {' '.join(command)}")
    return status.stdout

# What kind of system the target is.
target_type = None
# Directory on target system to symlink repo to.
repo_link = None
# Prefix component of target URL.
url = None
# User or organization name on target.
org = None
# New repository name.
repo = None
if args.site:
    generic = re.match(f"({'|'.join(gitlabhub)})(-(.*))?$", args.site)
    if generic:
        target_type = generic[1]
        org = generic[3]
        url = f"ssh://git@{target_type}.com"
    elif re.match("ssh://", args.site):
        target_type = "url"
        url = args.site
    else:
        vars = [ "GITHOST", "PARENT", "REPOLINK" ]
        fields = dict()
        path = configpath / f"{args.site}.conf"
        try:
            config = open(path, "r")
        except Exception as e:
            fail(f"could not open config: {e}")
        for i, line in enumerate(config):
            try:
                var, val = line.strip().split('=')
            except:
                fail(f"{path}:{i+1}: bad format")
            if var not in vars:
                fail(f"{var}: unknown config variable")
            fields[var] = val
        config.close()
        if 'GITHOST' not in fields:
            fail(f"{path}: no GITHOST")
        urlbase = Path(fields['GITHOST'])
        if 'PARENT' in fields:
            urlbase = urlbase / fields['PARENT']
        target_type = "configed"
        url = f"ssh://git@{urlbase}"
        repo_link = fields['REPOLINK']
        if args.repo_link:
            repo_link = args.repo_link
elif args.fork:
    full_url = git_command("remote", "get-url", "origin").strip()
    m = re.match("(.*)/([^/]+)/([^/]+)/?$", full_url)
    url = m[1]
    org = m[2]
    repo = m[3]
    target_type = "fork"
else:
    target_type = "github"
    url = "ssh://git@github.com"

# Try to get a user/org name.
if not org:
    if target_type == "github":
        org = read_oneliner(home / ".githubuser")
    elif target_type == "gitlab":
        org = read_oneliner(home / ".gitlabuser-gitlab.com")

# Set up the repo name.
if args.repo:
    if repo:
        warn(f"overriding repo name {repo} with {args.repo}")
    repo = args.repo
if not repo:
    repo = Path.cwd().parent.name
if not re.search("\.git$", repo):
    repo += ".git"

# Now target_type, url, org, repo and repo_link should be
# valid, so the fun can commence.

# Find current and main branch names.
branches = git_command("branch").splitlines()
branches.sort()
branch = branches.pop()
assert branch.startswith("* "), "internal error: branch no star"
branch = branch[2:]
main_branch = None
if branch in ["main", "master"]:
    main_branch = branch
elif "  main" in branches:
    main_branch = "main"
elif "  master" in branches:
    main_branch = "master"
else:
    fail(f"cannot find main or master branch")

# Find an appropriate description for the target repo.
description = args.description
if target_type in gitlabhub and not description:
    description = git_command("log", "--pretty=%s", main_branch)
    description = description.splitlines()[-1]
