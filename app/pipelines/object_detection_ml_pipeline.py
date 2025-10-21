"""
Object detection pipeline supporting multiple ML backends (ONNX, TFLite, RKNN).

This module loads the appropriate runtime depending on the configuration stored
for the pipeline. All heavy dependencies are optional; if a backend cannot be
initialised we fall back to returning no detections while logging the reason.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import cv2
import numpy as np
from appdirs import user_data_dir

from app.pipeline_validators import (
    ML_ACCELERATORS,
    ML_MODEL_TYPES,
    ONNX_EXECUTION_PROVIDERS,
    TFLITE_DELEGATES,
)


@dataclass
class Detection:
    label: str
    confidence: float
    box: Tuple[int, int, int, int]


class DetectionBackend:
    """Base interface for backend-specific inference helpers."""

    def __init__(
        self,
        img_size: int,
        confidence_threshold: float,
        nms_iou_threshold: float,
        max_detections: int,
        class_names: List[str],
        target_classes: Iterable[str],
    ) -> None:
        self.img_size = img_size
        self.conf_threshold = confidence_threshold
        self.nms_iou_threshold = nms_iou_threshold
        self.max_detections = max_detections
        self.class_names = class_names
        self.target_classes = set(target_classes or [])

    def predict(self, frame: np.ndarray) -> List[Detection]:
        raise NotImplementedError("DetectionBackend subclasses must implement predict")


def _resolve_path(config: Dict, base_dir: str, key: str) -> Optional[str]:
    """
    Resolves a path for keys like 'model', 'labels', 'converted_onnx', 'rknn'.
    Priority:
      1. {key}_path (absolute path stored by upload handler)
      2. {key}_filename (relative file within user data dir)
      3. Legacy support: specific keys such as model_filename, labels_filename
    """
    path = config.get(f"{key}_path")
    if path and os.path.exists(path):
        return path

    filename_candidates = [
        config.get(f"{key}_filename"),
        config.get(f"{key}_file"),
    ]
    if key == "model":
        filename_candidates.append(config.get("model_filename"))
    if key == "labels":
        filename_candidates.append(config.get("labels_filename"))
    if key == "converted_onnx":
        filename_candidates.append(config.get("converted_onnx_filename"))

    for name in filename_candidates:
        if not name:
            continue
        candidate = os.path.join(base_dir, name)
        if os.path.exists(candidate):
            return candidate
    return None


def _letterbox_image(
    image: np.ndarray, img_size: int
) -> Tuple[np.ndarray, float, Tuple[float, float]]:
    """Resizes image with unchanged aspect ratio using padding."""
    original_height, original_width = image.shape[:2]
    new_shape = (img_size, img_size)
    scale = min(new_shape[0] / original_height, new_shape[1] / original_width)
    resized_w = int(round(original_width * scale))
    resized_h = int(round(original_height * scale))

    resized = cv2.resize(image, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)
    pad_w = new_shape[1] - resized_w
    pad_h = new_shape[0] - resized_h
    pad_left = pad_w / 2
    pad_top = pad_h / 2
    top = int(np.floor(pad_top))
    bottom = int(np.ceil(pad_top))
    left = int(np.floor(pad_left))
    right = int(np.ceil(pad_left))

    padded = cv2.copyMakeBorder(
        resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114)
    )
    return padded, scale, (pad_left, pad_top)


def _xywh_to_xyxy(xywh: np.ndarray) -> np.ndarray:
    """Converts [x, y, w, h] to [x1, y1, x2, y2] format."""
    xyxy = np.zeros_like(xywh)
    xyxy[:, 0] = xywh[:, 0] - xywh[:, 2] / 2  # x1
    xyxy[:, 1] = xywh[:, 1] - xywh[:, 3] / 2  # y1
    xyxy[:, 2] = xywh[:, 0] + xywh[:, 2] / 2  # x2
    xyxy[:, 3] = xywh[:, 1] + xywh[:, 3] / 2  # y2
    return xyxy


def _non_max_suppression(
    boxes: np.ndarray,
    scores: np.ndarray,
    iou_threshold: float,
    max_detections: int,
) -> List[int]:
    """Pure NumPy NMS implementation returning the indices of kept boxes."""
    if len(boxes) == 0:
        return []

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]

    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]

    keep: List[int] = []
    while order.size > 0 and len(keep) < max_detections:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        union = areas[i] + areas[order[1:]] - inter
        iou = np.zeros_like(union)
        nonzero = union > 0
        iou[nonzero] = inter[nonzero] / union[nonzero]

        to_keep = np.where(iou <= iou_threshold)[0]
        order = order[to_keep + 1]

    return keep


def _postprocess_yolo(
    prediction: np.ndarray,
    meta: Dict[str, object],
    class_names: List[str],
    conf_threshold: float,
    iou_threshold: float,
    max_detections: int,
    target_classes: Iterable[str],
) -> List[Detection]:
    """Parses YOLO-style output tensor into structured detections."""
    if prediction.ndim == 3:
        prediction = np.squeeze(prediction, axis=0)
    if prediction.ndim == 1:
        prediction = np.expand_dims(prediction, axis=0)

    if prediction.shape[1] <= 5:
        return []

    boxes = prediction[:, :4]
    objectness = prediction[:, 4]
    class_scores = prediction[:, 5:]

    class_ids = np.argmax(class_scores, axis=1)
    class_confidences = class_scores[np.arange(class_scores.shape[0]), class_ids]
    scores = objectness * class_confidences

    mask = scores >= conf_threshold
    boxes = boxes[mask]
    scores = scores[mask]
    class_ids = class_ids[mask]

    if len(boxes) == 0:
        return []

    boxes = _xywh_to_xyxy(boxes)
    scale = float(meta["scale"])
    pad_x, pad_y = meta["pad"]
    orig_w, orig_h = meta["orig_size"]

    # Undo letterbox
    boxes[:, [0, 2]] -= pad_x
    boxes[:, [1, 3]] -= pad_y
    boxes /= scale

    boxes[:, 0] = np.clip(boxes[:, 0], 0, orig_w - 1)
    boxes[:, 1] = np.clip(boxes[:, 1], 0, orig_h - 1)
    boxes[:, 2] = np.clip(boxes[:, 2], 0, orig_w - 1)
    boxes[:, 3] = np.clip(boxes[:, 3], 0, orig_h - 1)

    valid_indices = _non_max_suppression(boxes, scores, iou_threshold, max_detections)

    target_set = set(target_classes or [])
    detections: List[Detection] = []
    for idx in valid_indices:
        class_id = int(class_ids[idx])
        label = (
            class_names[class_id]
            if 0 <= class_id < len(class_names)
            else f"class_{class_id}"
        )
        if target_set and label not in target_set:
            continue
        x1, y1, x2, y2 = boxes[idx].astype(int)
        detections.append(
            Detection(
                label=label,
                confidence=float(scores[idx]),
                box=(x1, y1, x2, y2),
            )
        )

    return detections


class OnnxYoloBackend(DetectionBackend):
    def __init__(
        self,
        model_path: str,
        provider: str,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.session = None
        self.input_name = None

        if provider not in ONNX_EXECUTION_PROVIDERS:
            raise RuntimeError(
                f"Unsupported ONNX Runtime provider '{provider}'. "
                f"Expected one of {ONNX_EXECUTION_PROVIDERS}."
            )

        try:
            import onnxruntime as ort  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "onnxruntime is not installed. Install it to run YOLO ONNX models."
            ) from exc

        providers = [provider]
        if provider != "CPUExecutionProvider":
            providers.append("CPUExecutionProvider")

        try:
            self.session = ort.InferenceSession(
                model_path,
                providers=providers,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to load ONNX model: {exc}") from exc

        self.input_name = self.session.get_inputs()[0].name

    def predict(self, frame: np.ndarray) -> List[Detection]:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resized, scale, pad = _letterbox_image(rgb, self.img_size)
        tensor = resized.astype(np.float32) / 255.0
        tensor = np.transpose(tensor, (2, 0, 1))
        tensor = np.expand_dims(tensor, axis=0)

        outputs = self.session.run(None, {self.input_name: tensor})
        prediction = outputs[0]
        meta = {
            "scale": scale,
            "pad": pad,
            "orig_size": (frame.shape[1], frame.shape[0]),
        }
        return _postprocess_yolo(
            prediction,
            meta,
            self.class_names,
            self.conf_threshold,
            self.nms_iou_threshold,
            self.max_detections,
            self.target_classes,
        )


class TFLiteBackend(DetectionBackend):
    def __init__(
        self,
        model_path: str,
        delegate: str,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.interpreter = self._build_interpreter(model_path, delegate)
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()

    @staticmethod
    def _load_delegate(delegate: str):
        if delegate == "GPU":
            possible_names = [
                "libtensorflowlite_gpu_delegate.so",
                "libtensorflowlite_gpu_delegate.dylib",
                "libtensorflowlite_gpu_delegate.dll",
            ]
            for name in possible_names:
                try:
                    from tflite_runtime import interpreter as tflite_interpreter  # type: ignore

                    return tflite_interpreter.load_delegate(name)
                except Exception:
                    try:
                        from tensorflow.lite import interpreter as tflite_interpreter  # type: ignore

                        return tflite_interpreter.load_delegate(name)
                    except Exception:
                        continue
        if delegate == "EdgeTPU":
            try:
                from pycoral.utils.edgetpu import make_interpreter  # type: ignore

                return make_interpreter  # type: ignore
            except Exception as exc:
                raise RuntimeError(
                    "EdgeTPU delegate requested but pycoral is unavailable"
                ) from exc
        return None

    def _build_interpreter(self, model_path: str, delegate: str):
        delegate = delegate or "CPU"
        if delegate not in TFLITE_DELEGATES:
            raise RuntimeError(
                f"Unsupported TFLite delegate '{delegate}'. Expected one of {TFLITE_DELEGATES}."
            )

        interpreter = None
        delegate_obj = None

        if delegate == "EdgeTPU":
            try:
                from pycoral.utils.edgetpu import make_interpreter  # type: ignore

                interpreter = make_interpreter(model_path)
                interpreter.allocate_tensors()
                return interpreter
            except Exception as exc:
                raise RuntimeError(
                    "Failed to create EdgeTPU interpreter. Ensure the Coral USB accelerator is connected "
                    "and the pycoral package is installed."
                ) from exc

        try:
            from tflite_runtime import interpreter as tflite_interpreter  # type: ignore

            if delegate == "GPU":
                delegate_obj = self._load_delegate(delegate)
                if delegate_obj:
                    interpreter = tflite_interpreter.Interpreter(
                        model_path=model_path, experimental_delegates=[delegate_obj]
                    )
                else:
                    interpreter = tflite_interpreter.Interpreter(model_path=model_path)
            else:
                interpreter = tflite_interpreter.Interpreter(model_path=model_path)
        except Exception:
            from tensorflow.lite import interpreter as tflite_interpreter  # type: ignore

            kwargs = {}
            if delegate == "GPU":
                delegate_obj = self._load_delegate(delegate)
                if delegate_obj:
                    kwargs["experimental_delegates"] = [delegate_obj]
            interpreter = tflite_interpreter.Interpreter(
                model_path=model_path, **kwargs
            )

        interpreter.allocate_tensors()
        return interpreter

    def _prepare_input(self, frame: np.ndarray) -> Tuple[np.ndarray, Dict[str, object]]:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resized, scale, pad = _letterbox_image(rgb, self.img_size)
        tensor = resized.astype(np.float32) / 255.0
        tensor = np.expand_dims(tensor, axis=0)
        return tensor, {
            "scale": scale,
            "pad": pad,
            "orig_size": (frame.shape[1], frame.shape[0]),
        }

    def predict(self, frame: np.ndarray) -> List[Detection]:
        tensor, meta = self._prepare_input(frame)
        input_detail = self.input_details[0]

        if input_detail["dtype"] == np.uint8:
            input_data = (tensor * 255).astype(np.uint8)
        else:
            input_data = tensor.astype(input_detail["dtype"])

        self.interpreter.set_tensor(input_detail["index"], input_data)
        self.interpreter.invoke()

        outputs = [
            self.interpreter.get_tensor(detail["index"])
            for detail in self.output_details
        ]

        # Attempt to detect TF detection API style outputs (boxes, class, scores, count)
        if len(outputs) >= 3 and outputs[0].ndim == 3 and outputs[0].shape[-1] == 4:
            boxes = outputs[0][0]
            classes = outputs[1][0].astype(int)
            scores = outputs[2][0]
            num = int(outputs[3][0]) if len(outputs) > 3 else len(scores)
            detections: List[Detection] = []

            for i in range(min(num, len(scores))):
                score = float(scores[i])
                if score < self.conf_threshold:
                    continue
                class_id = classes[i]
                label = (
                    self.class_names[class_id]
                    if 0 <= class_id < len(self.class_names)
                    else f"class_{class_id}"
                )
                if self.target_classes and label not in self.target_classes:
                    continue
                y1, x1, y2, x2 = boxes[i]
                x1 = int(x1 * frame.shape[1])
                x2 = int(x2 * frame.shape[1])
                y1 = int(y1 * frame.shape[0])
                y2 = int(y2 * frame.shape[0])
                detections.append(
                    Detection(label=label, confidence=score, box=(x1, y1, x2, y2))
                )
            return detections

        # Fallback to YOLO-style output parsing
        prediction = outputs[0]
        return _postprocess_yolo(
            prediction,
            meta,
            self.class_names,
            self.conf_threshold,
            self.nms_iou_threshold,
            self.max_detections,
            self.target_classes,
        )


class RKNNBackend(DetectionBackend):
    def __init__(
        self,
        model_path: str,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        try:
            from rknn.api import RKNN  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "RKNN-Toolkit2 is required to run RKNN models on Orange Pi 5."
            ) from exc

        self.rknn = RKNN()
        ret = self.rknn.load_rknn(model_path)
        if ret != 0:
            raise RuntimeError(
                f"Failed to load RKNN model from '{model_path}' (code {ret})."
            )

        ret = self.rknn.init_runtime()
        if ret != 0:
            raise RuntimeError("Failed to initialise RKNN runtime.")

    def predict(self, frame: np.ndarray) -> List[Detection]:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resized, scale, pad = _letterbox_image(rgb, self.img_size)
        tensor = resized.astype(np.float32) / 255.0
        tensor = np.expand_dims(tensor, axis=0)

        outputs = self.rknn.inference(inputs=[tensor])
        if not outputs:
            return []
        prediction = outputs[0]
        meta = {
            "scale": scale,
            "pad": pad,
            "orig_size": (frame.shape[1], frame.shape[0]),
        }
        return _postprocess_yolo(
            prediction,
            meta,
            self.class_names,
            self.conf_threshold,
            self.nms_iou_threshold,
            self.max_detections,
            self.target_classes,
        )


class ObjectDetectionMLPipeline:
    """High-level pipeline wrapper instantiating the appropriate backend."""

    def __init__(self, config: Dict[str, object]):
        self.config = config or {}
        self.data_dir = user_data_dir("VisionTools", "User")
        self.class_names: List[str] = self._load_labels()
        self.backend: Optional[DetectionBackend] = None
        self._initialisation_error: Optional[str] = None

        try:
            self.backend = self._create_backend()
            if self.backend:
                print("Object Detection (ML) pipeline initialised successfully.")
            else:
                print("Object Detection (ML) pipeline initialised without backend.")
        except Exception as exc:
            self._initialisation_error = str(exc)
            print(f"Failed to initialise Object Detection (ML) pipeline: {exc}")

    def _load_labels(self) -> List[str]:
        labels_path = _resolve_path(self.config, self.data_dir, "labels")
        if not labels_path or not os.path.exists(labels_path):
            return []

        try:
            with open(labels_path, "r", encoding="utf-8") as handle:
                return [line.strip() for line in handle if line.strip()]
        except OSError as exc:
            print(f"Failed to load labels file '{labels_path}': {exc}")
            return []

    def _create_backend(self) -> Optional[DetectionBackend]:
        model_type = self.config.get("model_type", "yolo")
        if model_type not in ML_MODEL_TYPES:
            raise RuntimeError(
                f"Unsupported model_type '{model_type}'. Expected one of {ML_MODEL_TYPES}."
            )

        img_size = int(self.config.get("img_size", 640))
        conf_threshold = float(self.config.get("confidence_threshold", 0.5))
        nms_iou_threshold = float(self.config.get("nms_iou_threshold", 0.45))
        max_detections = int(self.config.get("max_detections", 100))
        target_classes = self.config.get("target_classes", [])

        accelerator = self.config.get("accelerator", "none")
        onnx_provider = self.config.get("onnx_provider", "CPUExecutionProvider")
        tflite_delegate = self.config.get("tflite_delegate", "CPU")

        if accelerator not in ML_ACCELERATORS:
            raise RuntimeError(
                f"Unsupported accelerator '{accelerator}'. Expected one of {ML_ACCELERATORS}."
            )

        if model_type == "tflite":
            model_path = _resolve_path(self.config, self.data_dir, "model")
            if not model_path:
                print("TFLite model path not configured yet.")
                return None
            return TFLiteBackend(
                model_path=model_path,
                delegate=tflite_delegate,
                img_size=img_size,
                confidence_threshold=conf_threshold,
                nms_iou_threshold=nms_iou_threshold,
                max_detections=max_detections,
                class_names=self.class_names,
                target_classes=target_classes,
            )

        # YOLO path
        if accelerator == "rknn":
            model_path = _resolve_path(self.config, self.data_dir, "rknn")
            if not model_path:
                raise RuntimeError(
                    "Accelerator 'rknn' selected but rknn_path is missing."
                )
            return RKNNBackend(
                model_path=model_path,
                img_size=img_size,
                confidence_threshold=conf_threshold,
                nms_iou_threshold=nms_iou_threshold,
                max_detections=max_detections,
                class_names=self.class_names,
                target_classes=target_classes,
            )

        onnx_path = _resolve_path(
            self.config, self.data_dir, "converted_onnx"
        ) or _resolve_path(self.config, self.data_dir, "model")

        if not onnx_path:
            print("ONNX model path not configured yet.")
            return None

        return OnnxYoloBackend(
            model_path=onnx_path,
            provider=onnx_provider,
            img_size=img_size,
            confidence_threshold=conf_threshold,
            nms_iou_threshold=nms_iou_threshold,
            max_detections=max_detections,
            class_names=self.class_names,
            target_classes=target_classes,
        )

    def process_frame(self, frame: np.ndarray, cam_matrix) -> List[Dict[str, object]]:
        if not self.backend:
            # Provide diagnostic information if available
            if self._initialisation_error:
                print(
                    f"Object Detection backend unavailable: {self._initialisation_error}"
                )
            return []

        detections = self.backend.predict(frame)
        return [
            {
                "label": det.label,
                "confidence": float(det.confidence),
                "box": [
                    int(det.box[0]),
                    int(det.box[1]),
                    int(det.box[2]),
                    int(det.box[3]),
                ],
            }
            for det in detections
        ]
