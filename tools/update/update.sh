#!/usr/bin/env bash

# Pull the git repo. uwsgi will automatically restart the
# application as necessary.

# Get to our root directory
UPDDIR=$(dirname $0)
cd $UPDDIR

# Now pull the main repo
cd $UPDDIR

# Sleep 10 seconds to avoid interfering with the automirror scripts that
# also run exactly on the minute.
sleep 10

# Pull changes from the git repo
git pull --rebase -q >/dev/null 2>&1
