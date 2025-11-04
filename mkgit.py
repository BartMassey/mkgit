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
from typing import Optional, List, Dict, Tuple, NoReturn, Any, Union
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
def fail(msg: str) -> NoReturn:
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


# Authentication management
class AuthHandler:
    """Handles authentication for different git services."""

    def __init__(self, home_dir: Path):
        self.home = home_dir

    def get_github_credentials(self) -> Tuple[str, str]:
        """Get GitHub username and token."""
        user_file = self.home / ".githubuser"
        token_file = self.home / ".github-oauthtoken"

        if not user_file.exists():
            fail(f"need {user_file}")
        if not token_file.exists():
            fail(f"need {token_file}")

        return read_oneliner(user_file), read_oneliner(token_file)

    def get_gitlab_credentials(self, host: str) -> Tuple[str, str]:
        """Get GitLab username and handle token creation."""
        user_file = self.home / f".gitlabuser-{host}"
        if not user_file.exists():
            fail(f"need {user_file}")

        user = read_oneliner(user_file)
        token = self._get_or_create_gitlab_token(host, user)

        return user, token

    def _get_or_create_gitlab_token(self, host: str, user: str) -> str:
        """Get existing GitLab token or create a new one."""
        token_file = self.home / f".gitlab-token-{host}"

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


# Git operations management
class GitOperations:
    """Handles git operations and repository management."""

    @staticmethod
    def execute_command(*args, verbose: bool = True) -> Tuple[int, str]:
        """Execute git command and return status, stdout."""
        return git_command(*args, verbose=verbose)

    @staticmethod
    def get_current_branch() -> str:
        """Get the current git branch name."""
        status, branch_output = git_command("branch")
        if status != 0:
            fail("could not get current branch")

        for line in branch_output.splitlines():
            if line.startswith("* "):
                return line[2:]

        fail("could not determine current branch")

    @staticmethod
    def get_default_description(branch: str, source_dir: Path) -> str:
        """Get default description from git log or directory name."""
        status, desc_output = git_command("log", "--pretty=%s", branch)
        if status == 0 and desc_output.strip():
            return desc_output.strip().split('\n')[-1]
        else:
            return f"Repository {source_dir.name}"

    @staticmethod
    def setup_and_push_remote(source_dir: Path, remote_url: str, current_branch: str) -> None:
        """Setup git remote and push."""
        os.chdir(source_dir)

        status, _ = git_command("remote", "get-url", "origin")
        if status == 0:
            warn("updating existing remote")
            git_command("remote", "rm", "origin")

        git_command("remote", "add", "origin", remote_url)

        status, output = git_command("push", "-u", "origin", current_branch)
        if status != 0:
            fail(f"push to origin failed: {output}")

        print(f"Successfully created and pushed to {remote_url}")


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
def validate_branch(branch: str) -> None:
    """Validate that branch is a main branch."""
    if branch not in VALID_MAIN_BRANCHES:
        fail(f"invalid main branch {branch}, must be {' or '.join(VALID_MAIN_BRANCHES)}")


# Service classes
class GitHubService:
    """Handles GitHub-specific repository operations."""

    def __init__(self, auth_handler: AuthHandler):
        self.auth = auth_handler

    def create_repository(self, site_config: SiteConfig, git_ctx: GitContext, private: bool) -> None:
        """Create GitHub repository via API."""
        user, token = self.auth.get_github_credentials()

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "mkgit"
        }

        data: Dict[str, Any] = {
            "name": git_ctx.repo_name.replace('.git', ''),
            "description": git_ctx.description
        }

        if private:
            data["private"] = True

        try:
            if site_config.org:
                url = f"/orgs/{site_config.org}/repos"
            else:
                url = "/user/repos"

            conn = client.HTTPSConnection(GITHUB_API_HOST)
            body = json.dumps(data)
            conn.request("POST", url, body=body, headers=headers)
            response = conn.getresponse()

            if response.status != 201:
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

    def fork_repository(self, site_config: SiteConfig) -> str:
        """Fork GitHub repository via API. Returns remote URL."""
        user, token = self.auth.get_github_credentials()

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
        fork_org = site_config.org if site_config.org else f"{user}-upstream"

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

    def get_repository_url(self, site_config: SiteConfig, git_ctx: GitContext) -> str:
        """Get repository URL for GitHub."""
        user, _ = self.auth.get_github_credentials()
        gh_org = site_config.org if site_config.org else user
        return f"ssh://git@github.com/{gh_org}/{git_ctx.repo_name}"


class GitLabService:
    """Handles GitLab-specific repository operations."""

    def __init__(self, auth_handler: AuthHandler):
        self.auth = auth_handler

    def create_repository(self, site_config: SiteConfig, git_ctx: GitContext, private: bool) -> None:
        """Create GitLab repository via API."""
        user, token = self.auth.get_gitlab_credentials(site_config.host)

        headers = {
            "PRIVATE-TOKEN": token,
            "Content-Type": "application/json"
        }

        data = {
            "name": git_ctx.repo_name.replace('.git', ''),
            "visibility": "private" if private else "public",
            "description": git_ctx.description
        }

        try:
            conn = client.HTTPSConnection(site_config.host)
            body = json.dumps(data)
            conn.request("POST", "/api/v4/projects", body=body, headers=headers)
            response = conn.getresponse()

            if response.status != 201:
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

    def fork_repository(self, site_config: SiteConfig) -> str:
        """Fork GitLab repository - not supported."""
        fail("forking only supported for GitHub")

    def get_repository_url(self, site_config: SiteConfig, git_ctx: GitContext) -> str:
        """Get repository URL for GitLab."""
        user, _ = self.auth.get_gitlab_credentials(site_config.host)
        return f"ssh://git@{site_config.host}/{user}/{git_ctx.repo_name}"


class SSHService:
    """Handles SSH-based repository operations."""

    def __init__(self, auth_handler: Optional[AuthHandler] = None):
        self.auth = auth_handler  # Not used for SSH, but kept for consistency

    def create_repository(self, site_config: SiteConfig, git_ctx: GitContext, private: bool) -> None:
        """Create repository on remote host via SSH."""
        if site_config.parent_path is None:
            fail("SSH site configuration missing parent_path")
        parent_q = shell_escape(site_config.parent_path)
        repo_q = shell_escape(git_ctx.repo_name)
        desc_q = shell_escape(git_ctx.description)

        ssh_script = f"""cd "{parent_q}" &&
mkdir -p "{repo_q}" &&
cd "{repo_q}" &&
git init --bare --shared=group &&
echo "{desc_q}" >description &&
if {str(not private).lower()} ; then
    touch git-daemon-export-ok &&
    if [ "{site_config.repo_link or ''}" != "" ] ; then
        ln -sf "{parent_q}/{repo_q}" "{site_config.repo_link}"/
    fi
fi"""

        try:
            result = subprocess.run(["ssh", "-x", site_config.host, "sh"],
                                  input=ssh_script, text=True, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            fail(f"SSH to {site_config.host} failed: {e.stderr}")

    def fork_repository(self, site_config: SiteConfig) -> str:
        """Fork SSH repository - not supported."""
        fail("forking only supported for GitHub")

    def get_repository_url(self, site_config: SiteConfig, git_ctx: GitContext) -> str:
        """Get repository URL for SSH."""
        if site_config.parent_path is None:
            fail("SSH site configuration missing parent_path")
        return f"ssh://{site_config.host}{site_config.parent_path}/{git_ctx.repo_name}"


# Service factory
class ServiceFactory:
    """Factory for creating appropriate service instances."""

    @staticmethod
    def create_service(site_type: str, auth_handler: AuthHandler) -> Union[GitHubService, GitLabService, SSHService]:
        """Create service instance based on site type."""
        if site_type == "github":
            return GitHubService(auth_handler)
        elif site_type == "gitlab":
            return GitLabService(auth_handler)
        elif site_type in ["ssh", "custom"]:
            return SSHService(auth_handler)
        else:
            fail(f"unknown site type: {site_type}")


# Utility functions for SSH
def shell_escape(s: str) -> str:
    """Escape special characters for shell."""
    return s.replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')


# Site configuration parsing
def parse_github_gitlab_site(site_arg: str) -> SiteConfig:
    """Parse github/gitlab site argument string."""
    match = re.match(r'^(github|gitlab)(.*)$', site_arg)
    if not match:
        fail(f"invalid site format: {site_arg}")

    service = match.group(1)
    suffix = match.group(2)  # Everything after "github" or "gitlab"

    if service == "github":
        # github -> no org
        # github-org -> org is "org"
        if suffix.startswith('-'):
            suffix = suffix[1:]  # strip leading hyphen
        return SiteConfig(
            type="github",
            host="github.com",
            org=suffix if suffix else None
        )
    elif service == "gitlab":
        # Parse gitlab suffix for host and org
        if not suffix:
            # plain gitlab -> gitlab.com
            return SiteConfig(
                type="gitlab",
                host="gitlab.com",
                org=None
            )

        # Handle leading hyphen or dot
        if suffix.startswith('-'):
            suffix = suffix[1:]  # strip leading hyphen
        elif suffix.startswith('.'):
            # gitlab.foo.com -> treat as hostname shorthand
            suffix = service + suffix  # reconstruct full hostname

        # Now parse the suffix
        # Check if suffix has both a dot and a hyphen
        parts = suffix.split('-', 1)
        if len(parts) == 2 and '.' in parts[0]:
            # gitlab.foo.com-org OR gitlab-gitlab.foo.com-org -> host=gitlab.foo.com, org=org
            return SiteConfig(
                type="gitlab",
                host=parts[0],
                org=parts[1]
            )
        elif '.' in suffix:
            # gitlab.foo.com OR gitlab-gitlab.foo.com -> host=gitlab.foo.com
            return SiteConfig(
                type="gitlab",
                host=suffix,
                org=None
            )
        else:
            # gitlab-org OR org -> gitlab.com with org
            return SiteConfig(
                type="gitlab",
                host="gitlab.com",
                org=suffix
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
        if not host or not parsed_repo:
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
        if not host or not parsed_repo:
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
        parent_path=script_vars.get('PARENT'),
        repo_link=script_vars.get('REPOLINK')
    ), repo_name


# Repository creation
def create_remote_repository(site_config: SiteConfig, git_ctx: GitContext,
                             private: bool, is_fork: bool, auth_handler: AuthHandler) -> str:
    """Create remote repository and return remote URL."""

    # Create appropriate service
    service = ServiceFactory.create_service(site_config.type, auth_handler)

    if is_fork:
        return service.fork_repository(site_config)
    else:
        service.create_repository(site_config, git_ctx, private)
        return service.get_repository_url(site_config, git_ctx)


def setup_and_push_remote(git_ctx: GitContext, remote_url: str) -> None:
    """Setup git remote and push."""
    GitOperations.setup_and_push_remote(git_ctx.source_dir, remote_url, git_ctx.current_branch)


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

    current_branch = GitOperations.get_current_branch()
    validate_branch(current_branch)

    description = args.description
    if not description:
        description = GitOperations.get_default_description(current_branch, source_dir)

    repo_name = args.repo if args.repo else source_dir.name
    if not repo_name.endswith('.git'):
        repo_name += '.git'

    return GitContext(
        source_dir=source_dir,
        current_branch=current_branch,
        description=description,
        repo_name=repo_name
    )


def main() -> None:
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

    # Initialize auth handler
    auth_handler = AuthHandler(Path.home())

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
    remote_url = create_remote_repository(site_config, git_ctx, args.private, args.fork, auth_handler)
    setup_and_push_remote(git_ctx, remote_url)


if __name__ == "__main__":
    main()
