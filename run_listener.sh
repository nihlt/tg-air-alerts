#!/bin/bash
cd "$(dirname "$0")"

echo "Cleanup before start..."
python3 cleanup_listener.py
if [ $? -ne 0 ]; then
    echo "Cleanup failed. Exiting."
    exit 1
fi

echo ""
echo "Starting listener. Stop with Ctrl+C."
echo ""
python3 listen_tg_channels.py
