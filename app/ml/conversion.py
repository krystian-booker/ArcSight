"""
Conversion utilities for ML models used in the object detection pipeline.

The functions in this module best-effort convert user supplied artefacts into
formats consumable by the runtime backends. They return (success, message, path)
tuples so calling code can surface actionable errors to the UI without
crashing the server when optional dependencies are not installed.
"""

from __future__ import annotations

import os
import shutil
from typing import Optional, Tuple


def convert_yolo_weights_to_onnx(
    source_path: str,
    destination_path: str,
    img_size: int = 640,
) -> Tuple[bool, str, Optional[str]]:
    """
    Converts a YOLO weights file (e.g. .pt) to ONNX format.

    Returns:
        success (bool), message (str), output_path (str|None)
    """
    try:
        from ultralytics import YOLO  # type: ignore
    except Exception:
        return (
            False,
            "Ultralytics package not available. Install 'ultralytics' to convert YOLO weights.",
            None,
        )

    try:
        model = YOLO(source_path)
        exported_path = model.export(
            format="onnx",
            imgsz=img_size,
            simplify=True,
            optimize=False,
            verbose=False,
        )
    except Exception as exc:
        return False, f"Failed to export YOLO model to ONNX: {exc}", None

    if not exported_path or not os.path.exists(exported_path):
        return False, "YOLO export did not produce an ONNX file.", None

    try:
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        shutil.move(exported_path, destination_path)
    except Exception as exc:
        return False, f"Failed to move exported ONNX file: {exc}", None

    return True, "Converted YOLO weights to ONNX.", destination_path


def convert_onnx_to_rknn(
    onnx_path: str,
    destination_path: str,
) -> Tuple[bool, str, Optional[str]]:
    """
    Converts an ONNX model to RKNN format using RKNN-Toolkit2.

    Returns:
        success (bool), message (str), output_path (str|None)
    """
    try:
        from rknn.api import RKNN  # type: ignore
    except Exception:
        return (
            False,
            "RKNN-Toolkit2 is not installed. Install it on the Orange Pi 5 to enable NPU conversion.",
            None,
        )

    rknn = RKNN()
    try:
        ret = rknn.load_onnx(model=onnx_path)
        if ret != 0:
            return False, f"Failed to load ONNX model into RKNN (code {ret}).", None

        ret = rknn.build(do_quantization=False)
        if ret != 0:
            return False, f"RKNN build failed with code {ret}.", None

        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        ret = rknn.export_rknn(destination_path)
        if ret != 0:
            return False, f"Failed to export RKNN model (code {ret}).", None

    except Exception as exc:
        return False, f"RKNN conversion error: {exc}", None
    finally:
        rknn.release()

    return True, "Converted ONNX model to RKNN.", destination_path


def validate_onnx_model(model_path: str) -> Tuple[bool, str]:
    """Validates that an ONNX model can be parsed."""
    try:
        import onnx  # type: ignore
    except Exception:
        return False, "onnx package is not installed; cannot validate model."

    try:
        model = onnx.load(model_path)
        onnx.checker.check_model(model)
        return True, "ONNX model validated successfully."
    except Exception as exc:
        return False, f"ONNX validation failed: {exc}"


def infer_model_type(filename: str) -> Optional[str]:
    """Infers model type based on file extension."""
    ext = os.path.splitext(filename.lower())[1]
    if ext in [".onnx", ".pt", ".weights"]:
        return "yolo"
    if ext in [".tflite"]:
        return "tflite"
    if ext in [".rknn"]:
        return "rknn"
    return None
