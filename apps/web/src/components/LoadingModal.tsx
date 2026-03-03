type LoadingModalProps = {
  open: boolean;
  title: string;
  description?: string;
  progressPercent?: number;
  progressLabel?: string;
  cancelLabel?: string;
  cancelDisabled?: boolean;
  onCancel?: () => void;
};

export function LoadingModal({
  open,
  title,
  description,
  progressPercent,
  progressLabel,
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
        {typeof progressPercent === "number" ? (
          <div className="loading-progress-wrap">
            <div className="loading-progress-track">
              <div
                className="loading-progress-fill"
                style={{ width: `${Math.max(0, Math.min(100, Math.round(progressPercent)))}%` }}
              />
            </div>
            <div className="loading-progress-meta">
              <span>{Math.max(0, Math.min(100, Math.round(progressPercent)))}%</span>
              {progressLabel ? <span>{progressLabel}</span> : null}
            </div>
          </div>
        ) : null}
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
