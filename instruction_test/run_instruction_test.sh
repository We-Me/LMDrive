#!/usr/bin/env bash
set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${TEST_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HOME="${HF_HOME:-${HOME}/.cache/huggingface}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-${HF_HOME}/transformers}"
export CARLA_ROOT="${CARLA_ROOT:-${HOME}/carla/carla09101}"
export CARLA_HOST="${CARLA_HOST:-127.0.0.1}"
export PORT="${PORT:-2000}"
export TM_PORT="${TM_PORT:-2500}"

START_CARLA_SERVER="${START_CARLA_SERVER:-1}"
KEEP_CARLA_SERVER="${KEEP_CARLA_SERVER:-0}"
CARLA_START_TIMEOUT="${CARLA_START_TIMEOUT:-120}"
CARLA_QUALITY="${CARLA_QUALITY:-Epic}"
CARLA_RES_X="${CARLA_RES_X:-1024}"
CARLA_RES_Y="${CARLA_RES_Y:-576}"
CARLA_WINDOW_MODE="${CARLA_WINDOW_MODE:-windowed}"
CARLA_EXTRA_ARGS="${CARLA_EXTRA_ARGS:-}"
CARLA_LOG="${CARLA_LOG:-${TEST_DIR}/output/carla_server.log}"

CARLA_TOWN="${CARLA_TOWN:-Town05}"
SPAWN_POINT_INDEX="${SPAWN_POINT_INDEX:-auto}"
BACKGROUND_VEHICLES="${BACKGROUND_VEHICLES:-0}"
EGO_VEHICLE="${EGO_VEHICLE:-vehicle.lincoln.mkz2017}"
CARLA_WEATHER="${CARLA_WEATHER:-ClearNoon}"

export LMDRIVE_INITIAL_COMMAND="${LMDRIVE_INITIAL_COMMAND:-Other-03}"
export LMDRIVE_TEMPLATE_INDEX="${LMDRIVE_TEMPLATE_INDEX:-0}"
export LMDRIVE_SAVE_FRAMES="${LMDRIVE_SAVE_FRAMES:-0}"
export PYTHONUNBUFFERED=1

PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
if [ ! -x "${PYTHON_BIN}" ]; then
    echo "[ERROR] LMDrive virtual environment not found: ${PYTHON_BIN}"
    echo "Create the project's .venv before running this test."
    exit 1
fi

CARLA_SERVER="${CARLA_ROOT}/CarlaUE4.sh"
CARLA_DIST_DIR="${CARLA_ROOT}/PythonAPI/carla/dist"
CARLA_EGG="${CARLA_DIST_DIR}/carla-0.9.10-py3.7-linux-x86_64.egg"

for required_path in "${CARLA_SERVER}" "${CARLA_EGG}"; do
    if [ ! -f "${required_path}" ]; then
        echo "[ERROR] Required CARLA file not found: ${required_path}"
        exit 1
    fi
done
if [ ! -x "${CARLA_SERVER}" ]; then
    echo "[ERROR] CARLA launcher is not executable: ${CARLA_SERVER}"
    exit 1
fi

export PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}"
export PYTHONPATH="${ROOT_DIR}/LAVIS:${PYTHONPATH}"
export PYTHONPATH="${ROOT_DIR}/vision_encoder:${PYTHONPATH}"
export PYTHONPATH="${CARLA_ROOT}/PythonAPI:${PYTHONPATH}"
export PYTHONPATH="${CARLA_ROOT}/PythonAPI/carla:${PYTHONPATH}"
export PYTHONPATH="${CARLA_EGG}:${PYTHONPATH}"

mkdir -p "${TEST_DIR}/output" "${TEST_DIR}/output/frames" "$(dirname "${CARLA_LOG}")"

carla_is_ready() {
    "${PYTHON_BIN}" - <<'PY' >/dev/null 2>&1
import os
import carla

client = carla.Client(os.environ["CARLA_HOST"], int(os.environ["PORT"]))
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
            echo "Stopping CARLA Server process group: ${CARLA_PID}"
            kill -TERM -- "-${CARLA_PID}" 2>/dev/null || true
            for _ in $(seq 1 20); do
                if ! kill -0 -- "-${CARLA_PID}" 2>/dev/null; then
                    break
                fi
                sleep 0.5
            done
            if kill -0 -- "-${CARLA_PID}" 2>/dev/null; then
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

if carla_is_ready; then
    echo "Reusing CARLA Server at ${CARLA_HOST}:${PORT}."
else
    if [ "${START_CARLA_SERVER}" != "1" ]; then
        echo "[ERROR] CARLA is not reachable and START_CARLA_SERVER=0."
        exit 1
    fi
    if ! command -v setsid >/dev/null 2>&1; then
        echo "[ERROR] setsid is required (Ubuntu package: util-linux)."
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
        windowed) CARLA_ARGS+=("-windowed") ;;
        fullscreen) CARLA_ARGS+=("-fullscreen") ;;
        none|"") ;;
        *)
            echo "[ERROR] CARLA_WINDOW_MODE must be windowed, fullscreen, or none."
            exit 1
            ;;
    esac
    if [ -n "${CARLA_EXTRA_ARGS}" ]; then
        # shellcheck disable=SC2206
        EXTRA_ARGS=( ${CARLA_EXTRA_ARGS} )
        CARLA_ARGS+=("${EXTRA_ARGS[@]}")
    fi

    echo "Starting CARLA Server..."
    (
        cd "${CARLA_ROOT}"
        exec setsid "${CARLA_SERVER}" "${CARLA_ARGS[@]}"
    ) >"${CARLA_LOG}" 2>&1 &
    CARLA_PID=$!
    CARLA_STARTED_BY_SCRIPT=1

    ready=0
    for ((elapsed = 1; elapsed <= CARLA_START_TIMEOUT; elapsed++)); do
        if carla_is_ready; then
            ready=1
            break
        fi
        if ! kill -0 -- "-${CARLA_PID}" 2>/dev/null; then
            echo "[ERROR] CARLA exited during startup."
            tail -n 80 "${CARLA_LOG}" || true
            exit 1
        fi
        if (( elapsed % 10 == 0 )); then
            echo "Waiting for CARLA... ${elapsed}s"
        fi
        sleep 1
    done
    if [ "${ready}" != "1" ]; then
        echo "[ERROR] CARLA did not become ready within ${CARLA_START_TIMEOUT}s."
        tail -n 80 "${CARLA_LOG}" || true
        exit 1
    fi
fi

if [ ! -t 0 ]; then
    echo "[WARNING] stdin is not a TTY; terminal instructions may be unavailable."
fi

echo "Starting native route-free LMDrive instruction test:"
echo "  map:              ${CARLA_TOWN}"
echo "  spawn point:      ${SPAWN_POINT_INDEX}"
echo "  ego vehicle:      ${EGO_VEHICLE}"
echo "  background count: ${BACKGROUND_VEHICLES}"
echo "  initial command:  ${LMDRIVE_INITIAL_COMMAND}"
echo "  control source:   raw LMDrive waypoints + original PID math"

"${PYTHON_BIN}" -u "${TEST_DIR}/standalone_client.py" \
    --host "${CARLA_HOST}" \
    --port "${PORT}" \
    --traffic-manager-port "${TM_PORT}" \
    --town "${CARLA_TOWN}" \
    --spawn-point "${SPAWN_POINT_INDEX}" \
    --vehicle "${EGO_VEHICLE}" \
    --background-vehicles "${BACKGROUND_VEHICLES}" \
    --weather "${CARLA_WEATHER}"
