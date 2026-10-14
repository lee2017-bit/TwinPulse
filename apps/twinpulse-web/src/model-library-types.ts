// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
export type LibraryModel = {
  model_id:string;kind:string;family:'home'|'warehouse'|'common';environments:string[];tool:string;
  catalog_version?:string; variants?:string[];finishes?:string[];
  dimensions_m: {default?:number[];minimum?:number[];maximum?:number[]};
};
