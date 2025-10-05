import pytest
import io
import cv2
import cv2.aruco as aruco
import numpy as np
import json
from reportlab.lib.pagesizes import A4

from app.calibration_utils import (
    generate_chessboard_pdf,
    generate_charuco_board_pdf,
    CalibrationManager,
)

# --- PDF Generation Tests ---

def test_generate_chessboard_pdf_success():
    """Test successful generation of a chessboard PDF."""
    buffer = io.BytesIO()
    generate_chessboard_pdf(buffer, rows=5, cols=7, square_size_mm=20)
    pdf_data = buffer.getvalue()
    assert pdf_data.startswith(b'%PDF-')
    assert len(pdf_data) > 100

def test_generate_chessboard_pdf_too_large():
    """Test that chessboard generation fails if the board is larger than the page."""
    with pytest.raises(ValueError):
        buffer = io.BytesIO()
        generate_chessboard_pdf(buffer, rows=50, cols=70, square_size_mm=20)

def test_generate_charuco_board_pdf_success():
    """Test successful generation of a ChAruco board PDF."""
    buffer = io.BytesIO()
    params = {
        'squares_x': 5,
        'squares_y': 7,
        'square_size': 30,
        'marker_size': 15,
        'dictionary_name': 'DICT_4X4_50'
    }
    generate_charuco_board_pdf(buffer, params)
    pdf_data = buffer.getvalue()
    assert pdf_data.startswith(b'%PDF-')
    assert len(pdf_data) > 100

def test_generate_charuco_board_pdf_too_large():
    """Test that ChAruco generation fails if the board is larger than the page."""
    with pytest.raises(ValueError, match="Board dimensions exceed page size."):
        buffer = io.BytesIO()
        params = {
            'squares_x': 5,
            'squares_y': 7,
            'square_size': 100,  # 5*100mm = 500mm, larger than A4 width
            'marker_size': 50,
            'dictionary_name': 'DICT_4X4_50'
        }
        generate_charuco_board_pdf(buffer, params)

def test_generate_charuco_invalid_dictionary():
    """Test that ChAruco generation fails with an invalid dictionary name."""
    with pytest.raises(AttributeError):
        buffer = io.BytesIO()
        params = {
            'squares_x': 5,
            'squares_y': 7,
            'square_size': 30,
            'marker_size': 15,
            'dictionary_name': 'DICT_INVALID_NAME'
        }
        generate_charuco_board_pdf(buffer, params)


# --- CalibrationManager Tests ---

@pytest.fixture
def manager():
    """Provides a fresh CalibrationManager for each test."""
    return CalibrationManager()

def test_session_management(manager):
    """Test starting, getting, and ending a calibration session."""
    camera_id = 1
    params = {'rows': 6, 'cols': 9, 'square_size': 25}
    manager.start_session(camera_id, 'Chessboard', params)
    session = manager.get_session(camera_id)
    assert session is not None
    assert session['pattern_type'] == 'Chessboard'
    assert 'obj_points' in session
    manager.end_session(camera_id)
    session = manager.get_session(camera_id)
    assert session is None

def test_chessboard_calibration_flow(manager, mocker):
    """Test the full chessboard calibration flow by mocking the detector."""
    camera_id = 2
    rows, cols = 6, 9
    params = {'rows': rows, 'cols': cols, 'square_size': 25}
    manager.start_session(camera_id, 'Chessboard', params)

    # Create plausible fake corners that are geometrically consistent
    objp = np.zeros((rows * cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    base_2d_points = objp[:, :2].reshape(-1, 1, 2)

    list_of_fake_corners = []
    for i in range(10):
        offset = np.random.uniform(-5, 5, (1, 1, 2))
        scale = np.random.uniform(0.8, 1.2)
        corners = (base_2d_points * scale) + offset
        list_of_fake_corners.append(corners.astype(np.float32))
    
    mocker.patch('cv2.findChessboardCorners', side_effect=[(True, c) for c in list_of_fake_corners])
    mocker.patch('cv2.cornerSubPix', side_effect=list_of_fake_corners)
    
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    for i in range(10):
        success, msg, _ = manager.capture_points(camera_id, dummy_frame)
        assert success, f"Capture failed on iteration {i}: {msg}"

    results = manager.calculate_calibration(camera_id)
    assert results['success'], f"Calibration calculation failed: {results.get('error')}"
    assert 'camera_matrix' in results
    assert 'dist_coeffs' in results
    assert results['reprojection_error'] < 0.1

def test_charuco_calibration_flow(manager, mocker):
    """Test the full ChAruco calibration flow by mocking the detector."""
    camera_id = 3
    params = {
        'squares_x': 5, 'squares_y': 7, 'square_size': 30,
        'marker_size': 15, 'dictionary_name': 'DICT_4X4_50'
    }
    manager.start_session(camera_id, 'ChAruco', params)
    board = manager.get_session(camera_id)['board']
    all_board_corners = board.getChessboardCorners()
    
    num_visible_corners = 15
    list_of_fake_corners = []
    list_of_fake_ids = []

    for i in range(10):
        visible_indices = np.random.choice(len(all_board_corners), num_visible_corners, replace=False)
        obj_pts_subset = all_board_corners[visible_indices]
        img_pts_subset = obj_pts_subset[:, :2].copy()
        
        offset = np.random.uniform(-5, 5, (1, 2))
        scale = np.random.uniform(0.8, 1.2)
        img_pts_subset = (img_pts_subset * scale) + offset

        list_of_fake_corners.append(img_pts_subset.reshape(-1, 1, 2).astype(np.float32))
        list_of_fake_ids.append(visible_indices.reshape(-1, 1))

    mocker.patch('cv2.aruco.CharucoDetector.detectBoard', side_effect=[
        (c, i, None, None) for c, i in zip(list_of_fake_corners, list_of_fake_ids)
    ])

    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    for i in range(10):
        success, msg, _ = manager.capture_points(camera_id, dummy_frame)
        assert success, f"Capture failed on iteration {i}: {msg}"

    results = manager.calculate_calibration(camera_id)
    assert results['success'], f"Calibration calculation failed: {results.get('error')}"
    assert 'camera_matrix' in results
    assert 'dist_coeffs' in results
    assert results['reprojection_error'] < 0.1

def test_calibration_fails_with_insufficient_captures(manager):
    """Test that calibration fails if not enough points are captured."""
    camera_id = 4
    params = {'rows': 6, 'cols': 9, 'square_size': 25}
    manager.start_session(camera_id, 'Chessboard', params)
    results = manager.calculate_calibration(camera_id)
    assert not results['success']
    assert 'Not enough captures' in results['error']

def test_capture_fails_if_pattern_not_found(manager, mocker):
    """Test that point capture fails when the mocked detector finds nothing."""
    camera_id = 5
    params = {'rows': 6, 'cols': 9, 'square_size': 25}
    manager.start_session(camera_id, 'Chessboard', params)
    
    mocker.patch('cv2.findChessboardCorners', return_value=(False, None))
    
    blank_image = np.zeros((480, 640, 3), dtype=np.uint8)
    success, msg, _ = manager.capture_points(camera_id, blank_image)

    assert not success
    assert "pattern not found" in msg.lower()