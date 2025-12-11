#!/bin/bash

# Script to fix Git push issues by removing large database files from Git tracking

echo "Step 1: Removing large database files from Git tracking..."
git rm --cached law_database.db
git rm --cached conversation_memory.db
git rm --cached db.sqlite

echo "Step 2: Removing Python cache from Git tracking..."
git rm -r --cached __pycache__
git rm -r --cached .venv

echo "Step 3: Adding updated .gitignore..."
git add .gitignore

echo "Step 4: Committing changes..."
git commit -m "Remove large database files and Python cache from Git tracking"

echo "Step 5: Pushing to GitHub..."
git push origin main --force

echo "Done! Your repository should now be successfully pushed to GitHub."
echo "Note: The database files are still on your local machine, just not tracked by Git."
