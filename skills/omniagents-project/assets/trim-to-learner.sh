#!/usr/bin/env bash
# trim-to-learner.sh — strip productionization layer from a freshly-scaffolded
# OmniAgents project, leaving agent + tools + evaluations.
#
# Usage:  bash trim-to-learner.sh <project-dir>
#
# Idempotent: re-running on an already-trimmed project is a no-op.
# Removes: wrapper Python package, pyproject.toml, Makefile, devcontainer,
# .github/ (CI workflows + PR template), docs/RELEASE.md.
# Rewrites: README.md, .env.example, requirements.txt to learner-friendly forms.

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "usage: $0 <project-dir>" >&2
  exit 2
fi

PROJECT_DIR="$1"

if [ ! -d "$PROJECT_DIR" ]; then
  echo "error: $PROJECT_DIR is not a directory" >&2
  exit 1
fi

if [ ! -f "$PROJECT_DIR/project.yml" ]; then
  echo "error: $PROJECT_DIR/project.yml not found — is this an OmniAgents project?" >&2
  exit 1
fi

# Read the project name from project.yml (first 'name:' field at column 0).
PROJECT_NAME="$(grep -m1 '^name:' "$PROJECT_DIR/project.yml" | awk '{print $2}')"
if [ -z "$PROJECT_NAME" ]; then
  echo "error: could not read project name from project.yml" >&2
  exit 1
fi

echo "Trimming $PROJECT_DIR (project: $PROJECT_NAME) to learner tier..."

# --- Remove productionization files and directories ---

remove() {
  if [ -e "$1" ]; then
    echo "  remove  $1"
    rm -rf "$1"
  fi
}

# Wrapper Python package (provides <project> and <project>-setup CLI scripts).
remove "$PROJECT_DIR/$PROJECT_NAME"

# Packaging metadata.
remove "$PROJECT_DIR/pyproject.toml"
remove "$PROJECT_DIR/Makefile"

# Dev container.
remove "$PROJECT_DIR/.devcontainer"

# CI workflows + PR template.
remove "$PROJECT_DIR/.github"

# Release docs.
remove "$PROJECT_DIR/docs/RELEASE.md"
# Remove docs/ if it's now empty.
if [ -d "$PROJECT_DIR/docs" ] && [ -z "$(ls -A "$PROJECT_DIR/docs")" ]; then
  echo "  remove  $PROJECT_DIR/docs (empty)"
  rmdir "$PROJECT_DIR/docs"
fi

# --- Rewrite learner-friendly versions of remaining files ---

echo "  rewrite $PROJECT_DIR/README.md"
cat > "$PROJECT_DIR/README.md" <<README_EOF
# $PROJECT_NAME

An OmniAgents project: an AI agent paired with an evaluation harness.

## Setup

\`\`\`bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and set OPENAI_API_KEY
\`\`\`

## Run the agent

\`\`\`bash
omniagents run -P project.yml
\`\`\`

This opens the agent in a browser. For a terminal interface use
\`omniagents run -P project.yml --mode ink\`.

## Run the evaluations

\`\`\`bash
omniagents eval suite run
\`\`\`

Edit \`evaluations/scenarios.yml\` to change what's tested and
\`evaluations/measures.py\` to change how outputs are scored.

## Layout

- \`agents/$PROJECT_NAME/agent.yml\` — the agent's configuration
- \`agents/$PROJECT_NAME/instructions.md\` — the agent's system prompt
- \`tools/${PROJECT_NAME}_tools.py\` — custom tools the agent can call
- \`evaluations/\` — scenarios, measures, metrics
README_EOF

echo "  rewrite $PROJECT_DIR/.env.example"
cat > "$PROJECT_DIR/.env.example" <<'ENV_EOF'
# Required: your OpenAI API key.
OPENAI_API_KEY=

# Optional: only set these if using a custom OpenAI-compatible endpoint
# (e.g., a class server, Azure, or self-hosted).
# OPENAI_BASE_URL=
ENV_EOF

# Rewrite requirements.txt: drop the Gemfury --extra-index-url line (only
# needed for installing private packages from Gemfury) and the dev-only
# black dependency.
echo "  rewrite $PROJECT_DIR/requirements.txt"
cat > "$PROJECT_DIR/requirements.txt" <<'REQ_EOF'
openai==1.99.9
omniagents[all]==0.6.44
requests>=2.31.0
beautifulsoup4>=4.12.0
pygit2>=1.13.0
REQ_EOF

echo "Done. The project now contains only what's needed to run and evaluate the agent locally."
