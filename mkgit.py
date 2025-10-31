#!/usr/bin/python3
# Copyright © 2012 Bart Massey
# [This program is licensed under the "MIT License"]
# Please see the file LICENSE.txt in the source
# distribution of this software for license terms.

import argparse
import getpass
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import http.client as client


# Constants
DEFAULT_SITE_DIRS = [Path("/usr/local/share/mkgit")]
VALID_MAIN_BRANCHES = ["master", "main"]
GITHUB_API_HOST = "api.github.com"


# Data structures
@dataclass
class SiteConfig:
    """Configuration for a target repository site."""
    type: str  # github, gitlab, ssh, custom
    host: str
    org: Optional[str] = None
    parent_path: Optional[str] = None
    repo_link: Optional[str] = None


@dataclass
class GitContext:
    """Context for the local git repository."""
    source_dir: Path
    current_branch: str
    description: str
    repo_name: str


# Utility functions
def fail(msg: str) -> None:
    """Print error message and exit with status 1."""
    print("mkgit:", msg, file=sys.stderr)
    exit(1)


def warn(msg: str) -> None:
    """Print warning message to stderr."""
    print("mkgit: warning:", msg, file=sys.stderr)


def read_oneliner(path: Path) -> str:
    """Read and return contents of single-line file."""
    try:
        with open(path, "r") as f:
            result = f.read().strip()
            if len(result.splitlines()) > 1:
                fail(f"{path}: expected one line")
            return result
    except Exception as e:
        fail(f"error reading {path}: {e}")


def git_command(*args, verbose: bool = True) -> Tuple[int, str]:
    """Execute git command and return status, stdout."""
    command = ["git", *args]
    try:
        status = subprocess.run(command, capture_output=True, text=True, check=False)
        if status.returncode != 0 and verbose:
            print(status.stderr, file=sys.stderr)
        return status.returncode, status.stdout
    except Exception as e:
        if verbose:
            print(f"git command failed: {e}", file=sys.stderr)
        return 1, ""


# Site directory management
def get_site_directories() -> List[Path]:
    """Get list of directories to search for site configuration files."""
    env_dir = os.environ.get('MKGIT_SITE_DIR')
    if env_dir:
        return [Path(env_dir)]
    else:
        return DEFAULT_SITE_DIRS + [Path(__file__).parent]


def find_site_scripts() -> List[str]:
    """Find site scripts in site directory."""
    scripts = []
    for script_dir in get_site_directories():
        if script_dir.exists() and script_dir.is_dir():
            for file in script_dir.glob("mkgit-*"):
                if file.is_file():
                    scripts.append(file.name)
    return scripts


def list_sites() -> List[str]:
    """Return list of available site options."""
    sites = ["github", "gitlab"]
    site_scripts = find_site_scripts()
    for script in site_scripts:
        site_name = script.replace("mkgit-", "")
        sites.append(site_name)
    return sites


# SSH URL parsing
def parse_ssh_url(ssh_url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse SSH URL and return (host, parent_path, repo_name)."""
    git_match = re.match(r'ssh://([^/]*)', ssh_url)
    parent_match = re.match(r'ssh://[^/]*(/.*)/', ssh_url)
    proj_match = re.match(r'ssh://[^/]*/.*/([^/]*\.git)$', ssh_url)

    if not proj_match:
        proj_match = re.match(r'ssh://[^/]*/.*/([^/.]*)$', ssh_url)

    if git_match and parent_match and proj_match:
        host = git_match.group(1)
        parent_path = parent_match.group(1)
        repo_name = proj_match.group(1)
        if not repo_name.endswith('.git'):
            repo_name += '.git'
        return host, parent_path, repo_name

    return None, None, None


# Git operations
def get_current_branch() -> str:
    """Get the current git branch name."""
    status, branch_output = git_command("branch")
    if status != 0:
        fail("could not get current branch")

    for line in branch_output.splitlines():
        if line.startswith("* "):
            return line[2:]

    fail("could not determine current branch")


def validate_branch(branch: str) -> None:
    """Validate that branch is a main branch."""
    if branch not in VALID_MAIN_BRANCHES:
        fail(f"invalid main branch {branch}, must be {' or '.join(VALID_MAIN_BRANCHES)}")


def get_default_description(branch: str, source_dir: Path) -> str:
    """Get default description from git log or directory name."""
    status, desc_output = git_command("log", "--pretty=%s", branch)
    if status == 0 and desc_output.strip():
        return desc_output.strip().split('\n')[-1]
    else:
        return f"Repository {source_dir.name}"


# GitHub API operations
def create_github_repo(user: str, token: str, org: Optional[str], repo: str,
                       description: str, private: bool) -> bool:
    """Create GitHub repository via API."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "mkgit"
    }

    data = {
        "name": repo.replace('.git', ''),
        "description": description
    }

    if private:
        data["private"] = True

    try:
        if org:
            url = f"/orgs/{org}/repos"
        else:
            url = "/user/repos"

        conn = client.HTTPSConnection(GITHUB_API_HOST)
        body = json.dumps(data)
        conn.request("POST", url, body=body, headers=headers)
        response = conn.getresponse()

        if response.status == 201:
            return True
        else:
            error_body = response.read().decode()
            try:
                error_data = json.loads(error_body)
                message = error_data.get("message", "Unknown error")
                if "errors" in error_data:
                    for error in error_data["errors"]:
                        message += f": {error.get('message', 'Unknown')}"
            except (json.JSONDecodeError, KeyError):
                message = error_body[:200]
            fail(f"GitHub API error: {message}")

    except Exception as e:
        fail(f"GitHub connection error: {e}")


def fork_github_repo(user: str, token: str, org: Optional[str]) -> str:
    """Fork GitHub repository via API. Returns remote URL."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "mkgit"
    }

    # Get current origin to determine fork source
    status, origin_url = git_command("remote", "get-url", "origin")
    if status != 0:
        fail("could not get origin URL")

    origin_match = re.match(r'https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$', origin_url.strip())
    if origin_match is None:
        fail(f"origin must be a GitHub repository: {origin_url.strip()}")

    source_user = origin_match.group(1)
    source_repo = origin_match.group(2).replace('.git', '')

    # Determine fork organization
    fork_org = org if org else f"{user}-upstream"

    # Create fork via API
    try:
        conn = client.HTTPSConnection(GITHUB_API_HOST)
        data = {
            "organization": fork_org
        }
        body = json.dumps(data)
        url = f"/repos/{source_user}/{source_repo}/forks"
        conn.request("POST", url, body=body, headers=headers)
        response = conn.getresponse()

        if response.status == 202:
            return f"ssh://git@github.com/{fork_org}/{source_repo}.git"
        else:
            error_body = response.read().decode()
            fail(f"GitHub fork failed: {error_body}")

    except Exception as e:
        fail(f"GitHub fork error: {e}")


# GitLab API operations
def create_gitlab_repo(user: str, token: str, host: str, repo: str,
                       description: str, private: bool) -> bool:
    """Create GitLab repository via API."""
    headers = {
        "PRIVATE-TOKEN": token,
        "Content-Type": "application/json"
    }

    data = {
        "name": repo.replace('.git', ''),
        "visibility": "private" if private else "public",
        "description": description
    }

    try:
        conn = client.HTTPSConnection(host)
        body = json.dumps(data)
        conn.request("POST", "/api/v4/projects", body=body, headers=headers)
        response = conn.getresponse()

        if response.status == 201:
            return True
        else:
            error_body = response.read().decode()
            try:
                error_data = json.loads(error_body)
                if isinstance(error_data, dict):
                    if "error_description" in error_data:
                        message = error_data["error_description"]
                    elif "message" in error_data:
                        message = error_data["message"]
                    else:
                        message = str(error_data)
                else:
                    message = str(error_data)
            except (json.JSONDecodeError, KeyError):
                message = error_body[:200]
            fail(f"GitLab API error: {message}")

    except Exception as e:
        fail(f"GitLab connection error: {e}")


def get_gitlab_token(host: str, user: str, home: Path) -> str:
    """Get or create GitLab token."""
    token_file = home / f".gitlab-token-{host}"

    if token_file.exists():
        return read_oneliner(token_file)

    # Need to authenticate to get token
    password = getpass.getpass(f"GitLab password for {user}@{host}: ")

    try:
        conn = client.HTTPSConnection(host)
        data = {
            "login": user,
            "password": password
        }
        body = json.dumps(data)
        conn.request("POST", "/api/v4/session", body=body, headers={"Content-Type": "application/json"})
        response = conn.getresponse()

        if response.status == 201:
            response_data = json.loads(response.read().decode())
            private_token = response_data.get("private_token")
            if private_token:
                with open(token_file, "w") as f:
                    f.write(private_token)
                os.chmod(token_file, 0o600)
                return private_token
            else:
                fail("no private token in response")
        else:
            fail("GitLab authentication failed")

    except Exception as e:
        fail(f"GitLab authentication error: {e}")


# SSH operations
def shell_escape(s: str) -> str:
    """Escape special characters for shell."""
    return s.replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')


def create_ssh_repo(host: str, parent_path: str, repo_name: str,
                    description: str, private: bool, repo_link: Optional[str] = None) -> bool:
    """Create repository on remote host via SSH."""
    parent_q = shell_escape(parent_path)
    repo_q = shell_escape(repo_name)
    desc_q = shell_escape(description)

    ssh_script = f"""cd "{parent_q}" &&
mkdir -p "{repo_q}" &&
cd "{repo_q}" &&
git init --bare --shared=group &&
echo "{desc_q}" >description &&
if {str(not private).lower()} ; then
    touch git-daemon-export-ok &&
    if [ "{repo_link or ''}" != "" ] ; then
        ln -sf "{parent_q}/{repo_q}" "{repo_link}"/
    fi
fi"""

    try:
        result = subprocess.run(["ssh", "-x", host, "sh"],
                              input=ssh_script, text=True, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        fail(f"SSH to {host} failed: {e.stderr}")


# Site configuration parsing
def parse_github_gitlab_site(site_arg: str) -> SiteConfig:
    """Parse github/gitlab site argument string."""
    match = re.match(r'^(github|gitlab)(?:-([^-]+)(?:-([^-]+))?)?$', site_arg)
    if not match:
        fail(f"invalid site format: {site_arg}")

    service = match.group(1)

    if service == "github":
        return SiteConfig(
            type="github",
            host="github.com",
            org=match.group(3) if match.group(3) else None
        )
    elif service == "gitlab":
        # Parse gitlab-host-org or gitlab-org patterns
        if match.group(3):
            # gitlab-host-org
            return SiteConfig(
                type="gitlab",
                host=match.group(2),
                org=match.group(3)
            )
        elif match.group(2):
            if '.' in match.group(2):
                # gitlab-host
                return SiteConfig(
                    type="gitlab",
                    host=match.group(2),
                    org=None
                )
            else:
                # gitlab-org
                return SiteConfig(
                    type="gitlab",
                    host="gitlab.com",
                    org=match.group(2)
                )
        else:
            # plain gitlab
            return SiteConfig(
                type="gitlab",
                host="gitlab.com",
                org=None
            )
    else:
        fail(f"internal error: unknown service {service}")


def parse_custom_site_file(site_name: str) -> Dict[str, str]:
    """Parse custom site configuration file."""
    script_path = None
    for search_dir in get_site_directories():
        potential_path = search_dir / f"mkgit-{site_name}"
        if potential_path.exists():
            script_path = potential_path
            break

    if script_path is None:
        fail(f"unknown site script: mkgit-{site_name}")

    script_vars = {}
    try:
        with open(str(script_path), 'r') as f:
            for line in f:
                line = line.strip()
                if line and '=' in line and not line.startswith('#'):
                    var, val = line.split('=', 1)
                    script_vars[var.strip()] = val.strip()
    except Exception as e:
        fail(f"failed to read site script: {e}")

    return script_vars


def parse_site_config(args, repo_arg: str) -> Tuple[Optional[SiteConfig], str]:
    """Parse site configuration from arguments. Returns (SiteConfig, repo_name)."""
    repo_name = repo_arg

    # Handle SSH URL as positional argument
    if not args.site and repo_arg and repo_arg.startswith("ssh://"):
        host, parent_path, parsed_repo = parse_ssh_url(repo_arg)
        if not host:
            fail(f"bad SSH URL: {repo_arg}")
        return SiteConfig(
            type="ssh",
            host=host,
            parent_path=parent_path
        ), parsed_repo

    # No site specified
    if not args.site:
        return None, repo_name

    # SSH URL via -X flag
    if args.site.startswith("ssh://"):
        host, parent_path, parsed_repo = parse_ssh_url(args.site)
        if not host:
            fail(f"bad SSH URL: {args.site}")
        return SiteConfig(
            type="ssh",
            host=host,
            parent_path=parent_path
        ), parsed_repo

    # GitHub or GitLab
    if args.site.startswith("github") or args.site.startswith("gitlab"):
        return parse_github_gitlab_site(args.site), repo_name

    # Custom site
    script_vars = parse_custom_site_file(args.site)

    target_host = script_vars.get('GITHOST')
    if not target_host:
        fail("site script must set GITHOST")

    return SiteConfig(
        type="custom",
        host=target_host,
        parent_path=script_vars.get('PARENT', ''),
        repo_link=script_vars.get('REPOLINK')
    ), repo_name


# Repository creation
def create_remote_repository(site_config: SiteConfig, git_ctx: GitContext,
                             private: bool, is_fork: bool, home: Path) -> str:
    """Create remote repository and return remote URL."""

    if is_fork:
        if site_config.type != "github":
            fail("forking only supported for GitHub")

        user = read_oneliner(home / ".githubuser")
        token = read_oneliner(home / ".github-oauthtoken")
        return fork_github_repo(user, token, site_config.org)

    elif site_config.type == "github":
        user = read_oneliner(home / ".githubuser")
        token = read_oneliner(home / ".github-oauthtoken")
        create_github_repo(user, token, site_config.org, git_ctx.repo_name,
                          git_ctx.description, private)
        gh_org = site_config.org if site_config.org else user
        return f"ssh://git@github.com/{gh_org}/{git_ctx.repo_name}"

    elif site_config.type == "gitlab":
        gitlab_user_file = home / f".gitlabuser-{site_config.host}"
        if not gitlab_user_file.exists():
            fail(f"need {gitlab_user_file}")

        user = read_oneliner(gitlab_user_file)
        token = get_gitlab_token(site_config.host, user, home)
        create_gitlab_repo(user, token, site_config.host, git_ctx.repo_name,
                          git_ctx.description, private)
        return f"ssh://git@{site_config.host}/{user}/{git_ctx.repo_name}"

    elif site_config.type == "ssh":
        create_ssh_repo(site_config.host, site_config.parent_path, git_ctx.repo_name,
                       git_ctx.description, private)
        return f"ssh://{site_config.host}{site_config.parent_path}/{git_ctx.repo_name}"

    elif site_config.type == "custom":
        create_ssh_repo(site_config.host, site_config.parent_path, git_ctx.repo_name,
                       git_ctx.description, private, site_config.repo_link)
        return f"ssh://{site_config.host}{site_config.parent_path}/{git_ctx.repo_name}"

    else:
        fail(f"unknown site type: {site_config.type}")


def setup_and_push_remote(git_ctx: GitContext, remote_url: str) -> None:
    """Setup git remote and push."""
    os.chdir(git_ctx.source_dir)

    status, _ = git_command("remote", "get-url", "origin")
    if status == 0:
        warn("updating existing remote")
        git_command("remote", "rm", "origin")

    git_command("remote", "add", "origin", remote_url)

    status, output = git_command("push", "-u", "origin", git_ctx.current_branch)
    if status != 0:
        fail(f"push to origin failed: {output}")

    print(f"Successfully created and pushed to {remote_url}")


# Main workflow
def setup_git_context(args) -> GitContext:
    """Setup and validate git repository context."""
    if args.source_dir:
        source_dir = Path(args.source_dir).resolve()
        if not (source_dir / ".git").exists():
            fail(f"directory {source_dir} is not a git working directory!")
        os.chdir(source_dir)
    else:
        source_dir = Path.cwd()
        if not (source_dir / ".git").exists():
            fail(f"current directory is not a git working directory!")

    current_branch = get_current_branch()
    validate_branch(current_branch)

    description = args.description
    if not description:
        description = get_default_description(current_branch, source_dir)

    repo_name = args.repo if args.repo else source_dir.name
    if not repo_name.endswith('.git'):
        repo_name += '.git'

    return GitContext(
        source_dir=source_dir,
        current_branch=current_branch,
        description=description,
        repo_name=repo_name
    )


def main():
    """Main entry point for the mkgit command."""
    ap = argparse.ArgumentParser(description="Create a new upstream git repository")
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
        "-X",
        "--site",
        help="site for new repo (use --list-sites for options)",
    )
    ap.add_argument(
        "--list-sites",
        help="list available site options",
        action="store_true",
    )
    ap.add_argument(
        "repo",
        help="name of repository (with or without .git)",
        nargs="?",
    )
    ap.add_argument(
        "source_dir",
        help="source directory (defaults to current directory)",
        nargs="?",
    )
    args = ap.parse_args()

    if args.list_sites:
        sites = list_sites()
        print("Available sites:", ", ".join(sites), file=sys.stderr)
        print("Usage examples:", file=sys.stderr)
        print("  mkgit -X github myrepo", file=sys.stderr)
        print("  mkgit -X gitlab myrepo", file=sys.stderr)
        print("  mkgit -X github-org myrepo", file=sys.stderr)
        print("  mkgit ssh://user@host/path/repo.git", file=sys.stderr)
        exit(0)

    home = Path.home()
    git_ctx = setup_git_context(args)

    # Determine site configuration
    repo_arg = args.repo if args.repo else git_ctx.source_dir.name
    site_config, parsed_repo_name = parse_site_config(args, repo_arg)

    # Update repo_name if it was parsed from SSH URL
    if parsed_repo_name != repo_arg:
        git_ctx.repo_name = parsed_repo_name

    if site_config is None:
        fail("no target site specified")

    # Create repository and setup remote
    remote_url = create_remote_repository(site_config, git_ctx, args.private, args.fork, home)
    setup_and_push_remote(git_ctx, remote_url)


if __name__ == "__main__":
    main()
