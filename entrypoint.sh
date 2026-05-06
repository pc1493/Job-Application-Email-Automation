#!/bin/bash
if [ -n "$GITHUB_TOKEN" ]; then
    git config --global credential.helper store
    echo "https://pc1493:${GITHUB_TOKEN}@github.com" > /home/claude-user/.git-credentials
fi
git config --global user.name "pc-1493"
git config --global user.email "peterchen.ba@gmail.com"
git config --global --add safe.directory /workspace
exec "$@"