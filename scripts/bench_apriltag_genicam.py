import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np
from harvesters.core import Harvester

from app.pipelines.apriltag_pipeline import AprilTagPipeline


def _load_matrix(path: Optional[str]) -> Optional[np.ndarray]:
    if not path:
        return None
    data = json.loads(Path(path).read_text())
    return np.asarray(data, dtype=np.float32)


def _derive_intrinsics(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    fx = fy = width * 0.9
    cx = width / 2.0
    cy = height / 2.0
    return np.array(
        [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]],
        dtype=np.float32,
    )


def run_benchmark(args: argparse.Namespace) -> Dict[str, Any]:
    if args.config:
        config = json.loads(Path(args.config).read_text())
    else:
        config = {}

    pipeline = AprilTagPipeline(config)

    if args.field_layout:
        layout_payload = json.loads(Path(args.field_layout).read_text())
        from app.apriltag_fields import validate_layout_structure

        is_valid, error = validate_layout_structure(layout_payload)
        if not is_valid:
            raise ValueError(f"Invalid field layout JSON: {error}")
        pipeline._apply_layout(Path(args.field_layout).name, layout_payload)
        pipeline.multi_tag_enabled = True

    # Create a Harvester object
    h = Harvester()

    # Add the CTI file for the camera
    h.add_file(args.cti_file)

    # Update the list of available devices
    h.update()

    # Check if any devices were found
    if not h.device_info_list:
        raise RuntimeError("No GenICam cameras found.")

    print(f"Cameras found: {h.device_info_list}")

    frame_count = 0
    processing_times: list[float] = []
    jitter_samples: list[float] = []
    prev_translation: Optional[np.ndarray] = None
    cam_matrix = None
    dist_coeffs = _load_matrix(args.dist_coeffs) or np.zeros((4, 1), dtype=np.float32)

    # Create an ImageAcquirer object for the specified camera
    with h.create(args.camera_index) as ia:
        # Configure the camera for continuous acquisition
        try:
            ia.remote_device.node_map.AcquisitionMode.value = 'Continuous'
        except Exception as e:
            print(f"Could not set AcquisitionMode to Continuous: {e}")

        # Start image acquisition
        ia.start()
        print(f"Started acquisition. Processing {args.frames} frames...")

        while frame_count < args.frames:
            try:
                # Fetch a buffer with timeout
                with ia.fetch(timeout=5.0) as buffer:
                    # The payload contains the image data
                    component = buffer.payload.components[0]

                    # Reshape the 1D numpy array to a 2D image
                    frame = component.data.reshape(component.height, component.width)

                    # Convert to BGR if the image is grayscale (AprilTag pipeline may expect color)
                    if len(frame.shape) == 2:
                        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

                    if cam_matrix is None:
                        cam_matrix = _load_matrix(args.camera_matrix) or _derive_intrinsics(frame)

                    start = time.perf_counter()
                    result = pipeline.process_frame(frame, cam_matrix, dist_coeffs)
                    elapsed = (time.perf_counter() - start) * 1000.0
                    processing_times.append(elapsed)

                    detections = result.get("detections", [])
                    if detections:
                        translation = detections[0]["camera_to_tag"]["translation"]
                        translation_vec = np.array(
                            [translation["x"], translation["y"], translation["z"]], dtype=np.float32
                        )
                        if prev_translation is not None:
                            jitter_samples.append(
                                float(np.linalg.norm(translation_vec - prev_translation))
                            )
                        prev_translation = translation_vec

                    frame_count += 1

            except Exception as e:
                print(f"Error fetching frame: {e}")
                break

        # Stop the image acquisition
        ia.stop()

    # Clean up
    h.reset()

    fps = frame_count / (sum(processing_times) / 1000.0) if processing_times else 0.0
    jitter = statistics.pstdev(jitter_samples) if len(jitter_samples) > 1 else 0.0

    return {
        "frames_processed": frame_count,
        "mean_latency_ms": statistics.mean(processing_times) if processing_times else 0,
        "p95_latency_ms": statistics.quantiles(processing_times, n=20)[-1]
        if len(processing_times) >= 20
        else max(processing_times, default=0.0),
        "fps": fps,
        "translation_jitter_m": jitter,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark AprilTag pipeline throughput and pose jitter using GenICam camera."
    )
    parser.add_argument(
        "--cti-file",
        type=str,
        required=True,
        help="Path to the GenICam CTI file (e.g., /Applications/Spinnaker/lib/spinnaker-gentl/Spinnaker_GenTL.cti)",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="Camera index to use (default: 0)",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=500,
        help="Number of frames to process (default: 500)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to JSON configuration file for the pipeline",
    )
    parser.add_argument(
        "--camera-matrix",
        type=str,
        default=None,
        help="Path to JSON file with a 3x3 intrinsic matrix",
    )
    parser.add_argument(
        "--dist-coeffs",
        type=str,
        default=None,
        help="Path to JSON file with distortion coefficients",
    )
    parser.add_argument(
        "--field-layout",
        type=str,
        default=None,
        help="Optional path to a WPILib AprilTag field layout JSON",
    )

    args = parser.parse_args()
    metrics = run_benchmark(args)

    print("Frames processed:", metrics["frames_processed"])
    print(f"Mean latency: {metrics['mean_latency_ms']:.2f} ms")
    print(f"P95 latency: {metrics['p95_latency_ms']:.2f} ms")
    print(f"Effective FPS: {metrics['fps']:.2f}")
    print(f"Translation jitter (σ): {metrics['translation_jitter_m']:.4f} m")


if __name__ == "__main__":
    main()
