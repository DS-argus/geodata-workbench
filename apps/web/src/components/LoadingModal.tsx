type LoadingModalProps = {
  open: boolean;
  title: string;
  description?: string;
  cancelLabel?: string;
  cancelDisabled?: boolean;
  onCancel?: () => void;
};

export function LoadingModal({
  open,
  title,
  description,
  cancelLabel,
  cancelDisabled = false,
  onCancel
}: LoadingModalProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="loading-modal-backdrop" role="status" aria-live="polite">
      <div className="loading-modal">
        <div className="loading-spinner" />
        <h4>{title}</h4>
        {description ? <p>{description}</p> : null}
        {onCancel ? (
          <button className="ghost danger loading-cancel-btn" onClick={onCancel} disabled={cancelDisabled}>
            {cancelLabel ?? "중단"}
          </button>
        ) : null}
      </div>
    </div>
  );
}
