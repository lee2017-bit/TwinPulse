// SPDX-License-Identifier: Apache-2.0
import {useEffect,useRef,useState} from 'react';
import {fleetRobotFresh,type RobotFleetRobot} from './robot-fleet-types';
import {LidarPointView} from './LidarPointView';

// Display only. Native sensor-local points never acquire an Isaac/world TF.
export function PhysicalLidarPanel({robot,rendered,currentRevision,available=true}:{robot:RobotFleetRobot;rendered:boolean;currentRevision?:string;available?:boolean}){
  const [now,setNow]=useState(Date.now);
  useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),250);return()=>clearInterval(timer);},[]);
  const scan=robot.scan;
  const owner=[robot.robot_id,robot.operation_id,robot.connection_epoch].join('/');
  const identity=[scan?.frame_sequence,scan?.raw_sha256,scan?.captured_at_ms].join('/');
  const receipt=useRef({owner,identity,blocked:false,seen:Date.now(),age:robot.scan_receipt?.age_ms});
  if(receipt.current.owner!==owner||receipt.current.identity!==identity)receipt.current={owner,identity,
    blocked:receipt.current.identity===identity&&(receipt.current.owner!==owner||receipt.current.blocked),
    seen:Date.now(),age:robot.scan_receipt?.age_ms};
  const age=typeof receipt.current.age==='number'&&Number.isFinite(receipt.current.age)?receipt.current.age+Math.max(0,now-receipt.current.seen):null;
  const connected=available&&fleetRobotFresh(robot);
  const live=connected&&!receipt.current.blocked&&robot.lidar_state==='STREAMING'&&!!scan&&age!==null&&age>=0&&age<1000;
  const placed=!!robot.display_pose&&robot.display_pose.scene_revision===currentRevision;
  return <aside className="physical-lidar-panel" aria-label="Physical robot and LiDAR">
    <strong>Physical LiDAR</strong>
    <p role="status">{!connected?'Disconnected · no live scan':robot.lidar_state==='OFF'?'Sensor OFF':
      live?`Receiving · ${scan!.points.length} hits · ${Math.round(age!)} ms`:
      robot.lidar_state==='STREAMING'?'Scan unavailable / stale':`Sensor ${robot.lidar_state}`}</p>
    {live?<LidarPointView key={robot.robot_id+robot.connection_epoch} points={scan!.points} source={scan!.source}/>:
      <div className="physical-scan-placeholder">{robot.lidar_state==='OFF'?'Turn LiDAR on after connecting.':'Live sensor-local points appear here.'}</div>}
    <small>Sensor-local view · not projected into the room.</small>
    <details><summary>Alignment</summary><small>Use Import space → Scan alignment to check an initial pose. Turning alone does not establish room alignment. Purple overlays are geometric reviews, not driving approval.</small></details>
    <p className="physical-model-status" role="status">{rendered&&placed?'Robot model visible · estimated':placed?'Estimate saved · model outside view / awaiting render':'Robot not placed in this Twin'}</p>
    <small>{placed?'Estimated anchor, not measured localization.':'Set the Twin robot position below. No robot motion is started.'}</small>
  </aside>;
}
