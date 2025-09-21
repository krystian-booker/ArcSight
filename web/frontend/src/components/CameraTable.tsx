import { Fragment } from 'react'
import type { Camera } from '../types'
import { CameraStatusBadge } from './CameraStatusBadge'

export type CameraStatusState = 'connected' | 'disconnected' | 'checking' | 'error'

interface CameraTableProps {
  cameras: Camera[]
  statuses: Record<number, CameraStatusState>
  onEdit: (camera: Camera) => void
  onDelete: (camera: Camera) => void
  onToggleNodes?: (camera: Camera) => void
  renderNodeSection?: (camera: Camera) => React.ReactNode
}

export function CameraTable({ cameras, statuses, onEdit, onDelete, onToggleNodes, renderNodeSection }: CameraTableProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-800 bg-gray-900">
      <table className="min-w-full divide-y divide-gray-800">
        <thead className="bg-gray-800">
          <tr>
            <th scope="col" className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-400">
              Name
            </th>
            <th scope="col" className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-400">
              Type
            </th>
            <th scope="col" className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-400">
              Identifier
            </th>
            <th scope="col" className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-400">
              Status
            </th>
            <th scope="col" className="relative px-6 py-3">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800 bg-gray-900">
          {cameras.length === 0 && (
            <tr>
              <td colSpan={5} className="px-6 py-6 text-center text-sm text-gray-400">
                No cameras configured.
              </td>
            </tr>
          )}

          {cameras.map((camera) => (
            <Fragment key={camera.id}>
              <tr>
                <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-white">{camera.name}</td>
                <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-300">{camera.camera_type}</td>
                <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-300">{camera.identifier}</td>
                <td className="whitespace-nowrap px-6 py-4 text-sm">
                  <CameraStatusBadge status={statuses[camera.id] ?? 'checking'} />
                </td>
                <td className="whitespace-nowrap px-6 py-4 text-right text-sm font-medium space-x-3">
                  {camera.camera_type === 'GenICam' && onToggleNodes && (
                    <button
                      type="button"
                      className="text-indigo-400 hover:text-indigo-200"
                      onClick={() => onToggleNodes(camera)}
                    >
                      Nodes
                    </button>
                  )}
                  <button type="button" className="text-indigo-400 hover:text-indigo-200" onClick={() => onEdit(camera)}>
                    Edit
                  </button>
                  <button type="button" className="text-red-400 hover:text-red-200" onClick={() => onDelete(camera)}>
                    Delete
                  </button>
                </td>
              </tr>
              {camera.camera_type === 'GenICam' && renderNodeSection && (
                <tr>
                  <td colSpan={5} className="bg-gray-950 px-0 py-0">
                    {renderNodeSection(camera)}
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  )
}
