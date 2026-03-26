#!/usr/bin/env bash

set -u

PYTHON_MIN="3.10"
NODE_MIN="18.0"
NPM_MIN="9.0"

FAILURES=0
WARNINGS=0

platform_name() {
  case "$(uname -s)" in
    Darwin) echo "macos" ;;
    Linux) echo "linux" ;;
    MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
    *) echo "unknown" ;;
  esac
}

PLATFORM="$(platform_name)"

print_header() {
  printf '\n%s\n' "$1"
}

print_ok() {
  printf '  [OK] %s\n' "$1"
}

print_warn() {
  WARNINGS=$((WARNINGS + 1))
  printf '  [WARN] %s\n' "$1"
}

print_fail() {
  FAILURES=$((FAILURES + 1))
  printf '  [FAIL] %s\n' "$1"
}

version_ge() {
  local current="$1"
  local minimum="$2"
  python3 - "$current" "$minimum" <<'PY'
import sys

def parse(value: str) -> list[int]:
    pieces = []
    for item in value.split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        pieces.append(int(digits or "0"))
    return pieces

current = parse(sys.argv[1])
minimum = parse(sys.argv[2])
length = max(len(current), len(minimum))
current.extend([0] * (length - len(current)))
minimum.extend([0] * (length - len(minimum)))
sys.exit(0 if current >= minimum else 1)
PY
}

print_python_install_steps() {
  case "$PLATFORM" in
    macos)
      cat <<'EOF'
    Install Homebrew if needed:
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    Install Python 3.11:
      brew install python@3.11
EOF
      ;;
    linux)
      cat <<'EOF'
    Ubuntu/Debian example:
      sudo apt-get update
      sudo apt-get install -y python3.11 python3.11-venv python3-pip
EOF
      ;;
    windows)
      cat <<'EOF'
    Windows example:
      winget install Python.Python.3.11
EOF
      ;;
    *)
      cat <<'EOF'
    Install Python 3.10+ from:
      https://www.python.org/downloads/
EOF
      ;;
  esac
}

print_uv_install_steps() {
  case "$PLATFORM" in
    macos)
      cat <<'EOF'
    Install uv:
      brew install uv
EOF
      ;;
    linux)
      cat <<'EOF'
    Install uv:
      curl -LsSf https://astral.sh/uv/install.sh | sh
EOF
      ;;
    windows)
      cat <<'EOF'
    Install uv:
      winget install --id=AstralSoftware.UV -e
EOF
      ;;
    *)
      cat <<'EOF'
    Install uv:
      https://docs.astral.sh/uv/getting-started/installation/
EOF
      ;;
  esac
}

print_node_install_steps() {
  case "$PLATFORM" in
    macos)
      cat <<'EOF'
    Install Node.js 20 LTS (includes npm):
      brew install node@20
EOF
      ;;
    linux)
      cat <<'EOF'
    Ubuntu/Debian example:
      curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
      sudo apt-get install -y nodejs
EOF
      ;;
    windows)
      cat <<'EOF'
    Windows example:
      winget install OpenJS.NodeJS.LTS
EOF
      ;;
    *)
      cat <<'EOF'
    Install Node.js 18+ (includes npm):
      https://nodejs.org/
EOF
      ;;
  esac
}

print_docker_install_steps() {
  case "$PLATFORM" in
    macos)
      cat <<'EOF'
    Install Docker Desktop:
      brew install --cask docker
EOF
      ;;
    linux)
      cat <<'EOF'
    Install Docker Engine + Compose plugin:
      https://docs.docker.com/engine/install/
EOF
      ;;
    windows)
      cat <<'EOF'
    Install Docker Desktop:
      winget install Docker.DockerDesktop
EOF
      ;;
    *)
      cat <<'EOF'
    Install Docker:
      https://docs.docker.com/get-docker/
EOF
      ;;
  esac
}

check_python() {
  print_header "Python"
  if ! command -v python3 >/dev/null 2>&1; then
    print_fail "python3 not found. SceneDream backend requires Python ${PYTHON_MIN}+."
    print_python_install_steps
    return
  fi

  local version
  version="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
  if version_ge "$version" "$PYTHON_MIN"; then
    print_ok "python3 ${version}"
  else
    print_fail "python3 ${version} is too old. SceneDream backend requires Python ${PYTHON_MIN}+."
    print_python_install_steps
  fi
}

check_uv() {
  print_header "uv"
  if ! command -v uv >/dev/null 2>&1; then
    print_fail "uv not found. The backend install and run commands use uv."
    print_uv_install_steps
    return
  fi

  local version
  version="$(uv --version | awk '{print $2}')"
  print_ok "uv ${version}"
}

check_node() {
  print_header "Node.js"
  if ! command -v node >/dev/null 2>&1; then
    print_fail "node not found. The frontend requires Node.js ${NODE_MIN}+."
    print_node_install_steps
    return
  fi

  local version
  version="$(node -p 'process.versions.node')"
  if version_ge "$version" "$NODE_MIN"; then
    print_ok "node ${version}"
  else
    print_fail "node ${version} is too old. The frontend requires Node.js ${NODE_MIN}+."
    print_node_install_steps
  fi
}

check_npm() {
  print_header "npm"
  if ! command -v npm >/dev/null 2>&1; then
    print_fail "npm not found. Install Node.js ${NODE_MIN}+ to get a compatible npm."
    print_node_install_steps
    return
  fi

  local version
  version="$(npm --version)"
  if version_ge "$version" "$NPM_MIN"; then
    print_ok "npm ${version}"
  else
    print_fail "npm ${version} is too old. Install a newer Node.js LTS release."
    print_node_install_steps
  fi
}

check_docker() {
  print_header "Docker (optional but recommended)"
  if ! command -v docker >/dev/null 2>&1; then
    print_warn "docker not found. The documented direct-run path uses Docker for PostgreSQL."
    print_docker_install_steps
    return
  fi

  local docker_version
  docker_version="$(docker --version | awk '{print $3}' | tr -d ',')"
  print_ok "docker ${docker_version}"

  if docker compose version >/dev/null 2>&1; then
    local compose_version
    compose_version="$(docker compose version --short 2>/dev/null || docker compose version | awk '{print $4}')"
    print_ok "docker compose ${compose_version}"
  else
    print_warn "docker is installed, but the Docker Compose plugin is missing."
    print_docker_install_steps
  fi
}

print_next_steps() {
  print_header "Next steps"
  cat <<'EOF'
  1. Copy the env template:
       cp .env.example .env
  2. Add your OpenAI key to `.env`.
  3. Start PostgreSQL (documented quickstart path):
       docker compose up -d db
  4. Start the backend:
       cd backend
       uv sync
       uv run alembic upgrade head
       uv run fastapi dev app/main.py
  5. Start the frontend in another terminal:
       cd frontend
       npm install
       npm run dev
  6. Open the app at:
       http://localhost:5173
  7. In Settings, click "Run configuration test" before your first pipeline run.
EOF
}

printf 'SceneDream first-run doctor\n'
printf 'Platform: %s\n' "$PLATFORM"

check_python
check_uv
check_node
check_npm
check_docker
print_next_steps

print_header "Summary"
if [ "$FAILURES" -eq 0 ]; then
  if [ "$WARNINGS" -eq 0 ]; then
    printf '  Ready for the documented local setup path.\n'
  else
    printf '  Required tooling looks good. Review the warning(s) above.\n'
  fi
  exit 0
fi

printf '  %s required check(s) failed. Fix those items and rerun ./scripts/doctor.sh.\n' "$FAILURES"
exit 1
