#!/usr/bin/env bash

# 临时切换当前终端到 CUDA 11.8。
# 必须使用：
#   source ~/use_cuda_11_8.sh
#
# 关闭当前终端后，环境变量自动失效。

CUDA_VERSION="11.8"
CUDA_DIR="/usr/local/cuda-${CUDA_VERSION}"

if [[ ! -d "${CUDA_DIR}" ]]; then
    echo "错误：未找到 ${CUDA_DIR}"
    echo "请确认 CUDA ${CUDA_VERSION} 已经安装。"
    return 1 2>/dev/null || exit 1
fi

if [[ ! -x "${CUDA_DIR}/bin/nvcc" ]]; then
    echo "错误：未找到可执行文件：${CUDA_DIR}/bin/nvcc"
    return 1 2>/dev/null || exit 1
fi

# 删除 PATH 中已有的 CUDA 11.8 路径，避免重复添加。
PATH="$(printf '%s' "${PATH}" \
    | awk -v RS=: -v ORS=: -v target="${CUDA_DIR}/bin" \
        '$0 != target { print }' \
    | sed 's/:$//')"

# 删除 LD_LIBRARY_PATH 中已有的 CUDA 11.8 路径。
if [[ -n "${LD_LIBRARY_PATH:-}" ]]; then
    LD_LIBRARY_PATH="$(printf '%s' "${LD_LIBRARY_PATH}" \
        | awk -v RS=: -v ORS=: -v target="${CUDA_DIR}/lib64" \
            '$0 != target { print }' \
        | sed 's/:$//')"
fi

export CUDA_HOME="${CUDA_DIR}"
export CUDA_PATH="${CUDA_DIR}"
export CUDACXX="${CUDA_DIR}/bin/nvcc"

export PATH="${CUDA_DIR}/bin:${PATH}"
export LD_LIBRARY_PATH="${CUDA_DIR}/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

# 清除 Bash 对旧命令路径的缓存。
hash -r 2>/dev/null || true

echo "当前终端已切换到 CUDA ${CUDA_VERSION}"
echo "CUDA_HOME=${CUDA_HOME}"
echo "CUDACXX=${CUDACXX}"
echo "nvcc 路径：$(command -v nvcc)"
echo

nvcc --version
