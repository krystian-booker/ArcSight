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

    mock_detector_instance = mocker.MagicMock()
    mock_detector_instance.detectBoard.side_effect = [
        (c, i, None, None) for c, i in zip(list_of_fake_corners, list_of_fake_ids)
    ]
    mocker.patch('cv2.aruco.CharucoDetector', return_value=mock_detector_instance)

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

def test_get_non_existent_session(manager):
    """Test that getting a non-existent session returns None."""
    assert manager.get_session(999) is None

def test_capture_fails_if_not_enough_charuco_corners(manager, mocker):
    """Test that ChAruco capture fails if too few corners are visible."""
    camera_id = 6
    params = {
        'squares_x': 5, 'squares_y': 7, 'square_size': 30,
        'marker_size': 15, 'dictionary_name': 'DICT_4X4_50'
    }
    manager.start_session(camera_id, 'ChAruco', params)

    # Mock detector to return only 3 corners (less than the minimum of 4)
    mock_detector_instance = mocker.MagicMock()
    mock_detector_instance.detectBoard.return_value = (
        np.array([[[1,1]],[[2,2]],[[3,3]]]), # corners
        np.array([[1],[2],[3]]), # ids
        None, None
    )
    mocker.patch('cv2.aruco.CharucoDetector', return_value=mock_detector_instance)

    blank_image = np.zeros((480, 640, 3), dtype=np.uint8)
    success, msg, _ = manager.capture_points(camera_id, blank_image)

    assert not success
    assert "Not enough ChAruco corners found" in msg

def test_calculate_calibration_handles_cv2_exception(manager, mocker):
    """Test that a cv2 exception during calculation is caught and handled."""
    camera_id = 7
    params = {'rows': 6, 'cols': 9, 'square_size': 25}
    manager.start_session(camera_id, 'Chessboard', params)

    # Add enough dummy data to pass the initial checks
    session = manager.get_session(camera_id)
    dummy_points = np.zeros((54, 3), np.float32)
    session['obj_points'] = [dummy_points] * 5
    session['img_points'] = [dummy_points[:, :2]] * 5
    session['frame_shape'] = (480, 640)

    # Mock the calibration function to throw an exception
    mocker.patch('cv2.calibrateCamera', side_effect=cv2.error("Test CV2 Error"))

    results = manager.calculate_calibration(camera_id)
    assert not results['success']
    assert "Test CV2 Error" in results['error']

def test_generate_charuco_pdf_handles_imencode_failure(mocker):
    """Test that an exception during PDF generation is handled."""
    mocker.patch('cv2.imencode', return_value=(False, None))
    with pytest.raises(ValueError, match="Could not encode ChAruco board image."):
        buffer = io.BytesIO()
        params = {
            'squares_x': 5, 'squares_y': 7, 'square_size': 30,
            'marker_size': 15, 'dictionary_name': 'DICT_4X4_50'
        }
        generate_charuco_board_pdf(buffer, params)

def test_capture_unsupported_pattern_type(manager):
    """Test capture with an unsupported pattern type returns an error."""
    camera_id = 8
    manager.start_session(camera_id, 'UnsupportedPattern', {})
    blank_image = np.zeros((480, 640, 3), dtype=np.uint8)
    success, msg, _ = manager.capture_points(camera_id, blank_image)
    assert not success
    assert "Unsupported pattern type" in msg

def test_capture_points_with_no_session(manager):
    """Test that capturing points fails if no session has been started."""
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    success, msg, _ = manager.capture_points(999, dummy_frame) # Non-existent camera_id
    assert not success
    assert "No active session for this camera" in msg