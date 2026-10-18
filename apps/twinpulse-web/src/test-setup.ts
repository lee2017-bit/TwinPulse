// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

if (!URL.createObjectURL) URL.createObjectURL = vi.fn(() => "blob:preview");
if (!URL.revokeObjectURL) URL.revokeObjectURL = vi.fn();
