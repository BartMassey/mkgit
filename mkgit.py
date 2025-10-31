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
from pathlib import Path
import http.client as client


# =============================================================================
# Utility Functions
# =============================================================================

def fail(msg):
    """Print error message and exit with status 1."""
    print("mkgit:", msg, file=sys.stderr)
    exit(1)


def warn(msg):
    """Print warning message to stderr."""
    print("mkgit: warning:", msg, file=sys.stderr)


def shell_escape(s):
    """Escape special characters for shell commands."""
    return s.replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')


# =============================================================================
# Authentication Handler
# =============================================================================

class AuthHandler:
    """Handles authentication for different git services."""
    
    def __init__(self, home_dir):
        self.home = Path(home_dir)
    
    def read_oneliner(self, path):
        """Read and return contents of single-line file."""
        try:
            with open(path, "r") as f:
                result = f.read().strip()
                if len(result.splitlines()) > 1:
                    fail(f"{path}: expected one line")
                return result
        except Exception as e:
            fail(f"error reading {path}: {e}")
    
    def get_github_credentials(self):
        """Get GitHub username and token."""
        user_file = self.home / ".githubuser"
        token_file = self.home / ".github-oauthtoken"
        
        if not user_file.exists():
            fail(f"need {user_file}")
        if not token_file.exists():
            fail(f"need {token_file}")
        
        return self.read_oneliner(user_file), self.read_oneliner(token_file)
    
    def get_gitlab_credentials(self, host):
        """Get GitLab username and handle token creation."""
        user_file = self.home / f".gitlabuser-{host}"
        if not user_file.exists():
            fail(f"need {user_file}")
        
        user = self.read_oneliner(user_file)
        token = self._get_or_create_gitlab_token(host, user)
        
        return user, token
    
    def _get_or_create_gitlab_token(self, host, user):
        """Get existing GitLab token or create a new one."""
        token_file = self.home / f".gitlabtoken-{host}"
        
        if token_file.exists():
            return self.read_oneliner(token_file)
        
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


# =============================================================================
# Git Operations Handler
# =============================================================================

class GitOperations:
    """Handles git operations and repository management."""
    
    @staticmethod
    def execute_git_command(*args, verbose=True):
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
    
    @staticmethod
    def get_current_branch():
        """Get the current git branch."""
        status, branch_output = GitOperations.execute_git_command("branch")
        if status != 0:
            fail("could not get current branch")
            
        branch = None
        for line in branch_output.splitlines():
            if line.startswith("* "):
                branch = line[2:]
                break
        
        if branch is None:
            fail("could not determine current branch")
        
        if branch not in ["master", "main"]:
            fail(f"invalid main branch {branch}, must be master or main")
        
        return branch
    
    @staticmethod
    def get_description(default_description):
        """Get repository description from git log or use default."""
        if default_description:
            return default_description
        
        try:
            branch = GitOperations.get_current_branch()
            status, desc_output = GitOperations.execute_git_command("log", "--pretty=%s", branch)
            if status == 0 and desc_output.strip():
                return desc_output.strip().split('\n')[-1]
        except:
            pass
        
        return default_description or "Repository"
    
    @staticmethod
    def setup_remote(repo_url, source_dir):
        """Add or update origin remote."""
        original_dir = os.getcwd()
        try:
            os.chdir(source_dir)
            
            status, _ = GitOperations.execute_git_command("remote", "get-url", "origin")
            if status == 0:
                warn("updating existing remote")
                GitOperations.execute_git_command("remote", "rm", "origin")
            
            GitOperations.execute_git_command("remote", "add", "origin", repo_url)
        finally:
            os.chdir(original_dir)
    
    @staticmethod
    def push_to_remote(branch, source_dir):
        """Push to remote and set upstream."""
        original_dir = os.getcwd()
        try:
            os.chdir(source_dir)
            status, output = GitOperations.execute_git_command("push", "-u", "origin", branch)
            if status != 0:
                fail(f"push to origin failed: {output}")
        finally:
            os.chdir(original_dir)


# =============================================================================
# URL Parser
# =============================================================================

class URLParser:
    """Handles parsing of different URL formats."""
    
    @staticmethod
    def parse_ssh_url(ssh_url):
        """Parse SSH URL and return host, parent path, and repo name."""
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
        else:
            fail(f"bad SSH URL: {ssh_url}")
    
    @staticmethod
    def parse_site_arguments(site_arg):
        """Parse -X site arguments and return service type and configuration."""
        if not site_arg:
            return None, {}
        
        if site_arg.startswith("github") or site_arg.startswith("gitlab"):
            match = re.match(r'^(github|gitlab)(?:-([^-]+)(?:-([^-]+))?)?$', site_arg)
            if match:
                service = match.group(1)
                config = {}
                
                if service == "github":
                    config["host"] = "github.com"
                    config["org"] = match.group(3) if match.group(3) else None
                elif service == "gitlab":
                    if match.group(3):
                        config["host"] = match.group(2)
                        config["org"] = match.group(3)
                    elif match.group(2):
                        if '.' in match.group(2):
                            config["host"] = match.group(2)
                            config["org"] = None
                        else:
                            config["host"] = "gitlab.com"
                            config["org"] = match.group(2)
                    else:
                        config["host"] = "gitlab.com"
                        config["org"] = None
                
                return service, config
        
        elif site_arg.startswith("ssh://"):
            host, parent_path, repo_name = URLParser.parse_ssh_url(site_arg)
            return "ssh", {"host": host, "parent_path": parent_path, "repo_name": repo_name}
        
        else:
            return "custom", {"site_name": site_arg}
    
    @staticmethod
    def parse_repo_name(repo_name):
        """Parse and normalize repository name."""
        if not repo_name:
            return None
        return repo_name if repo_name.endswith('.git') else repo_name + '.git'


# =============================================================================
# Site Configuration
# =============================================================================

class SiteConfiguration:
    """Handles site configuration and custom site scripts."""
    
    @staticmethod
    def find_site_scripts():
        """Find site scripts in site directory."""
        env_dir = os.environ.get('MKGIT_SITE_DIR')
        if env_dir:
            script_dirs = [Path(env_dir)]
        else:
            script_dirs = [
                Path("/usr/local/share/mkgit"),
                Path(__file__).parent
            ]
        
        scripts = []
        for script_dir in script_dirs:
            if script_dir.exists() and script_dir.is_dir():
                for file in script_dir.glob("mkgit-*"):
                    if file.is_file():
                        scripts.append(file.name)
        return scripts
    
    @staticmethod
    def list_sites():
        """Return list of available site options."""
        sites = ["github", "gitlab"]
        site_scripts = SiteConfiguration.find_site_scripts()
        for script in site_scripts:
            site_name = script.replace("mkgit-", "")
            sites.append(site_name)
        return sites
    
    @staticmethod
    def load_site_config(site_name):
        """Load custom site configuration."""
        env_dir = os.environ.get('MKGIT_SITE_DIR')
        if env_dir:
            search_dirs = [Path(env_dir)]
        else:
            search_dirs = [
                Path("/usr/local/share/mkgit"),
                Path(__file__).parent
            ]
        
        script_path = None
        for search_dir in search_dirs:
            potential_path = search_dir / f"mkgit-{site_name}"
            if potential_path.exists():
                script_path = potential_path
                break
        
        if script_path is None or not script_path.exists():
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
        
        return {
            "host": script_vars.get('GITHOST'),
            "parent_path": script_vars.get('PARENT', ''),
            "repo_link": script_vars.get('REPOLINK')
        }


# =============================================================================
# Repository Configuration
# =============================================================================

class RepositoryConfig:
    """Handles repository configuration and target determination."""
    
    def __init__(self, args):
        self.args = args
        self.target_type = None
        self.target_host = None
        self.org = None
        self.parent_path = None
        self.repo_link = None
        self.repo_name = None
        
        self._parse_target()
    
    def _parse_target(self):
        """Parse target configuration from arguments."""
        # Handle site-specific arguments
        if self.args.site:
            self._parse_site_arguments()
        # Handle SSH URLs as positional arguments
        elif self.args.repo and self.args.repo.startswith("ssh://"):
            self._parse_ssh_url(self.args.repo)
        else:
            fail("no target site specified")
        
        # Set repository name
        if not self.repo_name:
            self.repo_name = URLParser.parse_repo_name(self.args.repo or Path.cwd().name)
    
    def _parse_site_arguments(self):
        """Parse -X site arguments."""
        if not self.args.site:
            fail("no site specified")
            
        service, config = URLParser.parse_site_arguments(self.args.site)
        
        if service in ["github", "gitlab"]:
            self.target_type = service
            self.target_host = config["host"]
            self.org = config["org"]
        
        elif service == "ssh":
            self.target_type = "ssh"
            self.target_host = config["host"]
            self.parent_path = config["parent_path"]
            self.repo_name = config["repo_name"]
        
        elif service == "custom":
            self.target_type = "custom"
            site_config = SiteConfiguration.load_site_config(config["site_name"])
            self.target_host = site_config["host"]
            self.parent_path = site_config["parent_path"]
            self.repo_link = site_config["repo_link"]
            
            if not self.target_host:
                fail("site script must set GITHOST")
    
    def _parse_ssh_url(self, ssh_url):
        """Parse SSH URL from positional arguments."""
        self.target_type = "ssh"
        self.target_host, self.parent_path, self.repo_name = URLParser.parse_ssh_url(ssh_url)


# =============================================================================
# Service Classes
# =============================================================================

class GitHubService:
    """Handles GitHub-specific repository operations."""
    
    def __init__(self, auth_handler):
        self.auth = auth_handler
    
    def create_repository(self, config, description, private):
        """Create GitHub repository via API."""
        user, token = self.auth.get_github_credentials()
        
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "mkgit"
        }
        
        data = {
            "name": config.repo_name.replace('.git', ''),
            "description": description
        }
        
        if private:
            data["private"] = True
        
        try:
            if config.org:
                url = f"/orgs/{config.org}/repos"
            else:
                url = "/user/repos"
            
            conn = client.HTTPSConnection("api.github.com")
            body = json.dumps(data)
            conn.request("POST", url, body=body, headers=headers)
            response = conn.getresponse()
            
            if response.status == 201:
                return True
            else:
                self._handle_api_error(response)
                
        except Exception as e:
            fail(f"GitHub connection error: {e}")
    
    def fork_repository(self, config):
        """Fork GitHub repository via API."""
        user, token = self.auth.get_github_credentials()
        
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "mkgit"
        }
        
        # Get current origin to determine fork source
        status, origin_url = GitOperations.execute_git_command("remote", "get-url", "origin")
        if status != 0:
            fail("could not get origin URL")
        
        origin_match = re.match(r'https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$', origin_url.strip())
        if origin_match is None:
            fail(f"origin must be a GitHub repository: {origin_url.strip()}")
        
        source_user = origin_match.group(1)
        source_repo = origin_match.group(2).replace('.git', '')
        
        # Determine fork organization
        fork_org = config.org if config.org else f"{user}-upstream"
        
        # Create fork via API
        try:
            conn = client.HTTPSConnection("api.github.com")
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
                self._handle_api_error(response)
                
        except Exception as e:
            fail(f"GitHub fork error: {e}")
    
    def get_repository_url(self, config):
        """Get repository URL for GitHub."""
        user, _ = self.auth.get_github_credentials()
        gh_org = config.org if config.org else user
        return f"ssh://git@github.com/{gh_org}/{config.repo_name}"
    
    def _handle_api_error(self, response):
        """Handle API error responses."""
        error_body = response.read().decode()
        try:
            error_data = json.loads(error_body)
            message = error_data.get("message", "Unknown error")
            if "errors" in error_data:
                for error in error_data["errors"]:
                    message += f": {error.get('message', 'Unknown')}"
        except:
            message = error_body[:200]
        fail(f"GitHub API error: {message}")


class GitLabService:
    """Handles GitLab-specific repository operations."""
    
    def __init__(self, auth_handler):
        self.auth = auth_handler
    
    def create_repository(self, config, description, private):
        """Create GitLab repository via API."""
        user, token = self.auth.get_gitlab_credentials(config.target_host)
        
        headers = {
            "PRIVATE-TOKEN": token,
            "Content-Type": "application/json"
        }
        
        data = {
            "name": config.repo_name.replace('.git', ''),
            "visibility": "private" if private else "public",
            "description": description
        }
        
        try:
            conn = client.HTTPSConnection(config.target_host)
            body = json.dumps(data)
            conn.request("POST", "/api/v4/projects", body=body, headers=headers)
            response = conn.getresponse()
            
            if response.status == 201:
                return True
            else:
                self._handle_api_error(response)
                
        except Exception as e:
            fail(f"GitLab connection error: {e}")
    
    def fork_repository(self, config):
        """Fork GitLab repository - not supported."""
        fail("forking not supported for GitLab")
    
    def get_repository_url(self, config):
        """Get repository URL for GitLab."""
        user, _ = self.auth.get_gitlab_credentials(config.target_host)
        return f"ssh://git@{config.target_host}/{user}/{config.repo_name}"
    
    def _handle_api_error(self, response):
        """Handle API error responses."""
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
        except:
            message = error_body[:200]
        fail(f"GitLab API error: {message}")


class SSHService:
    """Handles SSH-based repository operations."""
    
    def create_repository(self, config, description, private):
        """Create repository on remote host via SSH."""
        parent_q = shell_escape(config.parent_path)
        repo_q = shell_escape(config.repo_name)
        desc_q = shell_escape(description)
        
        ssh_script = f"""cd "{parent_q}" &&
    mkdir -p "{repo_q}" &&
    cd "{repo_q}" &&
    git init --bare --shared=group &&
    echo "{desc_q}" >description &&
    if {str(not private).lower()} ; then
        touch git-daemon-export-ok &&
        if "{config.repo_link or ''}" != "" ; then
            ln -sf "{parent_q}/{repo_q}" "{config.repo_link}"/
        fi
    fi"""
        
        try:
            result = subprocess.run(["ssh", "-x", config.target_host, "sh"], 
                                  input=ssh_script, text=True, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as e:
            fail(f"SSH to {config.target_host} failed: {e.stderr}")
    
    def fork_repository(self, config):
        """Fork SSH repository - not supported."""
        fail("forking not supported for SSH repositories")
    
    def get_repository_url(self, config):
        """Get repository URL for SSH."""
        return f"ssh://{config.target_host}{config.parent_path}/{config.repo_name}"


# =============================================================================
# Service Factory
# =============================================================================

class ServiceFactory:
    """Factory for creating appropriate service instances."""
    
    @staticmethod
    def create_service(target_type, auth_handler):
        """Create service instance based on target type."""
        if target_type == "github":
            return GitHubService(auth_handler)
        elif target_type == "gitlab":
            return GitLabService(auth_handler)
        elif target_type in ["ssh", "custom"]:
            return SSHService()
        else:
            fail(f"unknown target type: {target_type}")


# =============================================================================
# Main Function
# =============================================================================

def parse_arguments():
    """Parse command line arguments."""
    ap = argparse.ArgumentParser(description="Create a new upstream git repository")
    ap.add_argument(
        "-p", "--private",
        help="make new repo private",
        action="store_true",
    )
    ap.add_argument(
        "-d", "--description",
        help="description line for new repo",
    )
    ap.add_argument(
        "-F", "--fork",
        help="instead of a new repo, make a new upstream fork",
        action="store_true",
    )
    ap.add_argument(
        "-X", "--site",
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
    return ap.parse_args()


def list_available_sites():
    """List available sites and usage examples."""
    sites = SiteConfiguration.list_sites()
    print("Available sites:", ", ".join(sites), file=sys.stderr)
    print("Usage examples:", file=sys.stderr)
    print("  mkgit -X github myrepo", file=sys.stderr)
    print("  mkgit -X gitlab myrepo", file=sys.stderr)
    print("  mkgit -X github-org myrepo", file=sys.stderr)
    print("  mkgit ssh://user@host/path/repo.git", file=sys.stderr)


def setup_working_directory(args):
    """Setup and validate working directory."""
    original_dir = Path.cwd()
    
    if args.source_dir:
        source_dir = Path(args.source_dir).resolve()
        if not (source_dir / ".git").exists():
            fail(f"directory {source_dir} is not a git working directory!")
        os.chdir(source_dir)
    else:
        source_dir = Path.cwd()
        if not (source_dir / ".git").exists():
            fail(f"current directory is not a git working directory!")
    
    return source_dir


def main():
    """Main entry point for the mkgit command."""
    args = parse_arguments()
    
    if args.list_sites:
        list_available_sites()
        exit(0)
    
    # Setup components
    home = Path.home()
    auth_handler = AuthHandler(home)
    git_ops = GitOperations()
    
    # Setup and validate working directory
    source_dir = setup_working_directory(args)
    
    # Get repository configuration
    config = RepositoryConfig(args)
    
    # Validate current branch
    current_branch = git_ops.get_current_branch()
    
    # Get repository description
    description = git_ops.get_description(args.description)
    
    # Create or fork repository
    service = ServiceFactory.create_service(config.target_type, auth_handler)
    
    if args.fork:
        if config.target_type != "github":
            fail("forking only supported for GitHub")
        repo_url = service.fork_repository(config)
    else:
        service.create_repository(config, description, args.private)
        repo_url = service.get_repository_url(config)
    
    # Setup git remotes and push
    git_ops.setup_remote(repo_url, source_dir)
    git_ops.push_to_remote(current_branch, source_dir)
    
    print(f"Successfully created and pushed to {repo_url}")


if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
