// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useRef } from "react";

/** Visible, accessible feedback for local scene operations; never dismisses a pending write. */
export function OperationFeedback({ busyLabel, error, onDismiss }: {
  busyLabel: string | null;
  error: string | null;
  onDismiss: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!error) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    return () => previous?.focus();
  }, [error]);
  if (error) return <div className="operation-feedback-backdrop">
    <div className="operation-feedback-card" role="alertdialog" aria-modal="true"
      aria-labelledby="operation-error-title" aria-describedby="operation-error-description"
      onKeyDown={(event) => {
        if (event.key === "Escape") onDismiss();
        if (event.key === "Tab") { event.preventDefault(); closeRef.current?.focus(); }
      }}>
      <h3 id="operation-error-title">Unable to complete this operation</h3>
      <p id="operation-error-description">{error}</p>
      <p className="fine">If you are unsure whether a change was saved, refresh the current scene before retrying. This operation will not retry automatically.</p>
      <button ref={closeRef} type="button" onClick={onDismiss}>Close</button>
    </div>
  </div>;
  if (busyLabel) return <div className="operation-feedback-backdrop" role="status" aria-live="polite">
    <div className="operation-feedback-card operation-feedback-loading">
      <span className="operation-feedback-spinner" aria-hidden="true" />
      <div><strong>{busyLabel}</strong><p>Waiting for the result. No duplicate request will be sent.</p></div>
    </div>
  </div>;
  return null;
}
