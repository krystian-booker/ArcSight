export interface Camera {
  id: number
  name: string
  camera_type: string
  identifier: string
}

export interface CameraStatusResponse {
  connected: boolean
  error?: string
}

export interface DiscoverResponse {
  usb: { identifier: string; name: string }[]
  genicam: { identifier: string; name: string }[]
}

export interface GenicamNode {
  name: string
  display_name: string
  description: string
  interface_type: string
  access_mode: string
  is_readable: boolean
  is_writable: boolean
  value: string | null
  choices?: string[]
}

export interface SettingsResponse {
  team_number: string
  ip_mode: string
  hostname: string
  genicam_cti_path: string
}

export interface CameraListResponse {
  cameras: Camera[]
  genicam_enabled: boolean
}
