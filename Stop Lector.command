#!/usr/bin/env bash
# Double-click in Finder to stop a Lector server started by start.sh or
# "Start Lector.command".
exec "$(dirname "${BASH_SOURCE[0]}")/stop.sh"
