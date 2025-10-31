#!/bin/sh
# Copyright © 2012 Bart Massey
# [This program is licensed under the "MIT License"]
# Please see the file LICENSE.txt in the source
# distribution of this software for license terms.

# Create a new upstream git repository.
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
  [ -X ${SITES:+$SITES|}github[-<org>]|gitlab[-<org>] [-F] [<project>[.git]]
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
# Fork existing repo instead of making new one.
FORK=false

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
    -F)
        FORK=true
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

# Find and validate the current branch.
BRANCH="`git branch | sed -e '/^* /!d' -e 's/^* //'`"
case "$BRANCH" in
    master|main)
        ;;
    *)
        echo "invalid main branch $BRANCH" >&2
        exit 1
        ;;
esac

# Finalize the project description.
case "$DESC" in
  "")    
    # If no description, dig the description out of
    # the initial git commit.
    DESC="`git log --pretty="%s" $BRANCH | tail -1`"
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
# GITHOST and PARENT for the upcoming ssh. Note in particular
# the handling for the scripted special case, which sources
# the script for some of these variables.
case $X in
github*|gitlab*)
    PROJECT="$TARGET"
    case $X in
        github|gitlab)
            SERVICE="$X"
            ;;
        github-*)
            GITORG="`echo $X | sed 's/git...-//'`"
            SERVICE=github
            ;;
        gitlab-*)
            SUFFIX="`echo $X | sed 's/git...-//'`"
            case "$SUFFIX" in
                *.*-*)
                    GITHOST="`echo $SUFFIX | sed 's/-.*//'`"
                    GITORG="`echo $SUFFIX | sed 's/[a-z.][a-z.]*-//'`"
                    ;;
                *.*)
                    GITHOST="$SUFFIX"
                    ;;
                *)
                    GITORG="$SUFFIX"
                    ;;
            esac
            SERVICE=gitlab
            ;;
    esac
    ;;
"")
    if [ $# -eq 0 ]
    then
        echo "$USAGE" >&2
        exit 1
    fi
    GITHOST="`expr \"$TARGET\" : 'ssh://\([^/]*\)'`"
    PARENT="`expr \"$TARGET\" : 'ssh://[^/]*\(/.*\)/'`"
    PROJECT="`expr \"$TARGET\" : 'ssh://[^/]*/.*/\([^/]*\.git$\)'`"
    if [ "$PROJECT" = "" ]
    then
        PROJECT="`expr \"$TARGET\" : 'ssh://[^/]*/.*/\([^/.]*$\)'`"
    fi
    if [ "$GITHOST" = "" ] || [ "$PARENT" = "" ] || [ "$PROJECT" = "" ]
    then
        echo "$PGM: bad repo target URL \"$TARGET\", giving up" >&2
        exit 1
    fi
    ;;
*)
    PROJECT="$TARGET"
    case $X in
    $SITES)
        eval `. $BIN/mkgit-\"$X\"`
        ;;
    *)
        echo "$PGM: unknown -X target \"$X\", giving up" >&2
        exit 1
        ;;
    esac
    ;;
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
# Gitlab repo, or use the now-established GITHOST, PARENT and
# PROJECT to set up a repo using ssh.
case $SERVICE in
github)
    if echo "$PROJECT" | grep / >/dev/null
    then
        echo "$PGM: error: Github name should not be a pathname" >&2
        exit 1
    fi
    GITHUBUSER="`cat $HOME/.githubuser`"
    if [ $? -ne 0 ]
    then
	echo "$PGM: need \$HOME/.githubuser" >&2
	exit 1
    fi
    if [ ! -s "$HOME/.github-oauthtoken" ]
    then
        echo "no $HOME/.github-oauthtoken: see docs" >&2
        exit 1
    fi
    GITHUBTOKEN="`cat $HOME/.github-oauthtoken`"
    ESCDESC="`echo \"$DESC\" | sed -e 's/\\\\/\\\\\\\\/g' -e 's/"/\\\\"/g'`"
    if $FORK
    then
        ORIGIN="`git remote get-url origin`"
        TARGETUSER="`echo \"$ORIGIN\" | sed 's=.*://[^/]*/\([^/]*\)/.*=\1='`"
        PROJECT="`echo \"$ORIGIN\" | sed 's=.*/\([^/]*\)/*$=\1='`"
        FORKURL="https://api.github.com/repos/$TARGETUSER/$PROJECT/forks"
        echo "$FORKURL"
        if [ "$GITORG" = "" ]
        then
            GITORG=$GITHUBUSER-upstream
        fi
        if ! $PUBLIC
        then
            echo "forks must be public" >&2
            exit 1
        fi
        curl -f -H "Authorization: token $GITHUBTOKEN" \
             -d "{ \"user\": \"$GITHUBUSER\",
                   \"user_secret\": \"$GITHUBTOKEN\",
                   \"organization\": \"$GITORG\" }" \
             $FORKURL >/dev/null
    else
        CREATEURL=https://api.github.com/user/repos
        if [ "$GITORG" = "" ]
        then
            GITORG=$GITHUBUSER
        else
            CREATEURL=https://api.github.com/orgs/$GITORG/repos
        fi
        case $PUBLIC in
            true) PRIVATE=false ;;
            false) PRIVATE=true ;;
            *) echo "bad PUBLIC" >&2; exit 1 ;;
        esac
        curl -f -H "Authorization: token $GITHUBTOKEN" \
             -d "{ \"user\": \"$GITHUBUSER\",
                   \"user_secret\": \"$GITHUBTOKEN\",
                   \"name\": \"$PROJECT\",
                   \"description\": \"$ESCDESC\",
                   \"private\": $PRIVATE }" \
             $CREATEURL >/dev/null
    fi
    if [ $? -ne 0 ]
    then
	echo "failed to create/fork github repository: API error" >&2
	exit 1
    fi
    URL="ssh://git@github.com/$GITORG/$PROJECT"
    ;;
gitlab)
    if $FORK
    then
        echo "cannot fork gitlab yet" >&2
        exit 1
    fi
    if echo "$PROJECT" | grep / >/dev/null
    then
        echo "$PGM: error: Gitlab name should not be a pathname" >&2
        exit 1
    fi
    GITHOST=${GITHOST-gitlab.com}
    GITLABUSER="`cat $HOME/.gitlabuser-$GITHOST`"
    if [ $? -ne 0 ]
    then
	echo "$PGM: need \$HOME/.gitlabuser-$GITHOST" >&2
	exit 1
    fi
    if [ ! -f "$HOME/.gitlab-token-$GITHOST" ]
    then
        stty -echo
        read -p "Gitlab password: " GITLAB_PASSWORD
        stty echo
        echo ""
        RESP="`curl -f \
          --data \"login=$GITLABUSER\" \
          --data-urlencode \"password=$GITLAB_PASSWORD\" \
          https://$GITHOST/api/v4/session`"
        if [ $? -ne 0 ]
        then
            echo "Gitlab authentication failed" >&2
            exit 1
        fi
        echo "$RESP" | jq -r .private_token > "$HOME/.gitlab-token-$GITHOST"
        if [ $? -ne 0 ] || [ ! -s "$HOME/.gitlab-token-$GITHOST" ]
        then
            echo "$PGM: failed to get a Gitlab private token" >&2
            rm -f "$HOME/.gitlab-token-$GITHOST"
            exit 1
        fi
        chmod 0600 "$HOME/.gitlab-token-$GITHOST"
    fi
    GITLABTOKEN="`cat $HOME/.gitlab-token-$GITHOST`"
    PROJECTBASE="`basename \"$PROJECT\" .git`"
    case $PUBLIC in
        true) VISIBILITY=public ;;
        false) VISIBILITY=private ;;
        *) echo "bad PUBLIC" >&2; exit 1 ;;
    esac
    if curl -f -H "PRIVATE-TOKEN: $GITLABTOKEN" \
        --data "name=$PROJECTBASE" \
        --data "visibility=$VISIBILITY" \
        --data-urlencode "description=$DESC" \
        "https://$GITHOST/api/v4/projects" >/dev/null
    then
        :
    else
	echo "failed to create gitlab repository: curl error" >&2
	exit 1
    fi
    URL="ssh://git@$GITHOST/$GITLABUSER/$PROJECT"
    ;;
"")
    if $FORK
    then
        echo "cannot fork unknown repo" >&2
        exit 1
    fi
    if [ "$GITHOST" = "" ] || [ "$PARENT" = "" ] || [ "$PROJECT" = "" ]
    then
        echo "$PGM: insufficient info to proceed (internal error?)" >&2
        exit 1
    fi
    URL="ssh://$GITHOST$PARENT/$PROJECT"
    QUOTESTR="s/\\([\"\'\!\$\\\\]\\)/\\\\\\1/g"
    PARENTQ="`echo \"$PARENT\" | sed \"$QUOTESSTR\"`"
    PROJECTQ="`echo \"$PROJECT\" | sed \"$QUOTESSTR\"`"
    ssh -x "$GITHOST" sh <<EOF
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

if $FORK
then
    git remote rename origin upstream &&
    git remote add origin "$URL"
else
    # Push the source repo up to the newly-created target repo.
    if git remote add origin "$URL"
    then
        :
    else
        echo "$PGM: warning: updating remote"
        git remote rm origin
        git remote add origin "$URL"
    fi
    git push -u origin $BRANCH
    if [ "$?" -ne 0 ]
    then
        echo "$PGM: push to origin failed" >&2
        exit 1
    fi
fi
