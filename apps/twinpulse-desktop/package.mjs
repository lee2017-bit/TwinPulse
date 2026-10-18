// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {packager} from '@electron/packager';
import {mkdtemp, mkdir, copyFile, writeFile, readFile, access, cp} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.dirname(fileURLToPath(import.meta.url));
const index=process.argv.indexOf('--output');
if(index<0 || !process.argv[index+1]) throw new Error('DESKTOP_OUTPUT_REQUIRED');
const output=path.resolve(process.argv[index+1]);
const sourceIndex=process.argv.indexOf('--source-dir');
const source=sourceIndex>=0 ? path.resolve(process.argv[sourceIndex+1]) : root;
try {await access(output); throw new Error('DESKTOP_OUTPUT_ALREADY_EXISTS');}
catch(error) {if(error.code!=='ENOENT') throw error;}
await mkdir(output,{recursive:true});
// Stage an explicit tiny app. Never package project state, credentials, tests,
// source photographs or the build tool's node_modules into the renderer app.
const staging=await mkdtemp(path.join(output,'app-'));
for(const name of ['main.mjs','preload.cjs','protocol.mjs','automation.cjs','self-test-runner.cjs'])
  await copyFile(path.join(source,name),path.join(staging,name));
for(const name of ['LICENSE','NOTICE'])
  await copyFile(path.join(source,'../..',name),path.join(staging,name));
const metadata=JSON.parse(await readFile(path.join(source,'package.json'),'utf8'));
// Frozen input, inventoried by the Python builder. No browser download/runtime install.
await cp(path.join(source,'testing/playwright-core'),path.join(staging,'testing/playwright-core'),{recursive:true});
const testRuntime=JSON.parse(await readFile(path.join(staging,'testing/playwright-core/package.json'),'utf8'));
if(testRuntime.version!=='1.63.0')throw Error('TEST_RUNTIME_VERSION_MISMATCH');
const installedVersion=JSON.parse(await readFile(path.join(root,'node_modules/electron/package.json'),'utf8')).version;
if(installedVersion!==metadata.devDependencies.electron) throw new Error('DESKTOP_TOOL_VERSION_MISMATCH');
const runtimePackage=Object.fromEntries(Object.entries(metadata).filter(([key])=>
  !['devDependencies','scripts'].includes(key)));
await writeFile(path.join(staging,'package.json'),JSON.stringify(runtimePackage,null,2));
const paths=await packager({dir:staging,out:output,name:'TwinPulseDesktop',
  platform:'win32',arch:'x64',electronVersion:metadata.devDependencies.electron,
  asar:true,overwrite:false,prune:false,quiet:true});
if(paths.length!==1) throw new Error('DESKTOP_PACKAGE_AMBIGUOUS');
process.stdout.write(JSON.stringify({package:paths[0],electron:metadata.devDependencies.electron})+'\n');
