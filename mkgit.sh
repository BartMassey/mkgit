#!/bin/sh
# Copyright © 2009 Bart Massey
# ALL RIGHTS RESERVED
#
# This program is released under the MIT license
# See http://opensource.org/licenses/mit-license.php for
# licensing information
#
# Loosely based on an earlier script by Julian Kongslie

PGM="`basename $0`"

# The site scripts live in the same bin with mkgit.
# They are named mkgit-*.
BIN="`echo $0 | sed 's=/*[^/]*$=='`"
case $BIN in '') BIN='.' ;; esac
SITESCRIPTS="`ls \"$BIN\" | egrep '^mkgit-'`"
# Pipe-separated list of site names. Used both for
# display and with shell eval.
SITES="`echo $SITESCRIPTS | sed -e 's=mkgit-==g' -e 's= =|='`"

USAGE="$PGM: usage:
  $PGM [-p|-d <desc>]
  [ -X ${SITES:+$SITES|}github [<project>[.git]]
  | ssh://[<user>@]host/<dir>/<project>[.git]]
  [<source-dir>]"

# Set by site script: symlinked name for repo.
REPOLINK=""
# Repos must be specified as either "public" (will be made
# visible to all) or "private" (will be made visible only
# to those with commit access).
PRIVATE=false
PUBLIC=false
# Optional "special" site name that receives
# custom handling.
X=""

# Parse arguments.
while [ $# -gt 0 ]
do
    case "$1" in
    -X)
	X="$2"
	shift 2
	;;
    -d)
        PUBLIC=true
	DESC="$2"
	shift 2
	;;
    -p)
        PRIVATE=true
	shift
	;;
    -*)
	echo "$USAGE" >&2
	exit 1
	;;
    *)
	break
	;;
    esac
done

# Check that there are few enough arguments left over
# to make sense.
if [ $# -gt 2 ]
then
    echo "$USAGE" >&2
    exit 1
fi

# Check for screwups with public/private.
case $PUBLIC:$PRIVATE in
true:true)
    echo "$PGM: both public (-d <desc>) and private (-p) were specified" >&2
    exit 1
    ;;
false:false)
    echo "$PGM: neither public (-d <desc>) nor private (-p) was specified" >&2
    exit 1
    ;;
esac

# Parse and rearrange to try to get things in a reasonable
# order.

# This may be empty if there are 0 extra arguments, in
# which case we will default it appropriately.
TARGET="$1"
if [ $# -eq 0 ]
then
    TARGET="`basename \"\`pwd\`\"`"
fi

# Try to get the PROJECT (i.e., repo name on target machine)
# set up successfully. In the non-special case, also set up
# HOST and PARENT for the upcoming ssh. Note in particular
# the handling for the scripted special case, which sources
# the script for some of these variables.
case $X in
github)
    PROJECT="$TARGET"
    ;;
"")
    if [ $# -eq 0 ]
    then
        echo "$USAGE" >&2
        exit 1
    fi
    HOST="`expr \"$TARGET\" : 'ssh://\([^/]*\)'`"
    PARENT="`expr \"$TARGET\" : 'ssh://[^/]*\(/.*\)/'`"
    PROJECT="`expr \"$TARGET\" : 'ssh://[^/]*/.*/\([^/]*\.git$\)'`"
    if [ "$PROJECT" = "" ]
    then
        PROJECT="`expr \"$TARGET\" : 'ssh://[^/]*/.*/\([^/.]*$\)'`"
    fi
    if [ "$HOST" = "" ] || [ "$PARENT" = "" ] || [ "$PROJECT" = "" ]
    then
        echo "$PGM: bad repo target URL \"$TARGET\", giving up" >&2
        exit 1
    fi
    ;;
*)
    PROJECT="$TARGET"
    eval "case $X in
    $SITES)
        . $BIN/mkgit-$X
        X=''
        ;;
    *)
        echo \"$PGM: unknown -X target \\\"$X\\\", giving up\" >&2
        exit 1
        ;;
    esac"
esac

# For now, canonicalize target machine repo names to
# always end in ".git". May revisit later.
case "$PROJECT" in
*.git)
    ;;
*)
    echo "adding .git to project yielding $PROJECT.git"
    PROJECT="$PROJECT".git
    ;;
esac


# Find the Git working directory on local machine to be
# cloned (usually the current directory).
SRCDIR="."
if [ $# -eq 2 ]
then
    SRCDIR="$2"
fi
cd "$SRCDIR"
if [ "$?" -ne 0 ]
then
    echo "$PGM: could not find git directory $SRCDIR" >&2
    exit 1
fi
if [ ! -d ".git" ]
then
    echo "$PGM: directory $SRCDIR is not a git working directory!" 1>&2
    exit 1
fi

# Either execute the special-case code to set up a Github
# repo, or use the now-established HOST, PARENT and PROJECT
# to set up a repo using ssh.
case $X in
github)
    if echo "$PROJECT" | grep / >/dev/null
    then
        echo "$PGM: error: GitHub name should not be a pathname" >&2
        exit 1
    fi
    if $PRIVATE && [ ! -f "$HOME/.githubprivate" ]
    then
	echo "$PGM: cannot create private github repos for licensing reasons" >&2
	exit 1
    fi
    if [ ! -f "$HOME/.githubuser" ]
    then
	echo "$PGM: need \$HOME/.githubuser" >&2
	exit 1
    fi
    GITHUBUSER="`cat $HOME/.githubuser`"
    if [ ! -f "$HOME/.github-oauthtoken" ]
    then
      curl -u "$GITHUBUSER" \
        -d '{ "scopes": [ "repo" ], "note": "mkgit" }' \
        https://api.github.com/authorizations |
      awk -F '[:, ]+' '
      $2=="\"token\"" { print substr($3, 2, length($3) - 2) > HOME "/.github-oauthtoken"; }
      $2=="\"id\"" { print substr($3, 2, length($3) - 2) > HOME "/.github-oauthid"; }
      ' HOME="$HOME"
      if [ $? -ne 0 ] || [ ! -s "$HOME/.github-oauthtoken" ]
      then
          echo "$PGM: failed to get a GitHub OAuth2 authorization token" >&2
          exit 1
      fi
      chmod 0600 "$HOME/.github-oauthtoken"
      chmod 0600 "$HOME/.github-oauthid"
    fi
    GITHUBTOKEN="`cat $HOME/.github-oauthtoken`"
    OPTIONAL_DESCRIPTION=""
    if $PUBLIC
    then
        OPTIONAL_DESCRIPTION="
              \"description\": \"$DESC\",
"
    fi
    MSGTMP="/tmp/mkgit-curlmsg.$$"
    trap "rm -f $MSGTMP" 0 1 2 3 15
    if curl -H "Authorization: token $GITHUBTOKEN" \
        -d "{ \"user\": \"$GITHUBUSER\",
              \"user_secret\": \"$GITHUBTOKEN\",
              \"name\": \"$PROJECT\",
              $OPTIONAL_DESCRIPTION
              \"has_wiki\": false }" \
        https://api.github.com/user/repos >$MSGTMP
    then
	:
    else
	echo "failed to create github repository:" >&2
	cat $MSGTMP >&2
	exit 1
    fi
    URL="ssh://git@github.com/$GITHUBUSER/$PROJECT"
    ;;
"")
    if [ "$HOST" = "" ] || [ "$PARENT" = "" ] || [ "$PROJECT" = "" ]
    then
        echo "$PGM: insufficient info to proceed (internal error?)" >&2
        exit 1
    fi
    URL="ssh://$HOST$PARENT/$PROJECT"
    QUOTESTR="s/\\([\"\'\!\$\\\\]\\)/\\\\\\1/g"
    PARENTQ="`echo \"$PARENT\" | sed \"$QUOTESSTR\"`"
    PROJECTQ="`echo \"$PROJECT\" | sed \"$QUOTESSTR\"`"
    ssh "$HOST" <<EOF
    cd "${PARENTQ}" &&
    mkdir -p "${PROJECTQ}" &&
    cd "${PROJECTQ}" &&
    git init --bare --shared=group &&
    if ${PUBLIC}
    then
      touch git-daemon-export-ok
      echo "${DESC}" >description
      [ "${REPOLINK}" != "" ] && ln -s "${PARENTQ}/${PROJECTQ}" "${REPOLINK}"/.
    fi
EOF
    if [ "$?" -ne 0 ]
    then
	echo "$PGM: ssh to create repo failed" >&2
	exit 1
    fi
    ;;
*)
    echo "$PGM: internal error: unexpected -X $X" >&2
    exit 1
    ;;
esac

# Push the source repo up to the newly-created target repo.
if git remote add origin "$URL"
then
  :
else
  echo "$PGM: warning: updating remote"
  git remote rm origin
  git remote add origin "$URL"
fi
git push -u origin master
if [ "$?" -ne 0 ]
then
    echo "$PGM: push to origin failed" >&2
    exit 1
fi

exit 0
