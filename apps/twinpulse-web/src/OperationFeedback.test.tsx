// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OperationFeedback } from "./OperationFeedback";

describe("operation feedback", () => {
  it("announces a pending operation without pretending it has finished", () => {
    render(<OperationFeedback busyLabel="Creating preview…" error={null} onDismiss={vi.fn()} />);
    expect(screen.getByRole("status").textContent).toContain("Creating preview");
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("focuses a blocking error, and lets the user dismiss it with Escape", () => {
    const onDismiss = vi.fn();
    render(<OperationFeedback busyLabel={null} error="Scene change failed" onDismiss={onDismiss} />);
    const close = screen.getByRole("button", { name: "Close" });
    expect(screen.getByRole("alertdialog").textContent).toContain("Scene change failed");
    expect(document.activeElement).toBe(close);
    fireEvent.keyDown(close, { key: "Escape" });
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});
