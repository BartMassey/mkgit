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

import argparse, base64, getpass, json, re, subprocess, sys
import http.client as client
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
    options = [s + "[.<domain>][-<org>]" for s in gitlabhub]
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

def git_command(*args, verbose=True):
    """Run a git command."""
    command = ["git", *args]
    status = subprocess.run(command, capture_output=True, text=True)
    if not status:
        fail(f"command failed: git {' '.join(command)}")
    if status.returncode != 0 and verbose:
        print(status.stderr, file=sys.stderr)
    return status.returncode, status.stdout

connection = None

def connect(site):
    global connection
    if connection:
        return
    try:
        connection = client.HTTPSConnection(site)
    except client.HTTPException as e:
        fail(f"http connection error: {e.code}")

def curl(ctype, path, headers, body):
    # XXX Required by GitHub v3 API. Ugh. May as well use everywhere.
    headers["User-Agent"] = "mkgit"
    # Required by Gitlab v4 API. May as well use everywhere.
    headers["Content-Type"] = "application/json"
    body = json.dumps(body)
    try:
        connection.request(ctype, path, body=body, headers=headers)
        response = connection.getresponse()
    except client.HTTPException as e:
        fail(f"http connection failed: {e.code}")
    if response.status == 201:
        try:
            return None, json.load(response)
        except json.decoder.JSONDecodeError as e:
            fail(f"curl json error: {e}")
    else:
        if response.status in client.responses:
            code = client.responses[response.status]
        else:
            code = f"HTTP error {response.status}"
        try:
            error = json.load(response)
        except json.decoder.JSONDecodeError:
            error = None
        return code, error

def curl_github(path, body=None, auth=None, ctype='POST'):
    headers = dict()
    if not body:
        body = dict()
    # Required by Github v3 API.
    body["accept"] = "application/vnd.github.v3+json"
    if auth:
        # HTTP BasicAuth: not supported
        #authstr = ':'.join(auth)
        ## https://stackoverflow.com/a/7000784
        #authstr = base64.b64encode(bytes(authstr, "ascii")).decode("ascii")
        #headers["Authorization"] = f"Basic {authstr}"
        user, token = auth
        body["user"] = user
        body["user_secret"] = token
        headers["Authorization"] = f"token {token}"
        code, response = curl(ctype, path, headers, body)
        if not code:
            return response
        try:
            message = response["message"]
            if "errors" in response:
                for sub in response["errors"]:
                    message += f': {sub["message"]}'
        except:
            message = "unknown error"
        fail(f"API request failed: {code}: {message}")

def curl_gitlab(path, body=None, auth=None, ctype='POST'):
    headers = dict()
    if not body:
        body = dict()
    if auth:
        # HTTP BasicAuth: not supported
        #authstr = ':'.join(auth)
        ## https://stackoverflow.com/a/7000784
        #authstr = base64.b64encode(bytes(authstr, "ascii")).decode("ascii")
        #headers["Authorization"] = f"Basic {authstr}"
        headers["PRIVATE-TOKEN"] = f"{auth}"
    code, response = curl(ctype, path, headers, body)
    if not code:
        return response
    message = response
    try:
        for field in ["error", "message"]:
            if field in response:
                message = response[field]
                break
    except:
        pass
    fail(f"API request failed: {code}: {message}")

# What kind of system the target is.
target_type = None
# Directory on target system to symlink repo to.
repo_link = None
# Prefix of git remote.
remote = None
# User or organization name on target.
org = None
# New repository name.
repo = None
if args.site:
    spec = re.match(f"(({'|'.join(gitlabhub)})[.a-zA-Z0-9]*)(-(.*))?$", args.site)
    if spec:
        target_type = spec[2]
        if spec[1] != spec[2]:
            target_host = spec[1]
        else:
            target_host = f"{target_type}.com"
        org = spec[4]
        remote = f"ssh://git@{target_host}"
    elif re.match("ssh://", args.site):
        target_type = "url"
        remote = args.site
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
        remote = f"ssh://git@{urlbase}"
        repo_link = fields['REPOLINK']
        if args.repo_link:
            repo_link = args.repo_link
elif args.fork:
    status, full_url = git_command("remote", "get-url", "origin").strip()
    if status != 0:
        fail("could not get fork origin")
    m = re.match("(.*)/([^/]+)/([^/]+)/?$", full_url)
    remote = m[1]
    org = m[2]
    repo = m[3]
    target_type = "fork"
else:
    target_type = "github"
    remote = "ssh://git@github.com"

# Set up the repo name.
if args.repo:
    if repo:
        warn(f"overriding repo name {repo} with {args.repo}")
    repo = args.repo
if not repo:
    repo = Path.cwd().name
if not re.search("\.git$", repo):
    repo += ".git"

# Find current and main branch names.
status, branches = git_command("branch")
if status != 0:
    fail("could not get branches")
branches = branches.splitlines()    
branches.sort()
branch = branches.pop()
assert branch.startswith("* "), "internal error: branch no star"
branch = branch[2:]
branches = list(map(lambda b: b[2:], branches))
main_branch = None
if branch in ["main", "master"]:
    main_branch = branch
elif "main" in branches:
    main_branch = "main"
elif "master" in branches:
    main_branch = "master"
else:
    fail(f"cannot find main or master branch")

# Find an appropriate description for the target repo.
description = args.description
if target_type in gitlabhub and not description:
    status, description = git_command("log", "--pretty=%s", main_branch)
    if status == 0 and len(description) > 0:
        description = description.splitlines()[-1]
    else:
        description = f"{repo}"

# Now the controlling variables should be set up: the fun
# can commence.
print("target_type", target_type)
print("remote", remote)
print("org", org)
print("repo", repo)
print("repo_link", repo_link)
print("branch", branch)
print("main_branch", main_branch)
print("description", description)
#exit(0)

assert target_type, "no target type"
assert remote, "no remote"

# Actually do the work
if target_type == "github":
    user = read_oneliner(home / ".githubuser")
    oauthtoken = read_oneliner(home / ".github-oauthtoken")
    auth = (user, oauthtoken)
    if org:
        create_path = f"/orgs/{org}/repos"
        github_dir = org
    else:
        create_path = "/user/repos"
        github_dir = user
    private = str(args.private).lower()
    body = {
        "name": repo,
        "description": description,
    }
    if args.private:
        body["private"] = True
    connect("api.github.com")
    curl_github(create_path, body=body, auth=auth)
    remote = f"{remote}/{github_dir}/{repo}"
elif target_type == "gitlab":
    # XXX could probably deal with orgs
    if org:
        fail("gitlab orgs not yet supported")
    user = read_oneliner(home / f".gitlabuser-{target_host}")
    # XXX could get a new token
    oauthtoken = read_oneliner(home / f".gitlab-token-{target_host}")
    if args.private:
        visibility = "private"
    else:
        visibility = "public"
    assert repo[-4:] == ".git"
    name = repo[:-4]
    body = {
        "name": name,
        "visibility": visibility,
        "description": description,
    }
    connect(target_host)
    curl_gitlab("/api/v4/projects", body=body, auth=oauthtoken)
    remote = f"{remote}/{user}/{repo}"

status, _ = git_command("remote", "add", "origin", remote)
if status != 0:
    print("warning: updating remote", file=sys.stderr)
    git_command("remote", "rm", "origin")
    status, _ = git_command("remote", "add", "origin", remote)
    if status != 0:
        fail(f"could not update remote origin to {remote}")
status, _ = git_command("push", "-u", "origin", f"{main_branch}:{main_branch}")
if status != 0:
    fail(f"could not push {main_branch} to origin")
if branch != main_branch:
    status, _ = git_command("push", "-u", "origin", f"{branch}:{branch}")
    if status != 0:
        fail(f"could not push {branch} to origin")
