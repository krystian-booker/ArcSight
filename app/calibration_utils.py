import cv2
import numpy as np
import json
import threading

class CalibrationManager:
    """Manages active camera calibration sessions in a thread-safe manner."""

    def __init__(self):
        """Initializes the CalibrationManager."""
        self._sessions = {}
        self._lock = threading.Lock()

    def start_session(self, camera_id, pattern_type, pattern_params, square_size):
        """
        Initializes a new calibration session for a specified camera.

        Args:
            camera_id (int): The unique identifier for the camera.
            pattern_type (str): The calibration pattern type (e.g., 'Chessboard').
            pattern_params (dict): Pattern dimensions (e.g., {'rows': 6, 'cols': 9}).
            square_size (float): The real-world size of a pattern square (e.g., in mm).
        """
        with self._lock:
            self._sessions[camera_id] = {
                'pattern_type': pattern_type,
                'pattern_params': pattern_params,
                'square_size': square_size,
                'obj_points': [],  # 3D points in real-world coordinates
                'img_points': [],  # 2D points on the image plane
                'frame_shape': None
            }
            print(f"Started calibration session for camera {camera_id}")

    def get_session(self, camera_id):
        """
        Retrieves the active calibration session for a given camera.
        """
        with self._lock:
            return self._sessions.get(camera_id)

    def end_session(self, camera_id):
        """
        Ends a camera's calibration session and discards its data.
        """
        with self._lock:
            if camera_id in self._sessions:
                del self._sessions[camera_id]
                print(f"Ended calibration session for camera {camera_id}")

    def capture_points(self, camera_id, frame):
        """
        Processes a frame to find and store calibration pattern points.

        Args:
            camera_id (int): The identifier for the current calibration session.
            frame (np.ndarray): The image frame from the camera.

        Returns:
            tuple: A tuple containing (success, message, frame).
        """
        with self._lock:
            session = self._sessions.get(camera_id)
            if not session:
                return False, "No active session for this camera.", frame

            if session['frame_shape'] is None:
                session['frame_shape'] = frame.shape[:2]

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if session['pattern_type'] == 'Chessboard':
                rows = session['pattern_params']['rows']
                cols = session['pattern_params']['cols']
                square_size = session.get('square_size', 1.0)
                
                # Define the 3D coordinates for an idealized chessboard grid.
                objp = np.zeros((rows * cols, 3), np.float32)
                objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
                objp *= square_size

                ret, corners = cv2.findChessboardCorners(gray, (cols, rows), None)

                if ret:
                    session['obj_points'].append(objp)
                    
                    # Refine corner locations for higher accuracy.
                    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
                    corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
                    session['img_points'].append(corners2)

                    return True, f"Capture successful ({len(session['img_points'])} total)", frame
                else:
                    return False, "Pattern not found.", frame
            
            # Placeholder for other pattern types (e.g., AprilGrid).
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
            if not session or len(session['img_points']) < 5:
                return {'success': False, 'error': 'Not enough captures for calibration.'}

            try:
                ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
                    session['obj_points'],
                    session['img_points'],
                    session['frame_shape'],
                    None,
                    None
                )
                
                # Calculate the mean reprojection error to evaluate accuracy.
                mean_error = 0
                for i in range(len(session['obj_points'])):
                    imgpoints2, _ = cv2.projectPoints(session['obj_points'][i], rvecs[i], tvecs[i], mtx, dist)
                    error = cv2.norm(session['img_points'][i], imgpoints2, cv2.NORM_L2) / len(imgpoints2)
                    mean_error += error
                
                reprojection_error = mean_error / len(session['obj_points'])

                return {
                    'success': True,
                    'camera_matrix': json.dumps(mtx.tolist()),
                    'dist_coeffs': json.dumps(dist.tolist()),
                    'reprojection_error': reprojection_error
                }
            except Exception as e:
                return {'success': False, 'error': str(e)}

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4
import io

def generate_chessboard_pdf(buffer, rows, cols, square_size_mm, page_size=A4):
    """
    Generates a printable chessboard PDF with specified real-world dimensions.

    Args:
        buffer (io.BytesIO): A buffer to write the PDF content to.
        rows (int): The number of inner corners vertically.
        cols (int): The number of inner corners horizontally.
        square_size_mm (float): The side length of each square in millimeters.
        page_size (tuple): The page size, e.g., A4 from reportlab.lib.pagesizes.
    """
    # Note: A pattern with (cols x rows) inner corners has (cols+1) x (rows+1) squares.
    board_width_mm = (cols + 1) * square_size_mm
    board_height_mm = (rows + 1) * square_size_mm
    
    page_width_pt, page_height_pt = page_size
    
    if board_width_mm > page_width_pt / mm or board_height_mm > page_height_pt / mm:
        raise ValueError("Chessboard dimensions exceed the specified page size.")

    c = canvas.Canvas(buffer, pagesize=page_size)

    # Calculate offsets to center the board on the page.
    x_offset_mm = ((page_width_pt / mm) - board_width_mm) / 2
    y_offset_mm = ((page_height_pt / mm) - board_height_mm) / 2

    # Draw the black squares of the chessboard.
    for r in range(rows + 1):
        for col in range(cols + 1):
            if (r + col) % 2 == 1:
                c.setFillColorRGB(0, 0, 0)
                x = (x_offset_mm + col * square_size_mm) * mm
                y = (y_offset_mm + r * square_size_mm) * mm
                c.rect(x, y, square_size_mm * mm, square_size_mm * mm, fill=1, stroke=0)
    
    c.showPage()
    c.save()