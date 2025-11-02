import logging
import cv2
import cv2.aruco as aruco
import numpy as np
import json
import threading
import io
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

logger = logging.getLogger(__name__)


class CalibrationManager:
    """Manages active camera calibration sessions in a thread-safe manner."""

    def __init__(self):
        """Initializes the CalibrationManager."""
        self._sessions = {}
        self._lock = threading.Lock()

    def start_session(self, camera_id, pattern_type, pattern_params):
        """
        Initializes a new calibration session for a specified camera.

        Args:
            camera_id (int): The unique identifier for the camera.
            pattern_type (str): The calibration pattern type ('Chessboard' or 'ChAruco').
            pattern_params (dict): A dictionary of parameters for the pattern.
        """
        with self._lock:
            session = {
                "pattern_type": pattern_type,
                "pattern_params": pattern_params,
                "frame_shape": None,
            }

            if pattern_type == "ChAruco":
                p = pattern_params
                dictionary = aruco.getPredefinedDictionary(
                    getattr(aruco, p["dictionary_name"])
                )
                session["board"] = aruco.CharucoBoard(
                    (p["squares_x"], p["squares_y"]),
                    p["square_size"],
                    p["marker_size"],
                    dictionary,
                )
                session["all_charuco_corners"] = []
                session["all_charuco_ids"] = []
            else:  # Chessboard
                session["obj_points"] = []
                session["img_points"] = []

            self._sessions[camera_id] = session
            logger.info(f"Started {pattern_type} calibration session for camera {camera_id}")

    def get_session(self, camera_id):
        """Retrieves the active calibration session for a given camera."""
        with self._lock:
            return self._sessions.get(camera_id)

    def end_session(self, camera_id):
        """Ends a camera's calibration session and discards its data."""
        with self._lock:
            if camera_id in self._sessions:
                del self._sessions[camera_id]
                logger.info(f"Ended calibration session for camera {camera_id}")

    def capture_points(self, camera_id, frame):
        """
        Processes a frame to find and store calibration pattern points.

        Args:
            camera_id (int): The identifier for the current calibration session.
            frame (np.ndarray): The image frame from the camera.

        Returns:
            tuple: A tuple containing (success, message, annotated_frame).
        """
        with self._lock:
            session = self._sessions.get(camera_id)
            if not session:
                return False, "No active session for this camera.", frame

            if session["frame_shape"] is None:
                session["frame_shape"] = frame.shape[:2]

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            p = session["pattern_params"]

            if session["pattern_type"] == "Chessboard":
                objp = np.zeros((p["rows"] * p["cols"], 3), np.float32)
                objp[:, :2] = np.mgrid[0 : p["cols"], 0 : p["rows"]].T.reshape(-1, 2)
                objp *= p["square_size"]

                flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
                ret, corners = cv2.findChessboardCorners(
                    gray, (p["cols"], p["rows"]), flags=flags
                )

                if ret:
                    session["obj_points"].append(objp)
                    criteria = (
                        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                        30,
                        0.001,
                    )
                    corners2 = cv2.cornerSubPix(
                        gray, corners, (11, 11), (-1, -1), criteria
                    )
                    session["img_points"].append(corners2)

                    capture_count = len(session["img_points"])
                    return True, f"Capture successful ({capture_count} total)", frame
                else:
                    return False, "Chessboard pattern not found.", frame

            elif session["pattern_type"] == "ChAruco":
                board = session["board"]
                detector = aruco.CharucoDetector(board)
                charuco_corners, charuco_ids, marker_corners, marker_ids = (
                    detector.detectBoard(gray)
                )

                if charuco_ids is not None and len(charuco_ids) > 4:
                    session["all_charuco_corners"].append(charuco_corners)
                    session["all_charuco_ids"].append(charuco_ids)

                    capture_count = len(session["all_charuco_corners"])
                    return True, f"Capture successful ({capture_count} total)", frame
                else:
                    return False, "Not enough ChAruco corners found.", frame

            return False, "Unsupported pattern type.", frame

    def calculate_calibration(self, camera_id):
        """
        Calculates camera intrinsic parameters using the captured points.

        Args:
            camera_id (int): The identifier for the session to calibrate.

        Returns:
            dict: Calibration results, including matrix and distortion coefficients.
        """
        with self._lock:
            session = self._sessions.get(camera_id)

            min_captures = 5
            capture_count = 0
            if session:
                if session["pattern_type"] == "ChAruco":
                    capture_count = len(session["all_charuco_corners"])
                else:
                    capture_count = len(session["img_points"])

            if not session or capture_count < min_captures:
                return {
                    "success": False,
                    "error": f"Not enough captures for calibration (need at least {min_captures}).",
                }

            try:
                obj_points = []
                img_points = []

                if session["pattern_type"] == "ChAruco":
                    board_corners = session["board"].getChessboardCorners()
                    for i in range(len(session["all_charuco_corners"])):
                        # For each frame, get the corresponding object and image points
                        frame_obj_pts = board_corners[session["all_charuco_ids"][i]]
                        frame_img_pts = session["all_charuco_corners"][i]
                        obj_points.append(frame_obj_pts)
                        img_points.append(frame_img_pts)
                else:  # Chessboard
                    obj_points = session["obj_points"]
                    img_points = session["img_points"]

                ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
                    objectPoints=obj_points,
                    imagePoints=img_points,
                    imageSize=session["frame_shape"],
                    cameraMatrix=None,
                    distCoeffs=None,
                )

                # Calculate reprojection error for both types
                mean_error = 0
                for i in range(len(obj_points)):
                    imgpoints2, _ = cv2.projectPoints(
                        obj_points[i], rvecs[i], tvecs[i], mtx, dist
                    )
                    error = cv2.norm(img_points[i], imgpoints2, cv2.NORM_L2) / len(
                        imgpoints2
                    )
                    mean_error += error
                reprojection_error = mean_error / len(obj_points)

                return {
                    "success": True,
                    "camera_matrix": json.dumps(mtx.tolist()),
                    "dist_coeffs": json.dumps(dist.tolist()),
                    "reprojection_error": reprojection_error,
                }
            except Exception as e:
                return {"success": False, "error": str(e)}


def generate_charuco_board_pdf(buffer, p, page_size=A4):
    """
    Generates a printable ChAruco board PDF.
    """
    try:
        dictionary = aruco.getPredefinedDictionary(getattr(aruco, p["dictionary_name"]))
        board = aruco.CharucoBoard(
            (p["squares_x"], p["squares_y"]),
            p["square_size"] / 1000,  # Convert mm to meters for aruco lib
            p["marker_size"] / 1000,  # Convert mm to meters for aruco lib
            dictionary,
        )

        # Define image size in pixels (e.g., 200 pixels per square)
        pixels_per_square = 200
        img_size_px = (
            p["squares_x"] * pixels_per_square,
            p["squares_y"] * pixels_per_square,
        )

        # Generate the board image with a small margin
        board_img = board.generateImage(
            img_size_px, marginSize=int(pixels_per_square * 0.1), borderBits=1
        )

        is_success, img_buffer = cv2.imencode(".png", board_img)
        if not is_success:
            raise ValueError("Could not encode ChAruco board image.")

        img_reader = ImageReader(io.BytesIO(img_buffer))

        board_width_mm = p["squares_x"] * p["square_size"]
        board_height_mm = p["squares_y"] * p["square_size"]

        page_width_pt, page_height_pt = page_size
        if board_width_mm > page_width_pt / mm or board_height_mm > page_height_pt / mm:
            raise ValueError("Board dimensions exceed page size.")

        c = canvas.Canvas(buffer, pagesize=page_size)
        x_offset_mm = ((page_width_pt / mm) - board_width_mm) / 2
        y_offset_mm = ((page_height_pt / mm) - board_height_mm) / 2

        c.drawImage(
            img_reader,
            x_offset_mm * mm,
            y_offset_mm * mm,
            width=board_width_mm * mm,
            height=board_height_mm * mm,
            preserveAspectRatio=True,
        )
        c.showPage()
        c.save()

    except Exception as e:
        logger.error(f"Error in generate_charuco_board_pdf: {e}")
        raise


def generate_chessboard_pdf(buffer, rows, cols, square_size_mm, page_size=A4):
    """
    Generates a printable chessboard PDF with specified real-world dimensions.
    """
    board_width_mm = (cols + 1) * square_size_mm
    board_height_mm = (rows + 1) * square_size_mm

    page_width_pt, page_height_pt = page_size

    if board_width_mm > page_width_pt / mm or board_height_mm > page_height_pt / mm:
        raise ValueError("Chessboard dimensions exceed the specified page size.")

    c = canvas.Canvas(buffer, pagesize=page_size)

    x_offset_mm = ((page_width_pt / mm) - board_width_mm) / 2
    y_offset_mm = ((page_height_pt / mm) - board_height_mm) / 2

    for r in range(rows + 1):
        for col in range(cols + 1):
            if (r + col) % 2 == 1:
                c.setFillColorRGB(0, 0, 0)
                x = (x_offset_mm + col * square_size_mm) * mm
                y = (y_offset_mm + r * square_size_mm) * mm
                c.rect(x, y, square_size_mm * mm, square_size_mm * mm, fill=1, stroke=0)

    c.showPage()
    c.save()
