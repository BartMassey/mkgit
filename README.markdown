# mkgit
Copyright &copy; 2012 Bart Massey

This script, based on an idea by Julian Kongslie, creates a
new git repository on an upstream host and pushes the
current repository up to it, setting everything up so that
the upstream host is now being tracked. Oddly, you must have
ssh access to upstream to use this.

Options include: "magic -X modes" customizable for
particular upstreams; public or private repositories; and a
bunch of clever defaulting. In particular, the "-X github"
switch is convenient for pushing there: it uses the GitHub
API to create the new repo before pushing. Say "mkgit -h"
for details on all of this.

This work is under an MIT license. See
[opensource.org](http://opensource.org/licenses/mit-license.php)
for licensing information.
