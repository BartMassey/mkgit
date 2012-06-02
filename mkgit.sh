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
SITESCRIPTS="`ls ${BIN} | egrep '^mkgit-'`"
# Pipe-separated list of site names. Used both for
# display and with shell eval.
SITES="`echo $SITESCRIPTS | sed -e 's=mkgit-==g' -e 's= =|='`"

USAGE="$PGM: usage: $PGM [-p|-d <desc>] [-X [$SITES|github|na] [<project>[.git]] | ssh://[<user>@]host/<dir>/<project>.git] [<git-dir>]"

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

# HERE

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

if [ $# -gt 2 ]
then
    echo "$USAGE" >&2
    exit 1
fi

URL="$1"
GITDIR="."


case $X in
github|na)
    PROJECT="$URL"
    ;;
"")
    HOST="`expr \"$URL\" : 'ssh://\([^/]*\)'`"
    PARENT="`expr \"$URL\" : 'ssh://[^/]*\(/.*\)/'`"
    PROJECT="`expr \"$URL\" : 'ssh://[^/]*/.*/\([^/]*\.git$\)'`"
    if [ "$PROJECT" = "" ]
    then
        PROJECT="`expr \"$URL\" : 'ssh://[^/]*/.*/\([^/.]*$\)'`"
    fi
    if [ "$HOST" = "" ] || [ "$PARENT" = "" ] || [ "$PROJECT" = "" ]
    then
        echo "$PGM: bad repo URL \"$HOST\", giving up" >&2
        exit 1
    fi
    ;;
*)
    PROJECT="$URL"
    eval "case $X in
    $SITES)
        . $BIN/mkgit-$X
        X=''
        ;;
    *)
        echo \"$PGM: unknown -X argument \\\"$X\\\", giving up\" >&2
        exit 1
        ;;
    esac"
esac
case $X in
na)
    ;;
*)
    case "$PROJECT" in
    "")
	PROJECT="`basename \"\`pwd\`\"`"
	case "$PROJECT" in
	*.git)
	  ;;
        *)
	  PROJECT="$PROJECT".git
	  ;;
	esac
        echo "$PGM: warning: no project name specified, so using $PROJECT" >&2
	;;
    *.git)
        ;;
    *)
        PROJECT="$PROJECT".git
	echo "$PGM: warning: added .git to project" >&2
	;;
    esac
    ;;
esac

case $X in
github)
    if $PUBLIC
    then
        :
    else
	echo "$PGM: cannot create private github repos" >&2
	exit 1
    fi
    if [ ! -f "$HOME/.githubuser" ] || [ ! -f "$HOME/.githubtoken" ]
    then
	echo "$PGM: need \$HOME/.githubuser and \$HOME/.githubtoken" >&2
	exit 1
    fi
    PROJECT="`basename $PROJECT`"
    GITHUBUSER="`cat $HOME/.githubuser`"
    GITHUBTOKEN="`cat $HOME/.githubtoken`"
    URL="ssh://git@github.com/$GITHUBUSER/${PROJECT}"
    MSGTMP="/tmp/mkgit-curlmsg.$$"
    trap "rm -f $MSGTMP" 0 1 2 3 15
    if curl \
         -F "login=$GITHUBUSER" \
         -F "token=$GITHUBTOKEN" \
	 https://github.com/api/v2/yaml/repos/create \
         -F "name=$PROJECT" >$MSGTMP
    then
	:
    else
	echo "failed to create github repository:" >&2
	cat $MSGTMP >&2
	exit 1
    fi
    if curl \
         -F "login=$GITHUBUSER" \
         -F "token=$GITHUBTOKEN" \
	 "https://github.com/api/v2/yaml/repos/show/$GITHUBUSER/$PROJECT" \
         -F "values[description]=$DESC" >$MSGTMP
    then
	:
    else
e	echo "failed to set github description:" >&2
	cat $MSGTMP >&2
	exit 1
    fi
    ;;
"")
    if [ "$HOST" = "" ] || [ "$PARENT" = "" ] || [ "$PROJECT" = "" ]
    then
        echo "$USAGE" >&2
        exit 1
    fi
    URL="ssh://${HOST}${PARENT}/${PROJECT}"
    QUOTESTR="s/\\([\"\'\!\$\\\\]\\)/\\\\\\1/g"
    PARENTQ="`echo \"$PARENT\" | sed \"$QUOTESSTR\"`"
    PROJECTQ="`echo \"$PROJECT\" | sed \"$QUOTESSTR\"`"
    ssh "${HOST}" <<EOF
    cd "${PARENTQ}" &&
    mkdir -p "${PROJECTQ}" &&
    cd "${PROJECTQ}" &&
    git init --bare --shared=group &&
    if $PUBLIC
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
na)
    ;;
*)
    echo "$USAGE" >&2
    exit 1
    ;;
esac

if [ $# -eq 2 ]
then
    GITDIR="$2"
fi

cd "${GITDIR}"
if [ "$?" -ne 0 ]
then
    echo "$PGM: could not find git directory ${GITDIR}" >&2
    exit 1
fi
if [ ! -d ".git" ]
then
    echo "$PGM: directory ${GITDIR} is not a git working directory!" 1>&2
    exit 1
fi

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
