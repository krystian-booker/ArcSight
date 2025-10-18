"""
Runtime and hardware capability detection helpers for ML pipelines.

These utilities probe installed libraries and hardware so the UI can expose
only the execution providers that are likely to work on the current system.
The functions intentionally swallow import errors and fall back to sensible
defaults so they remain safe to call on developer machines without specialised
hardware or libraries installed.
"""

from __future__ import annotations

import os
import platform
import subprocess
from functools import lru_cache
from typing import Dict, List


@lru_cache(maxsize=1)
def _is_macos() -> bool:
    return platform.system().lower() == "darwin"


@lru_cache(maxsize=1)
def _is_windows() -> bool:
    return platform.system().lower() == "windows"


@lru_cache(maxsize=1)
def _has_nvidia_gpu() -> bool:
    # Try torch CUDA first if available
    try:
        import torch  # type: ignore

        if hasattr(torch, "cuda") and torch.cuda.is_available():
            return True
    except Exception:
        pass

    # Fallback: look for nvidia-smi utility
    cmd = "nvidia-smi.exe" if _is_windows() else "nvidia-smi"
    try:
        completed = subprocess.run(
            [cmd, "--help"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return completed.returncode == 0
    except Exception:
        return False


@lru_cache(maxsize=1)
def _is_orange_pi_5() -> bool:
    # Allow explicit override for development/testing
    if os.environ.get("VISIONTOOLS_FORCE_OPI5") == "1":
        return True

    # Orange Pi 5 devices use the RK3588 SoC and expose the model via device tree
    model_paths = [
        "/proc/device-tree/model",
        "/sys/firmware/devicetree/base/model",
    ]
    for path in model_paths:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                model = fh.read().lower()
                if "orange pi 5" in model or "rk3588" in model:
                    return True
        except FileNotFoundError:
            continue

    return False


@lru_cache(maxsize=1)
def _has_rknn_toolkit() -> bool:
    try:
        import rknn.api  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


def get_available_onnx_providers() -> List[str]:
    providers: List[str] = []
    try:
        import onnxruntime as ort  # type: ignore

        providers = list(ort.get_available_providers())
    except Exception:
        providers = []

    if not providers:
        providers = ["CPUExecutionProvider"]

    filtered: List[str] = []
    for provider in providers:
        if provider == "CoreMLExecutionProvider" and not _is_macos():
            continue
        if provider in ("CUDAExecutionProvider", "TensorrtExecutionProvider"):
            if not _has_nvidia_gpu():
                continue
        filtered.append(provider)

    # CPU provider should always be available as a safe fallback
    if "CPUExecutionProvider" not in filtered:
        filtered.append("CPUExecutionProvider")

    return filtered


def _tflite_delegate_supported(delegate: str) -> bool:
    if delegate == "CPU":
        # Always available if TFLite interpreter can be imported (checked below)
        return True

    try:
        from tflite_runtime import interpreter as tflite_interpreter  # type: ignore
    except Exception:
        try:
            from tensorflow.lite import interpreter as tflite_interpreter  # type: ignore  # noqa: F401
        except Exception:
            # Interpreter not present at all
            return False

    if delegate == "GPU":
        # Attempt to load the GPU delegate shared library
        possible_names = [
            "libtensorflowlite_gpu_delegate.so",
            "libtensorflowlite_gpu_delegate.dylib",
            "libtensorflowlite_gpu_delegate.dll",
        ]
        for name in possible_names:
            try:
                tflite_interpreter.load_delegate(name)
                return True
            except Exception:
                continue
        return False

    if delegate == "EdgeTPU":
        # Try importing pycoral utility to enumerate devices
        try:
            from pycoral.utils.edgetpu import list_edge_tpu_devices  # type: ignore

            devices = list_edge_tpu_devices()  # type: ignore
            return bool(devices)
        except Exception:
            return False

    return False


def get_available_tflite_delegates() -> List[str]:
    delegates: List[str] = []
    try:
        from tflite_runtime import interpreter as _  # type: ignore
    except Exception:
        try:
            from tensorflow.lite import interpreter as _  # type: ignore  # noqa: F401
        except Exception:
            # No interpreter available at all
            return []

    for delegate in ["CPU", "GPU", "EdgeTPU"]:
        if _tflite_delegate_supported(delegate):
            delegates.append(delegate)

    if "CPU" not in delegates:
        delegates.append("CPU")

    return delegates


def get_ml_availability() -> Dict[str, object]:
    """Returns a structured capability report for the ML pipeline UI."""
    onnx_providers = get_available_onnx_providers()
    tflite_delegates = get_available_tflite_delegates()
    is_orangepi5 = _is_orange_pi_5()
    rknn_supported = is_orangepi5 and _has_rknn_toolkit()

    return {
        "platform": {
            "is_macos": _is_macos(),
            "is_windows": _is_windows(),
            "has_nvidia": _has_nvidia_gpu(),
            "is_orangepi5": is_orangepi5,
        },
        "onnx": {
            "providers": onnx_providers,
        },
        "tflite": {
            "delegates": tflite_delegates,
        },
        "accelerators": {
            "rknn": rknn_supported,
        },
    }
