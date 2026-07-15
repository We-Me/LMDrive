#!/usr/bin/env bash
set -euo pipefail

# ==========================================================
# LMDrive Ubuntu Launcher
# Ubuntu CARLA Server + Ubuntu LMDrive Python Client
#
# 默认 CARLA 安装目录：~/carla/carla09101
# 默认行为：
#   1. 检查 LMDrive 的 uv 虚拟环境
#   2. 配置 Linux CARLA PythonAPI
#   3. 在本机启动 CARLA Server
#   4. 等待 CARLA Server 就绪
#   5. 启动 LMDrive Leaderboard evaluator
#   6. evaluator 结束时关闭本脚本启动的 CARLA Server
# ==========================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

# ----------------------------------------------------------
# 0. 可通过环境变量覆盖的配置
# ----------------------------------------------------------

export HF_ENDPOINT=https://hf-mirror.com
export CARLA_ROOT="${CARLA_ROOT:-${HOME}/carla/carla09101}"
export CARLA_HOST="${CARLA_HOST:-127.0.0.1}"
export PORT="${PORT:-2000}"
export TM_PORT="${TM_PORT:-2500}"

# 1：脚本负责启动 CARLA；0：仅连接已经运行的 CARLA。
START_CARLA_SERVER="${START_CARLA_SERVER:-1}"

# 1：evaluator 结束后保留 CARLA；0：关闭本脚本启动的 CARLA。
KEEP_CARLA_SERVER="${KEEP_CARLA_SERVER:-0}"

CARLA_START_TIMEOUT="${CARLA_START_TIMEOUT:-120}"

# CARLA 0.9.10 最高预设画质。
CARLA_QUALITY="${CARLA_QUALITY:-Epic}"

# CARLA 服务端观察窗口分辨率。
# 不影响 LMDrive 相机传感器自身的输入分辨率。
CARLA_RES_X="${CARLA_RES_X:-1024}"
CARLA_RES_Y="${CARLA_RES_Y:-576}"

CARLA_WINDOW_MODE="${CARLA_WINDOW_MODE:-windowed}"
CARLA_LOG="${CARLA_LOG:-${ROOT_DIR}/logs/carla_server.log}"

# 保持为空时使用 CARLA 默认渲染接口。
# 需要 OpenGL 时可在外部设置：
#   export CARLA_EXTRA_ARGS="-opengl"
CARLA_EXTRA_ARGS="${CARLA_EXTRA_ARGS:-}"

# ----------------------------------------------------------
# 1. LMDrive Python 虚拟环境
# ----------------------------------------------------------

UV_PYTHON="${ROOT_DIR}/.venv/bin/python"

if [ ! -x "${UV_PYTHON}" ]; then
    echo "[ERROR] uv virtual environment not found:"
    echo "        ${UV_PYTHON}"
    echo
    echo "Create it first:"
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
# 2. Ubuntu CARLA Server 与 PythonAPI
# ----------------------------------------------------------

CARLA_SERVER="${CARLA_ROOT}/CarlaUE4.sh"
CARLA_DIST_DIR="${CARLA_ROOT}/PythonAPI/carla/dist"

if [ ! -f "${CARLA_SERVER}" ]; then
    echo "[ERROR] CARLA server launcher not found:"
    echo "        ${CARLA_SERVER}"
    exit 1
fi

if [ ! -x "${CARLA_SERVER}" ]; then
    echo "[ERROR] CARLA server launcher is not executable:"
    echo "        ${CARLA_SERVER}"
    echo "Run:"
    echo "  chmod +x '${CARLA_SERVER}'"
    exit 1
fi

if [ ! -d "${CARLA_DIST_DIR}" ]; then
    echo "[ERROR] CARLA PythonAPI dist directory not found:"
    echo "        ${CARLA_DIST_DIR}"
    exit 1
fi

# ----------------------------------------------------------
# 明确使用 Python 3.7 版本 CARLA egg
# ----------------------------------------------------------

CARLA_EGG="${CARLA_DIST_DIR}/carla-0.9.10-py3.7-linux-x86_64.egg"

if [ ! -f "${CARLA_EGG}" ]; then
    echo "[ERROR] CARLA Python 3.7 egg not found:"
    echo "        ${CARLA_EGG}"
    echo
    echo "Available CARLA eggs:"
    find "${CARLA_DIST_DIR}" -maxdepth 1 -type f -name "*.egg" -print
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
# 4. Leaderboard / LMDrive 配置
# ----------------------------------------------------------

export LEADERBOARD_ROOT="${ROOT_DIR}/leaderboard"
export CHALLENGE_TRACK_CODENAME="${CHALLENGE_TRACK_CODENAME:-SENSORS}"
export DEBUG_CHALLENGE="${DEBUG_CHALLENGE:-0}"
export REPETITIONS="${REPETITIONS:-1}"

export ROUTES="${ROUTES:-${ROOT_DIR}/langauto/benchmark_tiny.xml}"
export TEAM_AGENT="${TEAM_AGENT:-${ROOT_DIR}/leaderboard/team_code/lmdriver_agent.py}"
export TEAM_CONFIG="${TEAM_CONFIG:-${ROOT_DIR}/leaderboard/team_code/lmdriver_config.py}"
export CHECKPOINT_ENDPOINT="${CHECKPOINT_ENDPOINT:-${ROOT_DIR}/results/sample_result.json}"
export SCENARIOS="${SCENARIOS:-${ROOT_DIR}/leaderboard/data/official/all_towns_traffic_scenarios_public.json}"
export SAVE_PATH="${SAVE_PATH:-${ROOT_DIR}/data/eval}"
export RESUME="${RESUME:-False}"

mkdir -p "$(dirname "${CHECKPOINT_ENDPOINT}")"
mkdir -p "${SAVE_PATH}"
mkdir -p "$(dirname "${CARLA_LOG}")"

REQUIRED_FILES=(
    "${LEADERBOARD_ROOT}/leaderboard/leaderboard_evaluator.py"
    "${ROUTES}"
    "${TEAM_AGENT}"
    "${TEAM_CONFIG}"
    "${SCENARIOS}"
)

for required_file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "${required_file}" ]; then
        echo "[ERROR] Required LMDrive file not found:"
        echo "        ${required_file}"
        exit 1
    fi
done

# ----------------------------------------------------------
# 5. 基础检查
# ----------------------------------------------------------

echo "LMDrive root:          ${ROOT_DIR}"
echo "CARLA root:            ${CARLA_ROOT}"
echo "CARLA executable:      ${CARLA_SERVER}"
echo "CARLA Python egg:      ${CARLA_EGG}"
echo "CARLA host:            ${CARLA_HOST}"
echo "CARLA RPC port:        ${PORT}"
echo "Traffic Manager port:  ${TM_PORT}"
echo "CARLA quality:         ${CARLA_QUALITY}"
echo "CARLA resolution:      ${CARLA_RES_X}x${CARLA_RES_Y}"
echo "CARLA window mode:     ${CARLA_WINDOW_MODE}"
echo "CARLA extra args:      ${CARLA_EXTRA_ARGS:-<none>}"
echo "CARLA log:             ${CARLA_LOG}"

echo "Checking CARLA PythonAPI..."
"${PYTHON_BIN}" -c "import carla; print('CARLA module:', carla.__file__)"

carla_is_ready() {
    "${PYTHON_BIN}" - <<'PY' >/dev/null 2>&1
import os
import carla

client = carla.Client(
    os.environ["CARLA_HOST"],
    int(os.environ["PORT"]),
)
client.set_timeout(2.0)
client.get_world()
PY
}

CARLA_PID=""
CARLA_STARTED_BY_SCRIPT=0

cleanup() {
    local exit_code=$?

    if [ "${CARLA_STARTED_BY_SCRIPT}" = "1" ] && [ -n "${CARLA_PID}" ]; then
        if [ "${KEEP_CARLA_SERVER}" = "1" ]; then
            echo "Keeping CARLA Server running. PID: ${CARLA_PID}"
        elif kill -0 -- "-${CARLA_PID}" 2>/dev/null; then
            echo "Stopping CARLA Server process group. PGID: ${CARLA_PID}"
            kill -TERM -- "-${CARLA_PID}" 2>/dev/null || true

            for _ in $(seq 1 20); do
                if ! kill -0 -- "-${CARLA_PID}" 2>/dev/null; then
                    break
                fi
                sleep 0.5
            done

            if kill -0 -- "-${CARLA_PID}" 2>/dev/null; then
                echo "CARLA did not exit normally; sending SIGKILL."
                kill -KILL -- "-${CARLA_PID}" 2>/dev/null || true
            fi

            wait "${CARLA_PID}" 2>/dev/null || true
        fi
    fi

    return "${exit_code}"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# ----------------------------------------------------------
# 6. 启动或复用 Ubuntu CARLA Server
# ----------------------------------------------------------

if carla_is_ready; then
    echo "CARLA Server is already running; reusing it."
    echo
    echo "[NOTICE] The existing CARLA process keeps its original quality"
    echo "         and resolution settings."
    echo "         Restart CARLA to apply Epic ${CARLA_RES_X}x${CARLA_RES_Y}."
else
    if [ "${START_CARLA_SERVER}" != "1" ]; then
        echo "[ERROR] CARLA is not reachable at ${CARLA_HOST}:${PORT}."
        echo "        START_CARLA_SERVER=0, so the script will not start it."
        exit 1
    fi

    CARLA_ARGS=(
        "-carla-rpc-port=${PORT}"
        "-quality-level=${CARLA_QUALITY}"
        "-ResX=${CARLA_RES_X}"
        "-ResY=${CARLA_RES_Y}"
        "-NoSound"
    )

    case "${CARLA_WINDOW_MODE}" in
        windowed)
            CARLA_ARGS+=("-windowed")
            ;;
        fullscreen)
            CARLA_ARGS+=("-fullscreen")
            ;;
        none|"")
            ;;
        *)
            echo "[ERROR] Unsupported CARLA_WINDOW_MODE: ${CARLA_WINDOW_MODE}"
            echo "        Use: windowed, fullscreen, or none"
            exit 1
            ;;
    esac

    if [ -n "${CARLA_EXTRA_ARGS}" ]; then
        # shellcheck disable=SC2206
        EXTRA_ARGS=( ${CARLA_EXTRA_ARGS} )
        CARLA_ARGS+=("${EXTRA_ARGS[@]}")
    fi

    echo "Starting Ubuntu CARLA Server..."
    echo "Command: ${CARLA_SERVER} ${CARLA_ARGS[*]}"

    if ! command -v setsid >/dev/null 2>&1; then
        echo "[ERROR] setsid is required but was not found."
        echo "        Install the Ubuntu util-linux package."
        exit 1
    fi

    (
        cd "${CARLA_ROOT}"
        exec setsid "${CARLA_SERVER}" "${CARLA_ARGS[@]}"
    ) >"${CARLA_LOG}" 2>&1 &

    CARLA_PID=$!
    CARLA_STARTED_BY_SCRIPT=1

    echo "CARLA PID: ${CARLA_PID}"
    echo "Waiting up to ${CARLA_START_TIMEOUT}s for CARLA..."

    ready=0

    for ((elapsed = 1; elapsed <= CARLA_START_TIMEOUT; elapsed++)); do
        if carla_is_ready; then
            ready=1
            break
        fi

        if ! kill -0 -- "-${CARLA_PID}" 2>/dev/null; then
            echo "[ERROR] CARLA Server exited during startup."
            echo "Last 80 log lines:"
            tail -n 80 "${CARLA_LOG}" || true
            exit 1
        fi

        if (( elapsed % 10 == 0 )); then
            echo "  still waiting... ${elapsed}s"
        fi

        sleep 1
    done

    if [ "${ready}" != "1" ]; then
        echo "[ERROR] CARLA did not become ready within ${CARLA_START_TIMEOUT}s."
        echo "Last 80 log lines:"
        tail -n 80 "${CARLA_LOG}" || true
        exit 1
    fi
fi

"${PYTHON_BIN}" - <<'PY'
import os
import carla

host = os.environ["CARLA_HOST"]
port = int(os.environ["PORT"])

client = carla.Client(host, port)
client.set_timeout(10.0)

world = client.get_world()
print("Connected to CARLA:", world.get_map().name)
PY

# ----------------------------------------------------------
# 7. 运行 LMDrive evaluator
# ----------------------------------------------------------

echo "Starting LMDrive evaluator..."

"${PYTHON_BIN}" -u \
    "${LEADERBOARD_ROOT}/leaderboard/leaderboard_evaluator.py" \
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