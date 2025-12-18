#!/usr/bin/env bash
# Exit on error
set -e

echo "--------------------------------------"
echo "Build Script Started"
echo "--------------------------------------"

# Create a local bin directory
echo "Creating local bin directory..."
mkdir -p bin

# Download and extract Git LFS
# We use --strip-components=1 because the tarball has a top-level directory e.g., git-lfs-3.4.0/
echo "Downloading Git LFS..."
curl -L https://github.com/git-lfs/git-lfs/releases/download/v3.4.0/git-lfs-linux-amd64-v3.4.0.tar.gz | tar -xz -C bin --strip-components=1

# Verify the binary exists
if [ -f "./bin/git-lfs" ]; then
    echo "Git LFS binary found at ./bin/git-lfs"
else
    echo "ERROR: Git LFS binary NOT found in ./bin"
    ls -R bin
    exit 1
fi

# Add bin to PATH just in case
export PATH=$PWD/bin:$PATH

# Install LFS hooks locally
echo "Installing Git LFS hooks..."
./bin/git-lfs install --force

# Pull the large database file
echo "Pulling LFS files (Database)..."
./bin/git-lfs pull

# Install Python requirements
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "--------------------------------------"
echo "Build Script Completed Successfully"
echo "--------------------------------------"
