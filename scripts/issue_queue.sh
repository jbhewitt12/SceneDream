#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISSUES_DIR="$ROOT_DIR/issues"
FIRST_ISSUE=""
LAST_ISSUE=""
RANGE_SPEC="${ISSUE_QUEUE_RANGE:-}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/issue_queue.sh [--range NNN-NNN] status
  ./scripts/issue_queue.sh [--range NNN-NNN] next
  ./scripts/issue_queue.sh [--range NNN-NNN] prompt
  ./scripts/issue_queue.sh [--range NNN-NNN] run-next
  ./scripts/issue_queue.sh [--range NNN-NNN] run-all
  ./scripts/issue_queue.sh [--range NNN-NNN] commit "<summary>"
  ./scripts/issue_queue.sh [--range NNN-NNN] verify

Examples:
  ./scripts/issue_queue.sh --range 020-026 run-all
  ./scripts/issue_queue.sh --range 027-033 status
  ISSUE_QUEUE_RANGE=027-033 ./scripts/issue_queue.sh run-next

Commit message format is enforced as:
  issue(0NN): <summary>

Range selection:
  - CLI option: --range NNN-NNN
  - Env var: ISSUE_QUEUE_RANGE=NNN-NNN
  - Default: auto-detect min/max issue IDs present in ./issues

Completion is read from git history in the selected range.
EOF
}

initialize_range() {
  local spec="${RANGE_SPEC}"
  if [[ -z "$spec" ]]; then
    discover_range_from_issues
    return 0
  fi
  parse_range_spec "$spec"
}

discover_range_from_issues() {
  local ids=()
  mapfile -t ids < <(
    find "$ISSUES_DIR" -maxdepth 1 -type f -name '[0-9][0-9][0-9]-*.md' -exec basename {} \; \
      | sed -E 's/^([0-9]{3})-.*/\1/' \
      | sort -n
  )

  if ((${#ids[@]} == 0)); then
    echo "No issue files found in $ISSUES_DIR."
    exit 1
  fi

  FIRST_ISSUE=$((10#${ids[0]}))
  LAST_ISSUE=$((10#${ids[${#ids[@]}-1]}))
}

parse_range_spec() {
  local spec="$1"
  if [[ ! "$spec" =~ ^([0-9]{1,3})-([0-9]{1,3})$ ]]; then
    echo "Invalid range '$spec'. Expected format: NNN-NNN"
    exit 1
  fi

  local start=$((10#${BASH_REMATCH[1]}))
  local end=$((10#${BASH_REMATCH[2]}))

  if ((start > end)); then
    echo "Invalid range '$spec'. Start must be <= end."
    exit 1
  fi

  FIRST_ISSUE="$start"
  LAST_ISSUE="$end"
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
  render_prompt "$id"
}

render_prompt() {
  local id="$1"
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

run_agent_for_issue() {
  local id="$1"
  local padded
  padded="$(pad_issue "$id")"
  local before_hash
  before_hash="$(issue_commit_hash "$id")"

  if [[ -n "$before_hash" ]]; then
    echo "Issue ${padded} is already complete."
    return 0
  fi

  local tmp_prompt
  tmp_prompt="$(mktemp)"
  render_prompt "$id" >"$tmp_prompt"

  echo "Running fresh agent context for issue ${padded}..."
  if ! codex exec --ephemeral --cd "$ROOT_DIR" - <"$tmp_prompt"; then
    rm -f "$tmp_prompt"
    echo "Agent run failed for issue ${padded}."
    return 1
  fi
  rm -f "$tmp_prompt"

  local after_hash
  after_hash="$(issue_commit_hash "$id")"
  if [[ -z "$after_hash" ]]; then
    echo "Issue ${padded} still pending. Expected commit subject: issue(${padded}): <summary>"
    return 1
  fi

  echo "Issue ${padded} completed."
}

cmd_run_next() {
  local id
  if ! id="$(next_pending_issue)"; then
    echo "All queued issues are complete."
    return 0
  fi
  run_agent_for_issue "$id"
}

cmd_run_all() {
  local id
  while id="$(next_pending_issue)"; do
    if ! run_agent_for_issue "$id"; then
      echo "Stopping queue."
      return 1
    fi
  done
  echo "All queued issues are complete."
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

  echo "Queue order is valid for issues $(pad_issue "$FIRST_ISSUE")-$(pad_issue "$LAST_ISSUE")."
}

main() {
  while (($# > 0)); do
    case "$1" in
      --range)
        if (($# < 2)); then
          echo "Missing value for --range"
          usage
          exit 1
        fi
        RANGE_SPEC="$2"
        shift 2
        ;;
      --range=*)
        RANGE_SPEC="${1#*=}"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        break
        ;;
    esac
  done

  initialize_range

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
    run-next)
      cmd_run_next
      ;;
    run-all)
      cmd_run_all
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

main "$@"
