#!/bin/sh
# Copyright © 2012 Bart Massey
# [This program is licensed under the "MIT License"]
# Please see the file COPYING in the source
# distribution of this software for license terms.

# Apply a license to files of an open source program.
# Loosely based on an earlier script by Julian Kongslie

PGM="`basename $0`"

# The site scripts live in the same bin with mkgit.
# They are named mkgit-*.
BIN="`echo $0 | sed 's=/*[^/]*$=='`"
case $BIN in '') BIN='.' ;; esac
SITESCRIPTS="`ls \"$BIN\" | egrep '^mkgit-'`"
# Pipe-separated list of site names. Used both for
# display and with shell eval.
SITES="`echo $SITESCRIPTS | sed -e 's=mkgit-==g' -e 's= =|=g'`"

USAGE="$PGM: usage:
  $PGM [-p|-d <desc>]
  [ -X ${SITES:+$SITES|}github|gitlab [<project>[.git]]
  | ssh://[<user>@]host/<dir>/<project>[.git]]
  [<source-dir>]"

# Set by site script: symlinked name for repo.
REPOLINK=""
# Repos must be specified as either "public" (will be made
# visible to all) or "private" (will be made visible only
# to those with commit access).
PUBLIC=true
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
	DESC="$2"
	shift 2
	;;
    -p)
        PUBLIC=false
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

# Finalize the project description.
case "$DESC" in
  "")    
    # If no description, dig the description out of
    # the initial git commit.
    DESC="`git log --pretty="%s" master | tail -1`"
    if [ $? -ne 0 ]
    then
        echo "$PGM: could not get a project description" >&2
        exit 1
    fi
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
github|gitlab)
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

# Either execute the special-case code to set up a Github or
# Gitlab repo, or use the now-established HOST, PARENT and
# PROJECT to set up a repo using ssh.
case $X in
github)
    if echo "$PROJECT" | grep / >/dev/null
    then
        echo "$PGM: error: Github name should not be a pathname" >&2
        exit 1
    fi
    if ! $PUBLIC && [ ! -f "$HOME/.githubprivate" ]
    then
	echo "$PGM: cannot create private github repos for licensing reasons" >&2
	exit 1
    fi
    GITHUBUSER="`cat $HOME/.githubuser`"
    if [ $? -ne 0 ]
    then
	echo "$PGM: need \$HOME/.githubuser" >&2
	exit 1
    fi
    if [ ! -s "$HOME/.github-oauthid" ] || [ ! -s "$HOME/.github-oauthtoken" ]
    then
        RESP="`curl -f -i -u \"$GITHUBUSER\" \
          -d '{ \"scopes\": [ \"repo\" ], \"note\": \"mkgit\" }' \
          https://api.github.com/authorizations`"
        if [ $? -ne 0 ]
        then
            echo "Github authentication failed" >&2
            exit 1
        fi
        if echo "$RESP" | grep -q "X-GitHub-OTP: required;" 
        then
            echo "two-factor authentication enabled" >&2 &&
            read -p "Enter authentication code: " CODE >&2 &&
            RESP2="`curl -f -i -u \"$GITHUBUSER\" -H \"X-GitHub-OTP: $CODE;\" \
              -d '{ \"scopes\": [ \"repo\" ], \"note\": \"mkgit\" }' \
              https://api.github.com/authorizations`" &&
            echo "$RESP2" | jq -r .token > $HOME/.github-oauthtoken &&
            echo "$RESP2" | jq -r .id > $HOME/.github-oauthid
        else
            echo "$RESP" | jq -r .token > $HOME/.github-oauthtoken &&
            echo "$RESP" | jq -r .id > $HOME/.github-oauthid
        fi
        if [ $? -ne 0 ] || [ ! -s "$HOME/.github-oauthid" ] ||
                           [ ! -s "$HOME/.github-oauthtoken" ]
        then
            echo "$PGM: failed to get a GitHub OAuth2 authorization token" >&2
            rm -f "$HOME/.github-oauthtoken"
            rm -f "$HOME/.github-oauthid"
            exit 1
        fi
        chmod 0600 "$HOME/.github-oauthtoken"
        chmod 0600 "$HOME/.github-oauthid"
    fi
    GITHUBTOKEN="`cat $HOME/.github-oauthtoken`"
    ESCDESC="`echo \"$DESC\" | sed -e 's/\\\\/\\\\\\\\/g' -e 's/"/\\\\"/g'`"
    curl -f -H "Authorization: token $GITHUBTOKEN" \
         -d "{ \"user\": \"$GITHUBUSER\",
               \"user_secret\": \"$GITHUBTOKEN\",
               \"name\": \"$PROJECT\",
               \"description\": \"$ESCDESC\" }" \
         https://api.github.com/user/repos >/dev/null
    if [ $? -ne 0 ]
    then
	echo "failed to create github repository: API error" >&2
	exit 1
    fi
    URL="ssh://git@github.com/$GITHUBUSER/$PROJECT"
    ;;
gitlab)
    if echo "$PROJECT" | grep / >/dev/null
    then
        echo "$PGM: error: Gitlab name should not be a pathname" >&2
        exit 1
    fi
    GITLABUSER="`cat $HOME/.gitlabuser`"
    if [ $? -ne 0 ]
    then
	echo "$PGM: need \$HOME/.gitlabuser" >&2
	exit 1
    fi
    if [ ! -f "$HOME/.gitlab-token" ]
    then
        # XXX The horrors of prompting for a password.
        # http://stackoverflow.com/a/28393320/364875
        trap "stty echo" 0
        stty -echo
        read -r -p "Gitlab password: " GITLAB_PASSWORD
        stty echo
        trap - 0
        echo ""
        RESP="`curl -f \
          --data \"login=$GITLABUSER\" \
          --data-urlencode \"password=$GITLAB_PASSWORD\" \
          https://gitlab.com/api/v3/session`"
        if [ $? -ne 0 ]
        then
            echo "Gitlab authentication failed" >&2
            exit 1
        fi
        echo "$RESP" | jq -r .private_token > $HOME/.gitlab-token
        if [ $? -ne 0 ] || [ ! -s "$HOME/.gitlab-token" ]
        then
            echo "$PGM: failed to get a Gitlab private token" >&2
            rm -f "$HOME/.gitlab-token"
            exit 1
        fi
        chmod 0600 "$HOME/.gitlab-token"
    fi
    GITLABTOKEN="`cat $HOME/.gitlab-token`"
    PROJECTBASE="`basename \"$PROJECT\" .git`"
    if curl -f -H "PRIVATE-TOKEN: $GITLABTOKEN" \
        --data "name=$PROJECTBASE" \
        --data "public=$PUBLIC" \
        --data-urlencode "description=$DESC" \
        https://gitlab.com/api/v3/projects >/dev/null
    then
        :
    else
	echo "failed to create gitlab repository: curl error" >&2
	exit 1
    fi
    URL="ssh://git@gitlab.com/$GITLABUSER/$PROJECT"
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
    ssh -x "$HOST" sh <<EOF
    cd "${PARENTQ}" &&
    mkdir -p "${PROJECTQ}" &&
    cd "${PROJECTQ}" &&
    git init --bare --shared=group &&
    echo "${DESC}" >description &&
    if ${PUBLIC}
    then
        touch git-daemon-export-ok &&
        if [ "${REPOLINK}" != "" ]
        then
            ln -s "${PARENTQ}/${PROJECTQ}" "${REPOLINK}"/.
        fi
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
