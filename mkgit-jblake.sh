#!/bin/sh

set -e

PROJECT="$1"
HOST="$2"
CDIR="$3"

if [ "${PROJECT}" == "" ]; then
	echo "Usage: $0 project [host [path]]" 1>&2
	exit 1
fi

if [ "${HOST}" == "" ]; then
	HOST="orchitis"
fi

if [ "${CDIR}" == "" ]; then
	CDIR="/home/staff/jblake/git"
fi

PROJECTQ="\"$(echo "${PROJECT}.git" | sed "s/\\([\"\'\!\$\\\\]\\)/\\\\\\1/g")\""
CDIRQ="\"$(echo "${CDIR}" | sed "s/\\([\"\'\!\$\\\\]\\)/\\\\\\1/g")\""

if [ -e "${PROJECT}" ]; then

	if [ ! -e "${PROJECT}/.git" ]; then
		echo "Local directory exists, but does not appear to be a git working directory!" 1>&2
		exit 1
	fi

	echo "Creating remote repo without initial commit."

	ssh "${HOST}" <<END
set -e
cd ${CDIRQ}
mkdir ${PROJECTQ}
export GIT_DIR=${PROJECTQ}
git init --bare --shared=group
END

	echo "Pushing existing local repo to remote."

	cd "${PROJECT}"
	git remote add origin "ssh://${HOST}/${CDIR}/${PROJECT}.git"
	git push origin +master:master

	echo "Configuring local repo to pull from remote."

	git config --add branch.master.merge refs/heads/master
	git config --add branch.master.remote origin

else

	echo "Creating remote repo with initial commit."

	ssh "${HOST}" <<END
set -e
cd ${CDIRQ}
mkdir ${PROJECTQ}
export GIT_DIR=${PROJECTQ}
git init --bare --shared=group
TREE="\$(git mktree < /dev/null)"
COMMIT="\$(echo 'Initial commit.' | git commit-tree "\${TREE}")"
git branch master "\${COMMIT}"
END

	echo "Cloning remote repo."

	git clone "ssh://${HOST}/${CDIR}/${PROJECT}.git" "${PROJECT}"

fi

echo "Done."
