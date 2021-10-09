# mkgit
Copyright (c) 2012 Bart Massey

---

**Note:** *The latest version of this package changed the
`HOST` variable in mkgit customization scripts: it is now
called `GITHOST`. Please adjust your scripts accordingly.

---

This script, based on an idea by Julian Kongslie, creates a
new git repository on an upstream host and pushes the
current repository up to it, setting everything up so that
the upstream host is now being tracked. Oddly, you must have
ssh access to upstream to use this.

Options include: "magic -X modes" customizable for
particular upstreams; public or private repositories; and a
bunch of clever defaulting. In particular, the "-X github"
and "-X gitlab" switches are convenient for pushing to these
places: see the manual page for details.

The "magic -X modes" can be customized by putting site variable
definitions in mkgit-<site> in the same bin directory as
mkgit. See mkgit-big-site and mkgit-little-site for
examples. All of this is fragile and a bit experimental:
patches welcome.

This work is under the "MIT license". See the file COPYING
in the source distribution for licensing information.
