#!/usr/bin/env bash
# Double-click in Finder to start Lector in a new Terminal window.
# Closing that window (or Ctrl+C) stops the server, same as ./start.sh.
exec "$(dirname "${BASH_SOURCE[0]}")/start.sh"
