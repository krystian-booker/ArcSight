import type { FormEvent } from 'react'
import { useEffect, useMemo, useState } from 'react'
import type { GenicamNode } from '../types'

interface GenicamNodeViewerProps {
  cameraId: number
  isOpen: boolean
}

interface UpdateState {
  status: 'idle' | 'pending' | 'success' | 'error'
  message?: string
}

export function GenicamNodeViewer({ cameraId, isOpen }: GenicamNodeViewerProps) {
  const [nodes, setNodes] = useState<GenicamNode[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [showAll, setShowAll] = useState(false)
  const [updateState, setUpdateState] = useState<Record<string, UpdateState>>({})

  useEffect(() => {
    if (isOpen && nodes === null && !loading) {
      void fetchNodes()
    }
    if (!isOpen) {
      setSearchTerm('')
      setShowAll(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, cameraId])

  async function fetchNodes(force = false) {
    if (loading) return
    if (!force && nodes !== null) return

    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`/api/genicam/nodes/${cameraId}`)
      const payload = (await response.json().catch(() => ({}))) as {
        nodes?: GenicamNode[]
        error?: string
      }
      if (!response.ok) {
        throw new Error(payload.error || 'Failed to load node map')
      }
      if (Array.isArray(payload.nodes)) {
        setNodes(payload.nodes)
      } else {
        setNodes([])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load node map')
    } finally {
      setLoading(false)
    }
  }

  const filteredNodes = useMemo(() => {
    if (!nodes) return []

    return nodes.filter((node) => {
      const hasDescription = Boolean(node.description?.trim())
      if (!showAll && !hasDescription) return false
      if (!showAll && (node.value === null || node.value === undefined)) return false
      if (!showAll && node.access_mode === 'RO') return false

      if (!searchTerm) return true
      const haystack = [node.name, node.display_name, node.description].join(' ').toLowerCase()
      return haystack.includes(searchTerm.toLowerCase())
    })
  }, [nodes, searchTerm, showAll])

  async function handleRefresh() {
    setNodes(null)
    await fetchNodes(true)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>, node: GenicamNode) {
    event.preventDefault()
    const form = event.currentTarget
    const formData = new FormData(form)
    const value = formData.get('node-value') as string

    setUpdateState((prev) => ({
      ...prev,
      [node.name]: { status: 'pending' },
    }))

    try {
      const response = await fetch(`/api/genicam/nodes/${cameraId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: node.name,
          value,
        }),
      })

      const payload = (await response.json().catch(() => ({}))) as {
        node?: GenicamNode
        message?: string
        error?: string
      }
      if (!response.ok) {
        throw new Error(payload.error || 'Failed to update node')
      }

      if (payload.node) {
        const updatedNode = payload.node
        setNodes((prev) =>
          prev
            ? prev.map((existing) => (existing.name === updatedNode.name ? { ...existing, value: updatedNode.value } : existing))
            : prev,
        )
      }

      setUpdateState((prev) => ({
        ...prev,
        [node.name]: { status: 'success', message: 'Updated successfully' },
      }))
    } catch (err) {
      setUpdateState((prev) => ({
        ...prev,
        [node.name]: {
          status: 'error',
          message: err instanceof Error ? err.message : 'Failed to update node',
        },
      }))
    }
  }

  if (!isOpen) {
    return null
  }

  return (
    <div className="bg-gray-900 px-6 py-6">
      <div className="flex flex-col gap-4 rounded-lg border border-gray-800 p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="text-lg font-semibold">GenICam Node Map</h3>
            <p className="text-sm text-gray-400">Inspect and configure the camera's remote device parameters.</p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <input
              type="text"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Quick Search..."
              className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <label className="flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={showAll}
                onChange={(event) => setShowAll(event.target.checked)}
                className="rounded border-gray-600 bg-gray-800 text-indigo-600 focus:ring-indigo-500"
              />
              Show All
            </label>
            <button
              type="button"
              onClick={handleRefresh}
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              Refresh
            </button>
          </div>
        </div>

        {loading && <div className="text-sm text-gray-400">Loading node map...</div>}
        {error && <div className="text-sm text-red-400">{error}</div>}

        {!loading && !error && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-800">
              <thead className="bg-gray-800">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-400">
                    Display Name
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-400">Value</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-400">Type</th>
                  {showAll && (
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-400">Access</th>
                  )}
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-400">Update</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800 bg-gray-900">
                {filteredNodes.length === 0 && (
                  <tr>
                    <td colSpan={showAll ? 5 : 4} className="px-4 py-6 text-center text-sm text-gray-400">
                      No configurable nodes reported by this camera.
                    </td>
                  </tr>
                )}

                {filteredNodes.map((node) => {
                  const state = updateState[node.name] ?? { status: 'idle' as const }
                  return (
                    <tr key={node.name} className="align-top">
                      <td className="px-4 py-3">
                        <div className="text-sm font-semibold text-white">{node.display_name || node.name}</div>
                        <div className="break-all text-xs text-gray-400">{node.name}</div>
                        {node.description && <div className="mt-2 text-xs text-gray-500">{node.description}</div>}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-200">
                        {node.is_readable && node.value !== null && node.value !== undefined && node.value !== '' && node.value}
                        {node.is_readable && (node.value === null || node.value === undefined || node.value === '') && (
                          <span className="text-gray-500">Unavailable</span>
                        )}
                        {!node.is_readable && node.is_writable && <span className="text-gray-500">Write only</span>}
                        {!node.is_readable && !node.is_writable && <span className="text-gray-500">Not accessible</span>}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-300">{node.interface_type}</td>
                      {showAll && <td className="px-4 py-3 text-sm text-gray-300">{node.access_mode}</td>}
                      <td className="px-4 py-3 text-sm text-gray-200">
                        {node.is_writable ? (
                          <form
                            className="flex flex-col gap-2 sm:flex-row sm:items-center"
                            onSubmit={(event) => handleSubmit(event, node)}
                          >
                            {renderInputForNode(node)}
                            <button
                              type="submit"
                              disabled={state.status === 'pending'}
                              className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-60"
                            >
                              {state.status === 'pending' ? 'Updating...' : 'Update'}
                            </button>
                          </form>
                        ) : (
                          <span className="text-gray-500">Read-only</span>
                        )}
                        {state.status === 'success' && <div className="text-xs text-green-400">{state.message}</div>}
                        {state.status === 'error' && <div className="text-xs text-red-400">{state.message}</div>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function renderInputForNode(node: GenicamNode) {
  const baseClasses =
    'w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500'

  if (node.interface_type === 'boolean') {
    const normalized = (node.value ?? '').toLowerCase()
    const value = ['false', '0', 'no', 'off'].includes(normalized) ? 'False' : 'True'
    return (
      <select name="node-value" defaultValue={value} className={baseClasses}>
        <option value="True">True</option>
        <option value="False">False</option>
      </select>
    )
  }

  if (node.interface_type === 'enumeration' && node.choices && node.choices.length > 0) {
    const options = node.value && !node.choices.includes(node.value) ? [node.value, ...node.choices] : node.choices
    return (
      <select name="node-value" defaultValue={node.value ?? ''} className={baseClasses}>
        {options.map((choice) => (
          <option key={choice} value={choice}>
            {choice}
          </option>
        ))}
      </select>
    )
  }

  const inputType = node.interface_type === 'integer' || node.interface_type === 'float' ? 'number' : 'text'
  return (
    <input
      type={inputType}
      step={node.interface_type === 'float' ? 'any' : undefined}
      name="node-value"
      defaultValue={node.value ?? ''}
      placeholder="Enter value"
      className={baseClasses}
    />
  )
}
