#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISSUES_DIR="$ROOT_DIR/issues"
FIRST_ISSUE=20
LAST_ISSUE=26

usage() {
  cat <<'EOF'
Usage:
  ./scripts/issue_queue.sh status
  ./scripts/issue_queue.sh next
  ./scripts/issue_queue.sh prompt
  ./scripts/issue_queue.sh commit "<summary>"
  ./scripts/issue_queue.sh verify

Commit message format is enforced as:
  issue(0NN): <summary>

The queue covers issues 020 through 026 and reads completion from git history.
EOF
}

pad_issue() {
  printf "%03d" "$1"
}

issue_file() {
  local padded
  padded="$(pad_issue "$1")"
  local pattern="$ISSUES_DIR/${padded}-"*.md
  shopt -s nullglob
  local matches=($pattern)
  shopt -u nullglob
  if ((${#matches[@]} == 0)); then
    return 1
  fi
  printf "%s\n" "${matches[0]}"
}

issue_commit_hash() {
  local padded
  padded="$(pad_issue "$1")"
  git -C "$ROOT_DIR" log --grep "^issue(${padded}): " --format="%H" -n 1 || true
}

issue_commit_subject() {
  local padded
  padded="$(pad_issue "$1")"
  git -C "$ROOT_DIR" log --grep "^issue(${padded}): " --format="%h %s" -n 1 || true
}

next_pending_issue() {
  local id
  for ((id=FIRST_ISSUE; id<=LAST_ISSUE; id++)); do
    if ! issue_file "$id" >/dev/null; then
      continue
    fi
    if [[ -z "$(issue_commit_hash "$id")" ]]; then
      printf "%d\n" "$id"
      return 0
    fi
  done
  return 1
}

cmd_status() {
  local id
  for ((id=FIRST_ISSUE; id<=LAST_ISSUE; id++)); do
    local file
    if ! file="$(issue_file "$id" 2>/dev/null)"; then
      continue
    fi
    local padded
    padded="$(pad_issue "$id")"
    local subject
    subject="$(issue_commit_subject "$id")"
    if [[ -n "$subject" ]]; then
      printf "%s  done     %s\n" "$padded" "$subject"
    else
      printf "%s  pending  %s\n" "$padded" "$file"
    fi
  done
}

cmd_next() {
  local id
  if ! id="$(next_pending_issue)"; then
    echo "All queued issues are complete."
    return 0
  fi
  local padded
  padded="$(pad_issue "$id")"
  local file
  file="$(issue_file "$id")"
  printf "Next issue: %s\nSpec file: %s\n" "$padded" "$file"
}

cmd_prompt() {
  local id
  if ! id="$(next_pending_issue)"; then
    echo "All queued issues are complete."
    return 0
  fi
  local padded
  padded="$(pad_issue "$id")"
  local file
  file="$(issue_file "$id")"
  cat <<EOF
Implement issue ${padded} from:
${file}

Rules:
1. Implement only this issue.
2. Follow repository standards in AGENTS.md and CONTRIBUTING.md.
3. Add/update tests required by the issue and run relevant checks.
4. When complete, stage changes and commit exactly once with:
   issue(${padded}): <summary>
5. Stop after the commit so a fresh agent context can start the next issue.

Issue specification:
EOF
  echo "-----"
  cat "$file"
}

cmd_commit() {
  local summary="${1:-}"
  if [[ -z "$summary" ]]; then
    echo "Missing summary."
    echo "Usage: ./scripts/issue_queue.sh commit \"<summary>\""
    return 1
  fi

  local id
  if ! id="$(next_pending_issue)"; then
    echo "All queued issues are complete. No commit created."
    return 1
  fi

  if ! git -C "$ROOT_DIR" diff --quiet; then
    echo "Unstaged changes detected. Stage or stash them before committing."
    return 1
  fi

  if git -C "$ROOT_DIR" diff --cached --quiet; then
    echo "No staged changes detected."
    return 1
  fi

  local padded
  padded="$(pad_issue "$id")"
  git -C "$ROOT_DIR" commit -m "issue(${padded}): ${summary}"
  echo "Committed issue ${padded}."
}

cmd_verify() {
  local id
  local saw_gap=false
  local previous_hash=""
  local previous_padded=""

  for ((id=FIRST_ISSUE; id<=LAST_ISSUE; id++)); do
    local file
    if ! file="$(issue_file "$id" 2>/dev/null)"; then
      continue
    fi

    local padded
    padded="$(pad_issue "$id")"
    local hash
    hash="$(issue_commit_hash "$id")"

    if [[ -z "$hash" ]]; then
      saw_gap=true
      continue
    fi

    if [[ "$saw_gap" == "true" ]]; then
      echo "Out-of-order completion: ${padded} has a commit, but an earlier issue is still pending."
      return 1
    fi

    if [[ -n "$previous_hash" ]]; then
      if ! git -C "$ROOT_DIR" merge-base --is-ancestor "$previous_hash" "$hash"; then
        echo "Sequence violation: issue ${previous_padded} commit is not an ancestor of issue ${padded} commit."
        return 1
      fi
    fi

    previous_hash="$hash"
    previous_padded="$padded"
  done

  echo "Queue order is valid for issues 020-026."
}

main() {
  local command="${1:-}"
  case "$command" in
    status)
      cmd_status
      ;;
    next)
      cmd_next
      ;;
    prompt)
      cmd_prompt
      ;;
    commit)
      shift || true
      cmd_commit "${1:-}"
      ;;
    verify)
      cmd_verify
      ;;
    *)
      usage
      ;;
  esac
}

main "${1:-}"
