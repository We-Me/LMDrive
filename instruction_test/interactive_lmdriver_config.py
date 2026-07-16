"""Self-contained configuration for native route-free LMDrive inference."""

import os


def _enabled(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class GlobalConfig:
    # Original LMDrive PID parameters.
    turn_KP = 1.25
    turn_KI = 0.75
    turn_KD = 0.3
    turn_n = 40
    speed_KP = 5.0
    speed_KI = 0.5
    speed_KD = 1.0
    speed_n = 40
    max_throttle = 0.75
    brake_speed = 0.1
    brake_ratio = 1.1
    clip_delta = 0.35

    llm_model = os.environ.get(
        "LMDRIVE_LLM_MODEL", "/home/ndsl/workspaces/LMDrive/ckpt/llava-v1.5-7b"
    )
    preception_model = "memfuser_baseline_e1d3_return_feature"
    preception_model_ckpt = os.environ.get(
        "LMDRIVE_VISION_CKPT",
        "/home/ndsl/workspaces/LMDrive/ckpt/vision-encoder-r50.pth.tar",
    )
    lmdrive_ckpt = os.environ.get(
        "LMDRIVE_CHECKPOINT",
        "/home/ndsl/workspaces/LMDrive/ckpt/llava-v1.5-checkpoint.pth",
    )
    agent_use_notice = _enabled("LMDRIVE_USE_NOTICE", False)
    sample_rate = 2

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
