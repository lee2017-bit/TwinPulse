import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

if (!URL.createObjectURL) URL.createObjectURL = vi.fn(() => "blob:preview");
if (!URL.revokeObjectURL) URL.revokeObjectURL = vi.fn();
