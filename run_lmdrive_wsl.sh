#!/usr/bin/env bash
set -euo pipefail

# ==========================================================
# LMDrive WSL Launcher
# Windows CARLA Server + WSL Python Client
# ==========================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

# ----------------------------------------------------------
# 0. Python executable from uv virtual environment
# ----------------------------------------------------------

UV_PYTHON="${ROOT_DIR}/.venv/bin/python"

if [ ! -x "${UV_PYTHON}" ]; then
    echo "uv virtual environment not found:"
    echo "${UV_PYTHON}"
    echo ""
    echo "Please create it first:"
    echo "  cd ${ROOT_DIR}"
    echo "  uv venv --python 3.8"
    echo "  uv pip install -r requirements.txt"
    exit 1
fi

PYTHON_BIN="${UV_PYTHON}"

echo "Python executable: ${PYTHON_BIN}"
"${PYTHON_BIN}" --version

export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HOME="${HF_HOME:-${HOME}/.cache/huggingface}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-${HF_HOME}/transformers}"

# ----------------------------------------------------------
# 1. Connect to Windows CARLA server
# ----------------------------------------------------------

export CARLA_HOST="${CARLA_HOST:-$(ip route | awk '/default/ {print $3; exit}')}"
export PORT=2000
export TM_PORT=2500

echo "LMDrive root: ${ROOT_DIR}"
echo "CARLA host: ${CARLA_HOST}"
echo "CARLA port: ${PORT}"
echo "Traffic Manager port: ${TM_PORT}"

# ----------------------------------------------------------
# 2. Linux CARLA PythonAPI path
# ----------------------------------------------------------
# 注意：这里必须是 Linux 版 CARLA PythonAPI，
# 不能使用 Windows 的 win-amd64.egg。

CARLA_ROOT="${ROOT_DIR}/third_party/carla"
CARLA_EGG="${CARLA_ROOT}/PythonAPI/carla/dist/carla-0.9.10-py3.7-linux-x86_64.egg"

if [ ! -f "${CARLA_EGG}" ]; then
    echo "CARLA Linux egg not found:"
    echo "${CARLA_EGG}"
    exit 1
fi

# ----------------------------------------------------------
# 3. PYTHONPATH
# ----------------------------------------------------------

export PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}"
export PYTHONPATH="${ROOT_DIR}/leaderboard:${PYTHONPATH}"
export PYTHONPATH="${ROOT_DIR}/leaderboard/team_code:${PYTHONPATH}"
export PYTHONPATH="${ROOT_DIR}/scenario_runner:${PYTHONPATH}"

export PYTHONPATH="${CARLA_ROOT}/PythonAPI:${PYTHONPATH}"
export PYTHONPATH="${CARLA_ROOT}/PythonAPI/carla:${PYTHONPATH}"
export PYTHONPATH="${CARLA_EGG}:${PYTHONPATH}"

# ----------------------------------------------------------
# 4. Leaderboard / LMDrive config
# ----------------------------------------------------------

export LEADERBOARD_ROOT="${ROOT_DIR}/leaderboard"
export CHALLENGE_TRACK_CODENAME="SENSORS"
export DEBUG_CHALLENGE=0
export REPETITIONS=1

export ROUTES="${ROOT_DIR}/langauto/benchmark_tiny.xml"
export TEAM_AGENT="${ROOT_DIR}/leaderboard/team_code/lmdriver_agent.py"
export TEAM_CONFIG="${ROOT_DIR}/leaderboard/team_code/lmdriver_config.py"
export CHECKPOINT_ENDPOINT="${ROOT_DIR}/results/sample_result.json"
export SCENARIOS="${ROOT_DIR}/leaderboard/data/official/all_towns_traffic_scenarios_public.json"
export SAVE_PATH="${ROOT_DIR}/data/eval"
export RESUME=True

mkdir -p "$(dirname "${CHECKPOINT_ENDPOINT}")"
mkdir -p "${SAVE_PATH}"

# ----------------------------------------------------------
# 5. Basic checks
# ----------------------------------------------------------

echo "Checking CARLA PythonAPI..."
${PYTHON_BIN} -c "import carla; print(carla.__file__)"

echo "Checking connection to Windows CARLA..."
${PYTHON_BIN} - <<PY
import carla
host = "${CARLA_HOST}"
port = int("${PORT}")
client = carla.Client(host, port)
client.set_timeout(10.0)
world = client.get_world()
print("Connected to CARLA:", world.get_map().name)
PY

# ----------------------------------------------------------
# 6. Run evaluator
# ----------------------------------------------------------

echo "Starting LMDrive evaluator..."

${PYTHON_BIN} -u "${LEADERBOARD_ROOT}/leaderboard/leaderboard_evaluator.py" \
    --host="${CARLA_HOST}" \
    --port="${PORT}" \
    --trafficManagerPort="${TM_PORT}" \
    --scenarios="${SCENARIOS}" \
    --routes="${ROUTES}" \
    --repetitions="${REPETITIONS}" \
    --track="${CHALLENGE_TRACK_CODENAME}" \
    --checkpoint="${CHECKPOINT_ENDPOINT}" \
    --agent="${TEAM_AGENT}" \
    --agent-config="${TEAM_CONFIG}" \
    --debug="${DEBUG_CHALLENGE}" \
    --resume="${RESUME}"