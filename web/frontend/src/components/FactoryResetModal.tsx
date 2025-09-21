import { Modal } from './Modal'

interface FactoryResetModalProps {
  open: boolean
  onCancel: () => void
  onConfirm: () => void
}

export function FactoryResetModal({ open, onCancel, onConfirm }: FactoryResetModalProps) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title="Confirm Factory Reset"
      footer={
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md bg-gray-600 px-4 py-2 text-sm font-medium text-white hover:bg-gray-500"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            Factory Reset
          </button>
        </div>
      }
    >
      <p className="text-sm text-gray-200">
        Are you sure you want to factory reset? This will delete all settings and cameras and cannot be undone.
      </p>
    </Modal>
  )
}
