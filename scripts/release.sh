#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:?Usage: scripts/release.sh <version>}"
DATE=$(date +%Y-%m-%d)
PREV_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")

# Guard: must be on main
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "main" ]]; then
  echo "ERROR: must be on main (currently on $BRANCH)" >&2
  exit 1
fi

# Guard: clean working tree
if [[ -n $(git status --porcelain) ]]; then
  echo "ERROR: working tree is dirty. Commit or stash first." >&2
  exit 1
fi

# Bump version in pyproject.toml and __init__.py
sed -i.bak "s/^version = .*/version = \"$VERSION\"/" pyproject.toml && rm pyproject.toml.bak
sed -i.bak "s/__version__ = .*/__version__ = \"$VERSION\"/" alcove/__init__.py && rm alcove/__init__.py.bak

# Generate CHANGELOG entry from git log
if [[ -n "$PREV_TAG" ]]; then
  LOG=$(git log "$PREV_TAG"..HEAD --pretty=format:"- %s" --no-merges)
else
  LOG=$(git log --pretty=format:"- %s" --no-merges)
fi

ENTRY="## [$VERSION] - $DATE

$LOG"

# Prepend to CHANGELOG.md
if [[ ! -f CHANGELOG.md ]]; then
  printf "# Changelog\n\nAll notable changes to alcove-search.\n\n%s\n" "$ENTRY" > CHANGELOG.md
else
  TMPFILE=$(mktemp)
  # Preserve the header line if it exists
  if head -1 CHANGELOG.md | grep -q "^# Changelog"; then
    { head -1 CHANGELOG.md; printf "\n%s\n\n" "$ENTRY"; tail -n +3 CHANGELOG.md; } > "$TMPFILE"
  else
    { printf "%s\n\n" "$ENTRY"; cat CHANGELOG.md; } > "$TMPFILE"
  fi
  mv "$TMPFILE" CHANGELOG.md
fi

# Commit, tag, push
git add pyproject.toml alcove/__init__.py CHANGELOG.md
git commit -m "Release v$VERSION"
git tag "v$VERSION"
git push origin main
git push origin "v$VERSION"

echo ""
echo "Released v$VERSION."
echo "PyPI publish: https://github.com/Pro777/alcove/actions"
echo "Release: https://github.com/Pro777/alcove/releases/tag/v$VERSION"
