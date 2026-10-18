// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
export type LibraryModel = {
  model_id:string;kind:string;family:'home'|'warehouse'|'common';environments:string[];tool:string;
  catalog_version?:string; variants?:string[];finishes?:string[];
  dimensions_m: {default?:number[];minimum?:number[];maximum?:number[]};
  title?:string; origin?:'builtin'|'model_generated';status?:string;recipe_sha256?:string;
  interpreter_version?:string;created_at_utc?:string;generation_request_id?:string;generator_model?:string;
  support_parts?:string[];validation_scope?:string;
  reusable?:boolean;reuse_problem?:string|null;
  parameters?:{name:string;type:'number'|'integer';minimum:number;maximum:number;default:number}[];
  preview_parts?:{id:string;center:number[];size:number[];material:string;support_top:boolean}[];
};
