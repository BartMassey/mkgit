# mkgit
Copyright (c) 2012 Bart Massey

---

**Note:** *The latest version of this package changed the
`HOST` variable in mkgit customization scripts: it is now
called `GITHOST`. Please adjust your scripts accordingly.

---

This tool, based on an idea by Julian Kongslie, creates a
new git repository on an upstream host and pushes the
current repository up to it, setting everything up so that
the upstream host is now being tracked. Both Python (`mkgit`)
and shell (`mkgit.sh`) versions are available, with the Python
version being the primary implementation and the shell script
retained for legacy compatibility.

You must have appropriate access (ssh for custom hosts, API tokens
for GitHub/GitLab) to create repositories on your target host.

## Installation

To install the Python version of mkgit:

```bash
# Install the main script
sudo cp mkgit.py /usr/local/bin/mkgit
sudo chmod +x /usr/local/bin/mkgit

# Install site configuration files (optional)
sudo cp mkgit-* /usr/local/bin/
sudo chmod +x /usr/local/bin/mkgit-*
```

The site configuration files (like `mkgit-big-site` and `mkgit-little-site`) 
must be in the same directory as the `mkgit` executable for custom
site support to work. These files contain variable assignments like:

```
GITHOST=big-site.example.org
PARENT=/storage/git
REPOLINK=/var/git-links
```

## Usage Examples

Create a GitHub repository:
```bash
mkgit -d "My new project" -X github my-project
```

Create a private GitLab repository:
```bash
mkgit -p -X gitlab my-project
```

Create a repository on a custom SSH host:
```bash
mkgit ssh://user@gitlab.example.com/git/storage/my-project.git
```

Fork an existing GitHub repository:
```bash
mkgit -F -X github
```

## Command Line Interface

```bash
usage: mkgit [-h] [-p] [-d DESCRIPTION] [-F] [-X SITE] [--list-sites]
            [repo] [source_dir]

Create a new upstream git repository

positional arguments:
  repo                  name of repository (with or without .git)
  source_dir            source directory (defaults to current directory)

options:
  -h, --help            show help message and exit
  -p, --private         make new repo private
  -d, --description DESCRIPTION
                        description line for new repo
  -F, --fork            instead of a new repo, make a new upstream fork
  -X, --site SITE       site for new repo (use --list-sites for options)
  --list-sites          list available site options
```

### Site Options

- `github` - Create repository on github.com
- `gitlab` - Create repository on gitlab.com
- `github-org` - Create repository in specific GitHub organization
- `gitlab-host-org` - Create repository on specific GitLab instance for organization
- `ssh://host/path/repo.git` - Create repository via SSH on custom host

Available sites can be listed with `--list-sites`.

### Authentication Requirements

**GitHub:** 
- Create `~/.githubuser` with your username
- Create `~/.github-oauthtoken` with GitHub personal access token

**GitLab:**
- Create `~/.gitlabuser-<host>` with your username
- Create `~/.gitlabtoken-<host>` with GitLab personal access token

**Custom SSH:** SSH key authentication to target host

### Typical Use Cases

1. **Public GitHub Repository:**
   ```bash
   cd my-new-project
   mkgit -d "Description from first commit" -X github
   ```

2. **Private GitLab Repository:**
   ```bash
   cd existing-project
   mkgit -p -d "Internal project" -X gitlab private-project
   ```

3. **Custom Host Repository:**
   ```bash
   cd local-project
   mkgit ssh://user@git.example.com/projects/my-project.git
   ```

4. **Fork GitHub Repository:**
   ```bash
   cd upstream-project
   mkgit -F -X github
   ```

5. **Repository in Organization:**
   ```bash
   cd team-project
   mkgit -d "Team project" -X github-org myorg
   ```

## Custom Sites

The "magic -X modes" can be customized by putting site variable
definitions in `mkgit-<site>` scripts in the same directory as
the `mkgit` executable. See `mkgit-big-site` and `mkgit-little-site` for
examples. All of this is fragile and a bit experimental:
patches welcome.

Each site configuration file can set these variables:
- `GITHOST` - Target hostname
- `PARENT` - Parent directory path on target
- `REPOLINK` - Directory for repository symlinks (optional)

Site configuration files must have executable permissions and be in the same
directory as the main `mkgit` script.

This work is under the "MIT license". See the file LICENSE.txt
in the source distribution for license terms.