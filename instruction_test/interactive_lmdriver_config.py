"""Configuration overlay for the interactive LMDrive agent.

Defaults are inherited from the project's existing configuration. Environment
variables make checkpoint locations and notice testing configurable without
editing any tracked LMDrive source file.
"""

import os

from lmdriver_config import GlobalConfig as BaseGlobalConfig


def _enabled(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class GlobalConfig(BaseGlobalConfig):
    llm_model = os.environ.get("LMDRIVE_LLM_MODEL", BaseGlobalConfig.llm_model)
    preception_model_ckpt = os.environ.get(
        "LMDRIVE_VISION_CKPT", BaseGlobalConfig.preception_model_ckpt
    )
    lmdrive_ckpt = os.environ.get(
        "LMDRIVE_CHECKPOINT", BaseGlobalConfig.lmdrive_ckpt
    )
    agent_use_notice = _enabled(
        "LMDRIVE_USE_NOTICE", BaseGlobalConfig.agent_use_notice
    )
