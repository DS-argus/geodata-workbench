import { useRef } from "react";
import { useModalA11y } from "./useModalA11y";

type DeleteConfirmDialogProps = {
  open: boolean;
  dialogId: string;
  title: string;
  message: string;
  targetLabel?: string;
  cancelLabel?: string;
  confirmLabel?: string;
  onCancel: () => void;
  onConfirm: () => void;
};

export function DeleteConfirmDialog({
  open,
  dialogId,
  title,
  message,
  targetLabel,
  cancelLabel = "취소",
  confirmLabel = "삭제",
  onCancel,
  onConfirm
}: DeleteConfirmDialogProps) {
  const modalRef = useRef<HTMLDivElement | null>(null);
  useModalA11y({ open, onClose: onCancel, modalRef });

  if (!open) {
    return null;
  }

  return (
    <div className="dialog-backdrop" role="presentation">
      <div
        ref={modalRef}
        className="dialog-card delete-confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={dialogId}
        tabIndex={-1}
      >
        <div className="dialog-head">
          <h4 id={dialogId}>{title}</h4>
          <button className="icon-btn" onClick={onCancel} aria-label="닫기">
            ✕
          </button>
        </div>
        <p>{message}</p>
        {targetLabel ? <p className="delete-target-label">{targetLabel}</p> : null}
        <div className="dialog-actions">
          <button className="ghost" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button className="primary danger" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
