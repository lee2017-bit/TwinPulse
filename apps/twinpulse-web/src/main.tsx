// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { RobotConsoleEntry } from "./RobotQuickConsole";
import "./styles.css";

const robotConsoleMode = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("robot-console") === "1";
createRoot(document.getElementById("root")!).render(
  <StrictMode>{robotConsoleMode ? <RobotConsoleEntry /> : <App />}</StrictMode>,
);
