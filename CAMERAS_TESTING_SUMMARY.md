# Cameras Page E2E Testing and Bug Fixes Summary

## Overview
Fixed critical bugs in the camera API routes and added comprehensive Playwright E2E testing with mock camera support for testing environments.

## Critical Bugs Fixed

### 1. **Form Parameter Mismatch** ✓
**Issue**: Frontend and backend were using different parameter names, causing all add/update operations to fail.

**Frontend sent**:
- `name`
- `camera_type`
- `identifier`

**Backend expected**:
- `camera-name`
- `camera-type`
- Type-specific selects: `usb-camera-select`, `genicam-camera-select`, etc.

**Fix**: Updated backend to accept both naming conventions for backwards compatibility.

**Files changed**: `app/blueprints/cameras/routes.py` (lines 14-79)

### 2. **Return Type Mismatch** ✓
**Issue**: All camera endpoints returned HTTP redirects instead of JSON, breaking the React frontend.

**Affected endpoints**:
- `POST /cameras/add` - Was returning `redirect(url_for("cameras.cameras_page"))`
- `POST /cameras/update/<id>` - Was returning `redirect(...)`
- `POST /cameras/delete/<id>` - Was returning `redirect(...)`

**Fix**: Changed all endpoints to return proper JSON responses:
- Success: `{"success": True, ...}` with 200/201 status
- Error: `{"error": "message"}` with 400/404/500 status

**Files changed**: `app/blueprints/cameras/routes.py`

### 3. **Missing Error Handling** ✓
**Issue**: No validation or error messages for missing/invalid fields.

**Fix**: Added comprehensive error handling:
- 400 Bad Request for missing required fields
- 400 Bad Request for duplicate camera identifiers
- 404 Not Found for camera lookup failures
- 500 Server Error for thread/database failures

### 4. **Testing Mode Not Supported** ✓
**Issue**: No way to test camera functionality without real hardware.

**Fix**: Added testing mode support:
- Mock camera discovery returns test devices when `FLASK_ENV=testing`
- Skip camera thread initialization when `CAMERA_THREADS_ENABLED=False`
- Mock devices for all camera types: USB, GenICam, OAK-D, RealSense

**Files changed**:
- `app/blueprints/cameras/routes.py` - Mock discovery endpoint
- `frontend/playwright.config.ts` - Set testing environment variables

## Mock Camera Support

### Mock Devices Available in Testing Mode

```python
# USB Cameras
{"identifier": "/dev/video0", "name": "Mock USB Camera 0"}
{"identifier": "/dev/video1", "name": "Mock USB Camera 1"}

# GenICam Cameras
{"identifier": "mock-genicam-001", "name": "Mock GenICam Camera"}

# OAK-D Cameras
{"identifier": "mock-oakd-001", "name": "Mock OAK-D Camera"}

# RealSense Cameras
{"identifier": "mock-realsense-001", "name": "Mock RealSense Camera"}
```

### Activation
Mock cameras are automatically activated when:
1. `FLASK_ENV=testing` environment variable is set, OR
2. `app.config['TESTING'] = True`

## Test Coverage

### Test File: `frontend/e2e/cameras.spec.ts` (16 tests, 342 lines)

#### Page Load & Navigation (2 tests)
1. ✓ **Load cameras page** - Page title and Add Camera button visible
2. ✓ **Show empty state** - Empty state message when no cameras configured

#### Add Camera Modal (2 tests)
3. ✓ **Open add camera modal** - Modal appears with all form fields
4. ✓ **Close modal on cancel** - Cancel button closes modal

#### Device Discovery (2 tests)
5. ✓ **Discover mock USB cameras** - Discovery populates device select
6. ✓ **Handle all camera types** - All 4 camera types have mock devices

#### Add Camera Workflow (4 tests)
7. ✓ **Add USB camera successfully** - Full workflow from discovery to table
8. ✓ **Show camera in table** - Correct columns and data display
9. ✓ **Validation error without name** - Error when name field is empty
10. ✓ **Require device discovery** - Error when no device selected

#### Edit Camera (1 test)
11. ✓ **Edit camera name** - Update name and verify persistence

#### Delete Camera (2 tests)
12. ✓ **Show delete confirmation** - Confirmation dialog with warning
13. ✓ **Delete camera successfully** - Remove camera and return to empty state

#### Persistence (1 test)
14. ✓ **Persist across page reload** - Camera survives page refresh

#### Error Handling (2 tests)
15. ✓ **Validation errors** - Missing fields handled gracefully
16. ✓ **All camera types work** - USB, GenICam, OAK-D, RealSense all testable

## API Changes Summary

### `/cameras/add` (POST)
**Before**:
- Expected `camera-name`, `camera-type`, type-specific selects
- Returned redirect on success/failure
- No error messages

**After**:
- Accepts both `name`/`camera-name`, `camera_type`/`camera-type`, `identifier`
- Returns JSON: `{"success": True, "camera_id": 123}` (201)
- Error JSON: `{"error": "message"}` (400/500)
- Skips thread start in testing mode

### `/cameras/update/<id>` (POST)
**Before**:
- Expected `camera-name`
- Returned redirect
- No error handling

**After**:
- Accepts both `name`/`camera-name`
- Returns JSON: `{"success": True, "camera": {...}}` (200)
- Error JSON: `{"error": "Camera not found"}` (404)

### `/cameras/delete/<id>` (POST)
**Before**:
- Returned redirect regardless of result

**After**:
- Returns JSON: `{"success": True}` (200)
- Error JSON: `{"error": "Camera not found"}` (404)
- Error JSON: `{"error": "Failed to stop camera thread"}` (500)

### `/cameras/discover` (GET)
**Before**:
- Only called real hardware discovery
- No testing support

**After**:
- Accepts `camera_type` query parameter
- Returns mock devices in testing mode
- Maintains backwards compatibility with existing code

## Running the Tests

### Prerequisites
```bash
# Install dependencies
cd frontend
npm install
npx playwright install chromium
```

### Run Tests
```bash
# All tests (Settings + Cameras)
npm run test:e2e

# Interactive UI mode
npm run test:e2e:ui

# Headed mode (see browser)
npm run test:e2e:headed

# Single test file
npx playwright test cameras.spec.ts
```

### Environment
Tests automatically start Flask in testing mode:
- `FLASK_ENV=testing` - Enables mock cameras
- `CAMERA_THREADS_ENABLED=False` - Disables camera threads
- Port 8080 - Single port for Vite dev server

## Files Modified

1. **app/blueprints/cameras/routes.py** (225 lines)
   - Fixed `/add`, `/update/<id>`, `/delete/<id>` endpoints
   - Added mock camera discovery
   - Added testing mode support

2. **frontend/e2e/cameras.spec.ts** (342 lines, NEW)
   - 16 comprehensive E2E tests
   - Full add/edit/delete workflow coverage
   - All camera types tested

3. **frontend/playwright.config.ts** (38 lines)
   - Added testing environment variables
   - Flask auto-start configuration

## Known Limitations

1. **Camera Threads**: Tests don't start actual camera threads (by design)
2. **Status Polling**: Camera status always shows "Disconnected" in tests
3. **Video Feeds**: No video feed available in testing mode
4. **Pipeline Results**: No pipeline results in testing mode

These limitations are intentional to allow testing without real hardware.

## Next Steps

Suggested improvements:
1. Add tests for camera controls (exposure, gain, orientation)
2. Add tests for GenICam node configuration
3. Add tests for pipeline association
4. Add visual regression testing for camera table
5. Add performance tests for large camera lists

## Testing Best Practices

1. **Isolation**: Each test adds/removes its own cameras
2. **Cleanup**: Deletion tests verify return to empty state
3. **Waits**: Explicit waits after async operations
4. **Selectors**: Semantic selectors (text, role) preferred over CSS
5. **Independence**: Tests can run in any order
