#!/usr/bin/env bash
# Exit on error
set -e

echo "--------------------------------------"
echo "Build Script Started"
echo "--------------------------------------"

# ---------------------------------------------------------------------------
# Database — persistent disk + LFS fallback
#
# law_database.db (1.4 GB) lives on a Render persistent disk mounted at
# /data so it survives across deploys. On the very first deploy the disk
# is empty, so we fall back to the Git LFS pull and copy the result onto
# the disk. Subsequent deploys skip LFS entirely → builds are ~5x faster.
# ---------------------------------------------------------------------------

DB_DEST="/data/law_database.db"

if [ -f "$DB_DEST" ]; then
    SIZE=$(stat -c%s "$DB_DEST" 2>/dev/null || stat -f%z "$DB_DEST")
    echo "✓ Found law_database.db on persistent disk ($SIZE bytes) — skipping Git LFS pull"
else
    echo "law_database.db not yet on persistent disk — running one-time Git LFS pull"

    # Install Git LFS locally for this build
    echo "Downloading Git LFS..."
    mkdir -p bin
    curl -L https://github.com/git-lfs/git-lfs/releases/download/v3.4.0/git-lfs-linux-amd64-v3.4.0.tar.gz \
        | tar -xz -C bin --strip-components=1
    if [ ! -f "./bin/git-lfs" ]; then
        echo "ERROR: Git LFS binary NOT found"
        exit 1
    fi
    export PATH=$PWD/bin:$PATH
    ./bin/git-lfs install --force

    # Pull the DB from LFS
    echo "Pulling LFS files (Database)..."
    ./bin/git-lfs pull

    # Persist to disk so we never have to do this again
    if [ -f law_database.db ] && [ -d /data ]; then
        echo "Copying law_database.db to persistent disk..."
        cp law_database.db "$DB_DEST"
        echo "✓ DB persisted to $DB_DEST"
    else
        echo "WARNING: /data not mounted or LFS pull did not produce the DB — app may fail at startup"
    fi
fi

# Install Python requirements
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "--------------------------------------"
echo "Build Script Completed Successfully"
echo "--------------------------------------"
