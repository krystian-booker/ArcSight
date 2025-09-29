import cv2
import numpy as np
import json
import threading

class CalibrationManager:
    """Manages the state of active camera calibration sessions."""
    def __init__(self):
        self._sessions = {}
        self._lock = threading.Lock()

    def start_session(self, camera_id, pattern_type, pattern_params, square_size):
        """
        Starts a new calibration session for a camera, resetting any previous data.

        Args:
            camera_id (int): The ID of the camera to calibrate.
            pattern_type (str): The type of pattern (e.g., 'Chessboard').
            pattern_params (dict): Parameters for the pattern (e.g., {'rows': 6, 'cols': 9}).
            square_size (float): The size of one square in the pattern (e.g., in mm).
        """
        with self._lock:
            self._sessions[camera_id] = {
                'pattern_type': pattern_type,
                'pattern_params': pattern_params,
                'square_size': square_size,
                'obj_points': [],  # 3D points in real-world space
                'img_points': [],  # 2D points in image plane
                'frame_shape': None
            }
            print(f"Started calibration session for camera {camera_id}")

    def get_session(self, camera_id):
        """Retrieves the active session for a camera."""
        with self._lock:
            return self._sessions.get(camera_id)

    def end_session(self, camera_id):
        """Ends a calibration session and removes its data."""
        with self._lock:
            if camera_id in self._sessions:
                del self._sessions[camera_id]
                print(f"Ended calibration session for camera {camera_id}")

    def capture_points(self, camera_id, frame):
        """
        Finds the calibration pattern in a frame and adds the points to the session.

        Args:
            frame (np.ndarray): The image frame to process.
            camera_id (int): The ID of the camera for the current session.

        Returns:
            tuple: (success, message, annotated_frame)
        """
        with self._lock:
            session = self._sessions.get(camera_id)
            if not session:
                return False, "No active session", frame

            if session['frame_shape'] is None:
                session['frame_shape'] = frame.shape[:2]

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            if session['pattern_type'] == 'Chessboard':
                rows = session['pattern_params']['rows']
                cols = session['pattern_params']['cols']
                square_size = session.get('square_size', 1.0) # Default to 1.0 if not set
                
                # Prepare object points, like (0,0,0), (20,0,0), (40,0,0) ...
                objp = np.zeros((rows * cols, 3), np.float32)
                objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
                objp = objp * square_size

                # Find the chessboard corners
                ret, corners = cv2.findChessboardCorners(gray, (cols, rows), None)

                if ret:
                    session['obj_points'].append(objp)
                    
                    # Refine corner locations
                    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
                    corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
                    session['img_points'].append(corners2)

                    return True, f"Capture successful ({len(session['img_points'])} total)", frame
                else:
                    return False, "Pattern not found", frame
            
            # Placeholder for other pattern types like AprilGrid
            return False, "Unsupported pattern type", frame

    def calculate_calibration(self, camera_id):
        """
        Performs camera calibration using the accumulated points.

        Returns:
            dict: A dictionary with calibration results or an error.
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
                
                # Calculate reprojection error
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
    Generates a printable chessboard PDF with real-world dimensions into a buffer.
    """
    # Note: The pattern is (cols+1)x(rows+1) squares for cols x rows inner corners.
    board_width_mm = (cols + 1) * square_size_mm
    board_height_mm = (rows + 1) * square_size_mm
    
    page_width_pt, page_height_pt = page_size
    
    # Check if the board fits on the page
    if board_width_mm > page_width_pt / mm or board_height_mm > page_height_pt / mm:
        raise ValueError("Chessboard is larger than the specified page size.")

    # Create the PDF document, writing to the provided buffer
    c = canvas.Canvas(buffer, pagesize=page_size)

    # Calculate offsets to center the board on the page
    x_offset_mm = ((page_width_pt / mm) - board_width_mm) / 2
    y_offset_mm = ((page_height_pt / mm) - board_height_mm) / 2

    # Draw the chessboard squares
    for r in range(rows + 1):
        for col in range(cols + 1):
            if (r + col) % 2 == 1: # Draw only the black squares
                c.setFillColorRGB(0, 0, 0)
                
                # Calculate the position of the bottom-left corner of the square
                x = (x_offset_mm + col * square_size_mm) * mm
                y = (y_offset_mm + r * square_size_mm) * mm
                
                # Draw a rectangle (x, y, width, height), no border
                c.rect(x, y, square_size_mm * mm, square_size_mm * mm, fill=1, stroke=0)
    
    # Save the PDF to the buffer
    c.showPage()
    c.save()


# --- Singleton Instance ---
calibration_manager = CalibrationManager()