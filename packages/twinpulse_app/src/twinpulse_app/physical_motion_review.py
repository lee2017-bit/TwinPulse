# SPDX-License-Identifier: Apache-2.0
"""One workspace-owned offline review; never a robot admission authority."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
from threading import Thread
from uuid import uuid4

from .command_broker import BrokerError
from .runtime_paths import child_environment,script_command

class PhysicalMotionReview:
    def __init__(self,devices,source_root,state_root,*,popen=subprocess.Popen,job_factory=None):
        self.devices=devices;self.source_root=Path(source_root);self.root=Path(state_root);self.popen=popen
        self.job_factory=job_factory
        self.job=None;self.thread=None;self.process=None;self.generation=0;self.closed=False;self.results={};self.cleanup_errors=[]

    def _key(self,operation,project):return (operation,project)

    def snapshot(self,operation,project):
        with self.devices.lock:
            job=deepcopy(self.job) if self.job and self.job['operation_id']==operation and self.job['project_id']==project else None
            result=self.results.get(self._key(operation,project))
        if result is None:
            index=self.root/'motion-reviews'/('saved-'+operation+'.json')
            if index.is_file() and not index.is_symlink() and index.stat().st_size<=2*1024*1024:
                try:
                    value=json.loads(index.read_bytes())
                    if (isinstance(value,dict) and value.get('operation_id')==operation and value.get('project_id')==project
                            and value.get('schema')=='physical-motion-review-1.0' and value.get('physical_motion_verified') is False
                            and value.get('authority_restored') is False):result=value
                except (ValueError,OSError):pass
        return dict(schema='physical-motion-review-job-1.0',job=job,review=deepcopy(result),
            scope='HISTORICAL_DERIVED_REVIEW_NOT_CURRENT_RAW_REVALIDATION_OR_BODY_PROOF',authority_restored=False)

    def start(self,operation,project,request):
        with self.devices.lock:
            if self.process is not None and self.process.poll() is None:raise BrokerError('motion_review_busy','Previous review process is still reaping.',status=409)
            if self.closed or self.thread is not None and self.thread.is_alive():raise BrokerError('motion_review_busy','One offline review is already running or reaping.',status=409)
            if self.devices.physical_runtime_active():raise BrokerError('motion_review_active','Review a closed recording while physical robots are idle.',status=409)
            self.generation+=1;token=self.generation
            self.job=dict(job_id=uuid4().hex,operation_id=operation,project_id=project,request_id=request,status='STARTING',cancel_reason=None)
            job=dict(self.job);self.thread=Thread(target=self._run,args=(job,token),name='TwinPulseOfflineMotionReview',daemon=True)
            self.thread.start()
        return self.snapshot(operation,project)

    def cancel_for_start(self,reason='PHYSICAL_START'):
        """Invalidate first, terminate only OUR held helper, never join here.

        Caller holds devices.lock for physical-start admission. A late Popen is
        rechecked by _run and killed. Stop/Disconnect do not call this method.
        """
        with self.devices.lock:
            if not self.thread or not self.thread.is_alive():return
            if self.job and self.job.get('status')=='COMPLETED':return # Immutable accepted result, only persistence remains.
            self.generation+=1
            if self.job:self.job.update(status='CANCEL_REQUESTED',cancel_reason=reason)
            process=self.process
            if process is not None:
                try:process.terminate()
                except OSError:
                    if self.job:self.job['termination_unconfirmed']=True

    def cancel(self,operation,project,job_id):
        with self.devices.lock:
            if not self.job or (self.job['operation_id'],self.job['project_id'],self.job['job_id'])!=(operation,project,job_id):raise BrokerError('motion_review_job','Review job does not match this operation.',status=409)
            self.cancel_for_start('EXPLICIT_CANCEL')
        return self.snapshot(operation,project)

    def _run(self,job,token):
        process=owned=None;errors=[];result=None;exited=False
        out=self.root/'motion-reviews'/'jobs'/job['job_id']
        try:
            if any(p.is_symlink() for p in (out,*out.parents)):raise ValueError('REVIEW_OUTPUT_PATH')
            out.mkdir(parents=True,exist_ok=False)
            command=script_command(self.source_root,'motion-review')+['--state-root',str(self.root),'--operation',job['operation_id'],'--project',job['project_id'],'--job',job['job_id']]
            if os.name=='nt':
                from .process_manager import _WindowsJob
                owned=self.job_factory() if self.job_factory is not None else _WindowsJob('offline-motion-review')
            with (out/'worker.log').open('xb') as log:
                process=self.popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                    env=child_environment(os.environ),creationflags=(subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS) if os.name=='nt' else 0)
                if owned:owned.assign(process)
                with self.devices.lock:
                    self.process=process
                    cancelled=token!=self.generation or self.closed
                    if not cancelled:self.job['status']='RUNNING'
                if cancelled:process.terminate()
                try:code=process.wait(timeout=75);exited=True
                except subprocess.TimeoutExpired:
                    errors.append('REVIEW_DEADLINE');process.terminate()
                    try:process.wait(timeout=3);exited=True
                    except subprocess.TimeoutExpired:
                        if owned:owned.terminate()
                        else:process.kill()
                        process.wait(timeout=3);exited=True
                    code=None
            path=out/'result.json'
            if code==0 and path.is_file() and not path.is_symlink() and path.stat().st_size<=2*1024*1024:
                result=json.loads(path.read_bytes())
                if (not isinstance(result,dict) or any(result.get(k)!=job[k] for k in ('operation_id','project_id','job_id'))
                        or result.get('schema')!='physical-motion-review-1.0' or result.get('physical_motion_verified') is not False
                        or result.get('authority_restored') is not False):raise ValueError('REVIEW_RESULT_BINDING')
            elif not errors:
                with self.devices.lock:still_current=token==self.generation and not self.closed
                if still_current:errors.append('REVIEW_WORKER_FAILED')
        except Exception as error:
            errors.append(type(error).__name__)
        finally:
            if process is not None and not exited:
                try:process.terminate();process.wait(timeout=3);exited=True
                except Exception:errors.append('REVIEW_REAP_UNCONFIRMED')
            if owned:
                try:owned.close()
                except Exception:errors.append('REVIEW_JOB_CLOSE_UNCONFIRMED')
            # Publish only this generation. A cancelled/spawned-late result is
            # retained as a job artifact but cannot become the selected review.
            with self.devices.lock:
                self.cleanup_errors.extend(e for e in errors if e in {'REVIEW_REAP_UNCONFIRMED','REVIEW_JOB_CLOSE_UNCONFIRMED'})
                current=token==self.generation and not self.closed
                if current and result is not None and not errors:
                    self.results[self._key(job['operation_id'],job['project_id'])]=result
                    self.job.update(status='COMPLETED',review_status=result.get('status'))
                elif self.job and self.job['job_id']==job['job_id']:
                    self.job.update(status='INCOMPLETE' if errors else 'CANCELLED' if exited else 'REAPING',errors=errors)
                self.process=None if exited else process
            if current and result is not None and not errors:
                try:
                    index=self.root/'motion-reviews'/('saved-'+job['operation_id']+'.json');temp=index.with_name(index.name+'.'+job['job_id']+'.tmp')
                    raw=json.dumps(result,allow_nan=False,separators=(',',':')).encode()
                    with temp.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
                    # The immutable result was accepted above before marking
                    # COMPLETED. Later physical starts do not wait for this
                    # historical index write, which is outside admission locks.
                    os.replace(temp,index)
                except Exception:
                    with self.devices.lock:
                        self.job.update(status='INCOMPLETE',errors=['REVIEW_SAVE_FAILED'])

    def close(self):
        self.cancel_for_start('APP_CLOSED')
        with self.devices.lock:self.closed=True;thread=self.thread
        if thread:thread.join(timeout=7)
        reaped=not bool(thread and thread.is_alive()) and (self.process is None or self.process.poll() is not None)
        return dict(closed=reaped and not self.cleanup_errors,root_reaped=reaped,evidence_complete=reaped and not self.cleanup_errors,errors=list(self.cleanup_errors))
