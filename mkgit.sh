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
USAGE="$PGM: usage: $PGM [-X svcs] [-p|-d <desc>] ssh://[<user>@]host/<dir>/<project>.git [<git-dir>]"

SVCS=false
PUBLIC=false
PRIVATE=false

while [ $# -gt 0 ]
do
    case "$1" in
    -X)
        case "$2" in
	svcs)
	    SVCS=true
	    ;;
	*)
	    echo "$PGM: unknown -X option: $2" >&2
	    exit 1
	    ;;
	esac
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
PROJECT="`expr \"$URL\" : 'ssh://[^/]*/.*/\(.*\.git$\)'`"

if $SVCS
then
    HOST=svcs.cs.pdx.edu
    PARENT=/storage/git
    PROJECT="$URL"
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
    URL="ssh://${HOST}${PARENT}/${PROJECT}"
elif [ "$HOST" = "" ] || [ "$PARENT" = "" ] || [ "$PROJECT" = "" ]
then
    echo "$USAGE" >&2
    exit 1
fi

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

QUOTESTR="s/\\([\"\'\!\$\\\\]\\)/\\\\\\1/g"
PARENTQ="`echo \"$PARENT\" | sed \"$QUOTESSTR\"`"
PROJECTQ="`echo \"$PROJECT\" | sed \"$QUOTESSTR\"`"
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

if git remote add -t master -m master origin "$URL"
then
  :
else
  echo "$PGM: warning: updating remote"
  git remote rm origin
  git remote add -t master -m master origin "$URL"
fi
git push origin +master:master
if [ "$?" -ne 0 ]
then
    echo "$PGM: push to origin failed" >&2
    exit 1
fi

exit 0
