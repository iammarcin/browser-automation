#!/bin/bash
# Wait for X server to be ready

set -e

echo "Waiting for X server at $DISPLAY..."

# Wait for X server to accept connections
timeout=30
count=0

while ! xdpyinfo >/dev/null 2>&1; do
    if [ $count -ge $timeout ]; then
        echo "X server at $DISPLAY not ready after $timeout seconds"
        exit 1
    fi
    echo "Waiting for X server... ($count/$timeout)"
    sleep 1
    count=$((count + 1))
done

echo "X server ready at $DISPLAY"

# Now start fluxbox
exec /usr/bin/fluxbox