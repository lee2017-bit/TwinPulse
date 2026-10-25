// SPDX-License-Identifier: Apache-2.0
import {describe,it,expect} from 'vitest';
import {isRobotTaskRequest} from './robot-task-intent';
it('Physical semantic destinations use the registered common task path, not the legacy anchor executor',()=>{
  expect(isRobotTaskRequest('Go to nearest sofa','physical')).toBe(true);
  expect(isRobotTaskRequest('가까운 소파로 이동해줘','physical')).toBe(true);
  expect(isRobotTaskRequest('Go to nearest sofa','sim')).toBe(false);
  expect(isRobotTaskRequest('Build a sofa','physical')).toBe(false);
  expect(isRobotTaskRequest('Stop now','physical')).toBe(false);
});
describe('robot task UI routing (not authority)',()=>{
  it('routes general compositions, not just one survey phrase',()=>{
    for(const text of ['방을 이동하며 측정하고 돌아와','Survey the room and return','Move forward 20cm then turn left 90 degrees','Go to chair and go to bed'])expect(isRobotTaskRequest(text)).toBe(true);
  });
  it('keeps emergency primitives and scene edits on existing paths',()=>{
    for(const text of ['stop','Stop survey','Stop the current task','작업 취소해줘','탐색을 즉시 정지해','Forward 10 cm','침대를 만들어줘','Build a room and place a robot'])expect(isRobotTaskRequest(text)).toBe(false);
  });
});
