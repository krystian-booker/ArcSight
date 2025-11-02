"""Service for ML model management and processing."""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from app.utils.config import DATA_DIR
from app.ml import (
    convert_yolo_weights_to_onnx,
    convert_onnx_to_rknn,
    validate_onnx_model,
    infer_model_type,
)
from app.hw.accel import get_ml_availability

logger = logging.getLogger(__name__)


class ModelService:
    """Service for handling ML model uploads, conversions, and configuration."""

    @staticmethod
    def remove_file(path: Optional[str]) -> None:
        """
        Safely remove a file if it exists.

        Args:
            path: Path to file to remove
        """
        if path and os.path.exists(path):
            try:
                os.remove(path)
                logger.debug(f"Removed file: {path}")
            except OSError as e:
                logger.warning(f"Failed to remove file {path}: {e}")

    @staticmethod
    def get_labels_from_file(labels_path: str) -> List[str]:
        """
        Read labels from a file.

        Args:
            labels_path: Path to labels file

        Returns:
            List of label strings
        """
        if not os.path.exists(labels_path):
            return []

        try:
            with open(labels_path, "r", encoding="utf-8") as handle:
                labels = [line.strip() for line in handle if line.strip()]
            logger.debug(f"Loaded {len(labels)} labels from {labels_path}")
            return labels
        except OSError as e:
            logger.error(f"Error reading labels file {labels_path}: {e}")
            return []

    @staticmethod
    def process_tflite_model(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process TFLite model configuration.

        Args:
            config: Current pipeline configuration

        Returns:
            Updated configuration for TFLite model
        """
        updated = dict(config)
        updated["model_type"] = "tflite"
        updated["tflite_delegate"] = updated.get("tflite_delegate") or "CPU"

        # Remove incompatible configuration
        updated.pop("onnx_provider", None)
        updated.pop("converted_onnx_path", None)
        updated.pop("converted_onnx_filename", None)
        updated.pop("rknn_path", None)

        if updated.get("accelerator") == "rknn":
            updated["accelerator"] = "none"

        logger.debug("Configured TFLite model")
        return updated

    @staticmethod
    def process_rknn_model(config: Dict[str, Any], save_path: str) -> Dict[str, Any]:
        """
        Process RKNN model configuration.

        Args:
            config: Current pipeline configuration
            save_path: Path to saved RKNN model

        Returns:
            Updated configuration for RKNN model
        """
        updated = dict(config)
        updated["model_type"] = "yolo"
        updated["accelerator"] = "rknn"
        updated["rknn_path"] = save_path

        # Remove incompatible configuration
        updated.pop("converted_onnx_path", None)
        updated.pop("converted_onnx_filename", None)
        updated.pop("tflite_delegate", None)

        logger.debug("Configured RKNN model")
        return updated

    @staticmethod
    def process_onnx_model(
        config: Dict[str, Any],
        pipeline_id: int,
        safe_filename: str,
        save_path: str,
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Process YOLO/ONNX model configuration.

        Args:
            config: Current pipeline configuration
            pipeline_id: Pipeline database ID
            safe_filename: Sanitized filename
            save_path: Path to saved model file

        Returns:
            Tuple of (success, error_message, updated_config)
        """
        updated = dict(config)
        updated["model_type"] = "yolo"
        updated["onnx_provider"] = updated.get("onnx_provider") or "CPUExecutionProvider"
        updated.pop("tflite_delegate", None)

        extension = os.path.splitext(safe_filename)[1].lower()

        # Handle ONNX files directly
        if extension == ".onnx":
            is_valid, message = validate_onnx_model(save_path)
            if not is_valid:
                return False, message, updated

            updated["converted_onnx_path"] = save_path
            updated["converted_onnx_filename"] = safe_filename
            logger.info(f"Validated ONNX model: {safe_filename}")

        # Convert PyTorch/Darknet weights to ONNX
        elif extension in [".pt", ".weights"]:
            base_name = os.path.splitext(safe_filename)[0]
            converted_filename = f"pipeline_{pipeline_id}_{base_name}.onnx"
            converted_path = os.path.join(DATA_DIR, converted_filename)

            success, message, output_path = convert_yolo_weights_to_onnx(
                save_path,
                converted_path,
                img_size=int(updated.get("img_size", 640)),
            )

            if not success:
                ModelService.remove_file(converted_path)
                return False, message, updated

            updated["converted_onnx_path"] = output_path
            updated["converted_onnx_filename"] = os.path.basename(output_path)
            logger.info(f"Converted {safe_filename} to ONNX: {output_path}")

        else:
            return (
                False,
                "Unsupported model format. Upload .onnx, .pt, .weights, .tflite, or .rknn files.",
                updated,
            )

        return True, None, updated

    @staticmethod
    def attempt_rknn_conversion(
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Attempt to convert ONNX model to RKNN if hardware acceleration is available.

        Args:
            config: Current pipeline configuration (must have converted_onnx_path)

        Returns:
            Updated configuration with RKNN path if successful
        """
        updated = dict(config)

        availability = get_ml_availability()
        rknn_supported = (
            availability.get("accelerators", {}).get("rknn", False)
            and updated.get("converted_onnx_path")
        )

        if not rknn_supported:
            # Remove RKNN configuration if not supported
            updated.pop("rknn_path", None)
            if updated.get("accelerator") == "rknn":
                updated["accelerator"] = "none"
            return updated

        # Attempt RKNN conversion
        converted_name = os.path.splitext(
            os.path.basename(updated["converted_onnx_path"])
        )[0]
        rknn_filename = f"{converted_name}.rknn"
        rknn_path = os.path.join(DATA_DIR, rknn_filename)

        success, message, output_path = convert_onnx_to_rknn(
            updated["converted_onnx_path"], rknn_path
        )

        if success and output_path:
            updated["rknn_path"] = output_path
            updated["accelerator"] = "rknn"
            logger.info(f"Successfully converted to RKNN: {output_path}")
        else:
            if message:
                logger.info(f"RKNN conversion skipped: {message}")
            updated.pop("rknn_path", None)
            if updated.get("accelerator") == "rknn":
                updated["accelerator"] = "none"

        return updated

    @staticmethod
    def apply_model_upload(
        pipeline_id: int,
        config: Dict[str, Any],
        safe_filename: str,
        save_path: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Update pipeline configuration after a model upload.

        This method handles model type detection, validation, conversion,
        and configuration updates for uploaded ML models.

        Args:
            pipeline_id: Pipeline database ID
            config: Current pipeline configuration (will be modified in place)
            safe_filename: Sanitized filename
            save_path: Path where model file was saved

        Returns:
            Tuple of (success, error_message)
        """
        updated_config = dict(config)
        updated_config["model_filename"] = safe_filename
        updated_config["model_path"] = save_path
        updated_config.setdefault("accelerator", "none")

        # Infer model type from filename
        inferred_type = infer_model_type(safe_filename) or "yolo"

        # Store previous paths for cleanup
        previous_converted = config.get("converted_onnx_path")
        previous_rknn = config.get("rknn_path")

        # Process based on model type
        if inferred_type == "tflite":
            updated_config = ModelService.process_tflite_model(updated_config)

        elif inferred_type == "rknn":
            updated_config = ModelService.process_rknn_model(updated_config, save_path)

        else:  # YOLO / ONNX
            success, error_msg, updated_config = ModelService.process_onnx_model(
                updated_config, pipeline_id, safe_filename, save_path
            )
            if not success:
                return False, error_msg

            # Attempt RKNN conversion if applicable
            updated_config = ModelService.attempt_rknn_conversion(updated_config)

        # Apply updates atomically
        config.clear()
        config.update(updated_config)

        # Clean up stale artifacts
        if previous_converted and previous_converted != config.get("converted_onnx_path"):
            ModelService.remove_file(previous_converted)
        if previous_rknn and previous_rknn != config.get("rknn_path"):
            ModelService.remove_file(previous_rknn)

        logger.info(f"Successfully processed model upload for pipeline {pipeline_id}")
        return True, None
