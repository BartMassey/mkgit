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
USAGE="$PGM: usage: $PGM [-p|-d <desc>] [-X [big-site|little-site|github|na] [<project>[.git]] | ssh://[<user>@]host/<dir>/<project>.git] [<git-dir>]"

X=''
SVCS=false
PUBLIC=false
PRIVATE=false

while [ $# -gt 0 ]
do
    case "$1" in
    -X)
	X="$2"
	shift 2
	;;
    -d)
	case "$PRIVATE" in
	true)
	    echo "$PGM: both private and public were specified"
	    exit 1
	    ;;
	esac
        PUBLIC=true
	DESC="$2"
	shift 2
	;;
    -p)
	case "$PUBLIC" in
	true)
	    echo "$PGM: both public and private were specified"
	    exit 1
	    ;;
	esac
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

if $PUBLIC || $PRIVATE
then
    :
else
    echo "$PGM: neither public (-d <desc>) nor private (-p) was specified" >&2
    exit 1
fi

if [ $# -gt 2 ]
then
    echo "$USAGE" >&2
    exit 1
fi

URL="$1"
GITDIR="."

HOST="`expr \"$URL\" : 'ssh://\([^/]*\)'`"
PARENT="`expr \"$URL\" : 'ssh://[^/]*\(/.*\)/'`"
PROJECT="`expr \"$URL\" : 'ssh://[^/]*/.*/\([^/]*\.git$\)'`"

case $X in
big-site)
    SVCS=true
    HOST=big-site.example.org
    PARENT=/storage/git
    ;;
little-site)
    HOST=little-site.example.org
    PARENT=/storage/git
    ;;
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
    if $PRIVATE
    then
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
    echo "$PARENT"
    echo "$PROJECT"
    URL="ssh://${HOST}${PARENT}/${PROJECT}"
    QUOTESTR="s/\\([\"\'\!\$\\\\]\\)/\\\\\\1/g"
    PARENTQ="`echo \"$PARENT\" | sed \"$QUOTESSTR\"`"
    PROJECTQ="`echo \"$PROJECT\" | sed \"$QUOTESSTR\"`"
    echo "$PARENTQ"
    echo "$PROJECTQ"
    ssh "${HOST}" <<EOF
    cd "${PARENTQ}" &&
    mkdir "${PROJECTQ}" &&
    cd "${PROJECTQ}" &&
    git init --bare --shared=group &&
    if $PUBLIC
    then
      touch git-daemon-export-ok
      echo "${DESC}" >description
      ${SVCS} && ln -s "${PARENTQ}/${PROJECTQ}" /git/.
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
