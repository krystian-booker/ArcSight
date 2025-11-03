/**
 * Settings-related types
 */

export type IPMode = 'dhcp' | 'static';

export interface GlobalSettings {
  team_number?: number | string;
  hostname?: string;
  ip_mode?: IPMode;
  static_ip?: string;
  static_netmask?: string;
  static_gateway?: string;
}

export interface GenICamSettings {
  cti_path: string;
}

export interface AprilTagFieldLayout {
  name: string;
  is_default: boolean;
  tags: {
    ID: number;
    pose: {
      translation: {
        x: number;
        y: number;
        z: number;
      };
      rotation: {
        quaternion: {
          W: number;
          X: number;
          Y: number;
          Z: number;
        };
      };
    };
  }[];
}

export interface AprilTagFieldsResponse {
  selected_field: string;
  available_fields: string[];
  custom_fields: string[];
  is_default: { [key: string]: boolean };
}

export interface DeviceControlAction {
  action: 'restart' | 'reboot' | 'export-db' | 'import-db' | 'factory-reset';
  confirm?: boolean;
}
