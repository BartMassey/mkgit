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


def fail(msg):
    """Print error message and exit with status 1."""
    print("mkgit:", msg, file=sys.stderr)
    exit(1)


def warn(msg):
    """Print warning message to stderr."""
    print("mkgit: warning:", msg, file=sys.stderr)


def read_oneliner(path):
    """Read and return contents of single-line file."""
    try:
        with open(path, "r") as f:
            result = f.read().strip()
            if len(result.splitlines()) > 1:
                fail(f"{path}: expected one line")
            return result
    except Exception as e:
        fail(f"error reading {path}: {e}")


def git_command(*args, verbose=True):
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


def find_site_scripts():
    """Find site scripts in site directory."""
    # Check environment variable first
    env_dir = os.environ.get('MKGIT_SITE_DIR')
    if env_dir:
        script_dirs = [Path(env_dir)]
    else:
        # Default search paths
        script_dirs = [
            Path("/usr/local/share/mkgit"),
            Path(__file__).parent  # fallback to script directory
        ]
    
    scripts = []
    for script_dir in script_dirs:
        if script_dir.exists() and script_dir.is_dir():
            for file in script_dir.glob("mkgit-*"):
                if file.is_file():
                    scripts.append(file.name)
    return scripts


def list_sites():
    """Return list of available site options."""
    sites = ["github", "gitlab"]
    site_scripts = find_site_scripts()
    for script in site_scripts:
        site_name = script.replace("mkgit-", "")
        sites.append(site_name)
    return sites


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
    
    status, branch_output = git_command("branch")
    if status != 0:
        fail("could not get current branch")
        
    current_branch = None
    for line in branch_output.splitlines():
        if line.startswith("* "):
            current_branch = line[2:]
            break
    
    if not current_branch:
        fail("could not determine current_branch")
    
    if current_branch not in ["master", "main"]:
        fail(f"invalid main branch {current_branch}, must be master or main")
    
    description = args.description
    if not description:
        status, desc_output = git_command("log", "--pretty=%s", current_branch)
        if status == 0 and desc_output.strip():
            description = desc_output.strip().split('\n')[-1]
        else:
            description = f"Repository {source_dir.name}"
    
    target_type = None
    target_host = None
    org = None
    parent_path = None
    repo_link = None
    repo_name = args.repo if args.repo else source_dir.name
    if not repo_name.endswith('.git'):
        repo_name += '.git'
    
    if args.site:
        if args.site.startswith("github") or args.site.startswith("gitlab"):
            match = re.match(r'^(github|gitlab)(?:-([^-]+)(?:-([^-]+))?)?$', args.site)
            if match:
                service = match.group(1)
                if service == "github":
                    target_host = "github.com"
                    org = match.group(3) if match.group(3) else None
                elif service == "gitlab":
                    if match.group(3):
                        target_host = match.group(2)
                        org = match.group(3)
                    elif match.group(2):
                        if '.' in match.group(2):
                            target_host = match.group(2)
                            org = None
                        else:
                            target_host = "gitlab.com"
                            org = match.group(2)
                    else:
                        target_host = "gitlab.com"
                        org = None
                else:
                    fail(f"internal error: unknown service {service}")
                target_type = service
        elif args.site.startswith("ssh://"):
            target_type = "ssh"
            ssh_url = args.site
            git_match = re.match(r'ssh://([^/]*)', ssh_url)
            parent_match = re.match(r'ssh://[^/]*(/.*)/', ssh_url)
            proj_match = re.match(r'ssh://[^/]*/.*/([^/]*\.git)$', ssh_url)
            
            if not proj_match:
                proj_match = re.match(r'ssh://[^/]*/.*/([^/.]*)$', ssh_url)
            
            if git_match and parent_match and proj_match:
                target_host = git_match.group(1)
                parent_path = parent_match.group(1)
                repo_name = proj_match.group(1)
                if not repo_name.endswith('.git'):
                    repo_name += '.git'
            else:
                fail(f"bad SSH URL: {ssh_url}")
        else:
            target_type = "custom"
            site_name = args.site
            
            # Find site configuration file using same logic as find_site_scripts
            env_dir = os.environ.get('MKGIT_SITE_DIR')
            if env_dir:
                search_dirs = [Path(env_dir)]
            else:
                search_dirs = [
                    Path("/usr/local/share/mkgit"),
                    Path(__file__).parent  # fallback to script directory
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
            
            target_host = script_vars.get('GITHOST')
            parent_path = script_vars.get('PARENT', '')
            repo_link = script_vars.get('REPOLINK')
            
            if not target_host:
                fail("site script must set GITHOST")
    
    # Handle SSH URLs as positional arguments (when no -X flag)
    if target_type is None and args.repo and args.repo.startswith("ssh://"):
        ssh_url = args.repo
        git_match = re.match(r'ssh://([^/]*)', ssh_url)
        parent_match = re.match(r'ssh://[^/]*(/.*)/', ssh_url)
        proj_match = re.match(r'ssh://[^/]*/.*/([^/]*\.git)$', ssh_url)
        
        if not proj_match:
            proj_match = re.match(r'ssh://[^/]*/.*/([^/.]*)$', ssh_url)
        
        if git_match and parent_match and proj_match:
            target_type = "ssh"
            target_host = git_match.group(1)
            parent_path = parent_match.group(1)
            repo_name = proj_match.group(1)
            if not repo_name.endswith('.git'):
                repo_name += '.git'
        else:
            fail(f"bad SSH URL: {ssh_url}")
    
    def create_github_repo(user, token, org, repo, description, private):
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
            
            conn = client.HTTPSConnection("api.github.com")
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
                except:
                    message = error_body[:200]
                fail(f"GitHub API error: {message}")
                
        except Exception as e:
            fail(f"GitHub connection error: {e}")
    
    
    def fork_github_repo(user, token, org, repo):
        """Fork GitHub repository via API."""
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
        
        source_user = origin_match.group(1)  # type: ignore
        source_repo = origin_match.group(2).replace('.git', '')  # type: ignore
        
        # Determine fork organization
        fork_org = org if org else f"{user}-upstream"
        
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
                error_body = response.read().decode()
                fail(f"GitHub fork failed: {error_body}")
                
        except Exception as e:
            fail(f"GitHub fork error: {e}")
    
    
    def create_gitlab_repo(user, token, host, repo, description, private):
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
                except:
                    message = error_body[:200]
                fail(f"GitLab API error: {message}")
                
        except Exception as e:
            fail(f"GitLab connection error: {e}")
    
    
    def get_gitlab_token(host, user):
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
    
    
    def create_ssh_repo(host, parent_path, repo_name, description, private, repo_link=None):
        """Create repository on remote host via SSH."""
        # Escape special characters for shell
        def shell_escape(s):
            return s.replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
        
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
    
    
    remote_url = None
    
    if args.fork:
        if target_type != "github":
            fail("forking only supported for GitHub")
        
        user = read_oneliner(home / ".githubuser")
        token = read_oneliner(home / ".github-oauthtoken")
        remote_url = fork_github_repo(user, token, org, repo_name.replace('.git', ''))
        
    elif target_type == "github":
        user = read_oneliner(home / ".githubuser")
        token = read_oneliner(home / ".github-oauthtoken")
        create_github_repo(user, token, org, repo_name, description, args.private)
        gh_org = org if org else user
        remote_url = f"ssh://git@github.com/{gh_org}/{repo_name}"
    
    elif target_type == "gitlab":
        gitlab_user_file = home / f".gitlabuser-{target_host}"
        if not gitlab_user_file.exists():
            fail(f"need {gitlab_user_file}")
        
        user = read_oneliner(gitlab_user_file)
        token = get_gitlab_token(target_host, user)
        create_gitlab_repo(user, token, target_host, repo_name, description, args.private)
        remote_url = f"ssh://git@{target_host}/{user}/{repo_name}"
    
    elif target_type == "ssh":
        create_ssh_repo(target_host, parent_path, repo_name, description, args.private)
        remote_url = f"ssh://{target_host}{parent_path}/{repo_name}"
    
    elif target_type == "custom":
        create_ssh_repo(target_host, parent_path, repo_name, description, args.private, repo_link)
        remote_url = f"ssh://{target_host}{parent_path}/{repo_name}"
    
    else:
        fail("no target site specified")
    
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

if __name__ == "__main__":
    main()
