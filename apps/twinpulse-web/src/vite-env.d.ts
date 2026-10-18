/// <reference types="vite/client" />
interface Window {
  twinpulseDesktop?: {
    versions():Promise<Record<string,unknown>>;
    automationStatus?():Promise<{enabled:boolean;state:string;run_id:string|null;report_available:boolean;endpoint?:string;scope:string}>;
    runBasicChecks?():Promise<unknown>;
    openCheckReport?():Promise<unknown>;
    onExitRequested(callback:()=>void):()=>void;
    reportExitResult(result:{requested:boolean;code?:string}):void;
  };
}
// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
