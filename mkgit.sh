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
USAGE="$PGM: usage: $PGM ssh://[<user>@]host/<dir>/<project>.git [<git-dir>]"

if [ $# -lt 1 ] || [ $# -gt 2 ]
then
    echo "$USAGE" >&2
    exit 1
fi

URL="$1"
GITDIR="."

HOST="`expr \"$URL\" : 'ssh://\([^/]*\)'`"
PARENT="`expr \"$URL\" : 'ssh://[^/]*\(/.*\)/'`"
PROJECT="`expr \"$URL\" : 'ssh://[^/]*/.*/\(.*\.git$\)'`"

if [ "$HOST" = "" ] || [ "$PARENT" = "" ] || [ "$PROJECT" = "" ]
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
git init --bare --shared=group
EOF
if [ "$?" -ne 0 ]
then
    echo "$PGM: ssh to create repo failed" >&2
    exit 1
fi

git remote add -t master -m master origin "$URL"
git push origin +master:master
if [ "$?" -ne 0 ]
then
    echo "$PGM: push to origin failed" >&2
    exit 1
fi

exit 0
