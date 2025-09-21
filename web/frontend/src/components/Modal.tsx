import type { PropsWithChildren, ReactNode } from 'react'

interface ModalProps extends PropsWithChildren {
  open: boolean
  title: string
  onClose: () => void
  footer?: ReactNode
}

export function Modal({ open, onClose, title, children, footer }: ModalProps) {
  if (!open) {
    return null
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" aria-hidden="true" onClick={onClose} />
      <div className="relative mx-4 w-full max-w-xl overflow-hidden rounded-lg bg-gray-800 shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-700 px-6 py-4">
          <h3 className="text-lg font-semibold text-white">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-gray-700 px-3 py-1 text-sm font-medium text-white hover:bg-gray-600"
          >
            Close
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-6 py-4 text-sm text-gray-100">{children}</div>
        {footer && <div className="border-t border-gray-700 bg-gray-900 px-6 py-4">{footer}</div>}
      </div>
    </div>
  )
}
