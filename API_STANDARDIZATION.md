# API Parameter Naming Standardization

## Summary

Removed all backwards compatibility code and standardized API parameter naming across the entire ArcSight application to use consistent **snake_case** (underscore) naming.

## Changes Made

### Camera Routes (`app/blueprints/cameras/routes.py`)

**Before** (with backwards compatibility):
```python
# Supported both naming conventions
name = request.form.get("name") or request.form.get("camera-name")
camera_type = request.form.get("camera_type") or request.form.get("camera-type")
identifier = request.form.get("identifier")
if not identifier:
    if camera_type == "USB":
        identifier = request.form.get("usb-camera-select")
    # ... etc
```

**After** (standardized):
```python
data = request.get_json() or request.form
name = data.get("name")
camera_type = data.get("camera_type")
identifier = data.get("identifier")
device_info_json = data.get("device_info_json")
```

### Settings Routes (`app/blueprints/settings/routes.py`)

**Before** (with backwards compatibility):
```python
# Support both dash and underscore versions for compatibility
path = (data.get("genicam_cti_path") or data.get("genicam-cti-path", "")).strip()
```

**After** (standardized):
```python
path = data.get("genicam_cti_path", "").strip()
```

## Standardized Parameter Naming Convention

### Application-Wide Standard

All API endpoints now follow this pattern:
```python
data = request.get_json() or request.form
param_name = data.get("param_name")
```

### Snake_case Parameters Only

**Camera Parameters:**
- `name` - Camera name
- `camera_type` - Type: USB, GenICam, OAK-D, RealSense
- `identifier` - Device identifier
- `device_info_json` - Optional device metadata

**Settings Parameters:**
- `team_number` - FRC team number
- `hostname` - Device hostname
- `ip_mode` - IP assignment mode (dhcp/static)
- `genicam_cti_path` - Path to GenICam CTI file
- `field_name` - AprilTag field layout name

### No Longer Supported

The following **dash-case** (hyphenated) parameters are **no longer accepted**:
- ❌ `camera-name`
- ❌ `camera-type`
- ❌ `usb-camera-select`
- ❌ `genicam-camera-select`
- ❌ `oakd-camera-select`
- ❌ `realsense-camera-select`
- ❌ `genicam-cti-path`

## Frontend Alignment

The React frontend was already using the correct snake_case naming:

**Cameras.tsx:**
```typescript
const formData = new FormData()
formData.append('name', newCameraName)
formData.append('camera_type', newCameraType)
formData.append('identifier', selectedDevice)
```

**Settings.tsx:**
```typescript
await api.post('/settings/global/update', {
  team_number: teamNumber,
  hostname: hostname,
  ip_mode: ipMode,
})

await api.post('/settings/genicam/update', {
  genicam_cti_path: genicamPath,
})
```

**No frontend changes were needed** - it was already following the standard.

## Affected Endpoints

### Camera Endpoints
- `POST /cameras/add` - Now requires: `name`, `camera_type`, `identifier`
- `POST /cameras/update/<id>` - Now requires: `name`

### Settings Endpoints
- `POST /settings/global/update` - Uses: `team_number`, `hostname`, `ip_mode`
- `POST /settings/genicam/update` - Uses: `genicam_cti_path`
- `POST /settings/apriltag/select` - Uses: `field_name`

## Benefits

1. **Consistency** - All endpoints use the same naming convention
2. **Clarity** - No confusion about which parameter names to use
3. **Maintainability** - Single pattern to follow throughout codebase
4. **Reduced Code** - Removed 14 lines of backwards compatibility code
5. **Python Convention** - Follows PEP 8 naming standards (snake_case)

## Testing

All Playwright E2E tests pass with the standardized naming:
- ✓ 16 Settings page tests
- ✓ 14 Cameras page tests
- ✓ 30 total tests passing

## Migration Guide

For any external code calling these APIs, update parameter names:

```python
# OLD (no longer works)
requests.post('/cameras/add', data={
    'camera-name': 'Front Camera',
    'camera-type': 'USB',
    'usb-camera-select': '/dev/video0'
})

# NEW (required)
requests.post('/cameras/add', json={
    'name': 'Front Camera',
    'camera_type': 'USB',
    'identifier': '/dev/video0'
})
```

## Files Modified

1. `app/blueprints/cameras/routes.py` - Standardized camera endpoints
2. `app/blueprints/settings/routes.py` - Removed genicam dash-case support

## Commit

Commit: `d46aa67`
Message: "Remove backwards compatibility and standardize API parameter naming"
