import cv2
import cv2.aruco as aruco
import numpy as np
import json
import threading

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
                'pattern_type': pattern_type,
                'pattern_params': pattern_params,
                'obj_points': [],  # 3D points in real-world coordinates
                'img_points': [],  # 2D points on the image plane
                'frame_shape': None
            }

            if pattern_type == 'ChAruco':
                # Pre-create the board for later use in point detection
                p = pattern_params
                dictionary = aruco.getPredefinedDictionary(getattr(aruco, p['dictionary_name']))
                session['board'] = aruco.CharucoBoard(
                    (p['squares_x'], p['squares_y']),
                    p['square_size'],
                    p['marker_size'],
                    dictionary
                )

            self._sessions[camera_id] = session
            print(f"Started {pattern_type} calibration session for camera {camera_id}")

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
            p = session['pattern_params']

            if session['pattern_type'] == 'Chessboard':
                objp = np.zeros((p['rows'] * p['cols'], 3), np.float32)
                objp[:, :2] = np.mgrid[0:p['cols'], 0:p['rows']].T.reshape(-1, 2)
                objp *= p['square_size']

                ret, corners = cv2.findChessboardCorners(gray, (p['cols'], p['rows']), None)

                if ret:
                    session['obj_points'].append(objp)
                    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
                    corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
                    session['img_points'].append(corners2)
                    return True, f"Capture successful ({len(session['img_points'])} total)", frame
                else:
                    return False, "Chessboard pattern not found.", frame

            elif session['pattern_type'] == 'ChAruco':
                board = session['board']
                parameters = aruco.DetectorParameters()
                corners, ids, _ = aruco.detectMarkers(gray, board.getDictionary(), parameters=parameters)

                if ids is not None and len(ids) > 4: # Require at least 4 markers
                    ret, charuco_corners, charuco_ids = aruco.interpolateCornersCharuco(
                        corners, ids, gray, board)
                    
                    if ret and charuco_corners is not None and charuco_ids is not None and len(charuco_corners) > 4:
                        obj_points, img_points = board.matchImagePoints(charuco_corners, charuco_ids)
                        session['obj_points'].append(obj_points)
                        session['img_points'].append(img_points)
                        return True, f"Capture successful ({len(session['img_points'])} total)", frame
                    else:
                        return False, "Not enough ChAruco corners found.", frame
                else:
                    return False, "Not enough ArUco markers found.", frame
            
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
                # For ChAruco, cv2.aruco.calibrateCameraCharuco could be used for potentially
                # better results, but cv2.calibrateCamera is general and works for both.
                ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
                    objectPoints=session['obj_points'],
                    imagePoints=session['img_points'],
                    imageSize=session['frame_shape'],
                    cameraMatrix=None,
                    distCoeffs=None
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
from reportlab.lib.utils import ImageReader
import io

def generate_charuco_board_pdf(buffer, p, page_size=A4):
    """
    Generates a printable ChAruco board PDF.

    Args:
        buffer (io.BytesIO): Buffer to write the PDF to.
        p (dict): Parameters for the ChAruco board.
        page_size (tuple): Page size from reportlab.
    """
    try:
        dictionary = aruco.getPredefinedDictionary(getattr(aruco, p['dictionary_name']))
        board = aruco.CharucoBoard(
            (p['squares_x'], p['squares_y']),
            p['square_size'],
            p['marker_size'],
            dictionary
        )
        
        # Generate the board image using OpenCV
        img_size_px = (int(p['squares_x'] * 100), int(p['squares_y'] * 100))
        board_img = board.generateImage(img_size_px, marginSize=int(100 * p['square_size'] / p['squares_x']))
        
        # Convert to a format reportlab can use
        is_success, img_buffer = cv2.imencode(".png", board_img)
        if not is_success:
            raise ValueError("Could not encode ChAruco board image.")
        
        img_reader = ImageReader(io.BytesIO(img_buffer))

        # Calculate board dimensions in mm for the PDF
        board_width_mm = p['squares_x'] * p['square_size']
        board_height_mm = p['squares_y'] * p['square_size']
        
        page_width_pt, page_height_pt = page_size
        if board_width_mm > page_width_pt / mm or board_height_mm > page_height_pt / mm:
            raise ValueError("Board dimensions exceed page size.")

        c = canvas.Canvas(buffer, pagesize=page_size)
        x_offset_mm = ((page_width_pt / mm) - board_width_mm) / 2
        y_offset_mm = ((page_height_pt / mm) - board_height_mm) / 2

        c.drawImage(img_reader, x_offset_mm * mm, y_offset_mm * mm, width=board_width_mm * mm, height=board_height_mm * mm)
        
        c.showPage()
        c.save()

    except Exception as e:
        # For debugging purposes, re-raise the exception
        raise e


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