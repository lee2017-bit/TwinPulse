// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// User input may be multilingual; product interface copy remains English.
export function isConversationStopRequest(text:string):boolean {
  return ['stop','stop simulation','pause simulation','정지','멈춰'].includes(text.trim().toLowerCase());
}
export function isConversationStatusRequest(text: string): boolean {
  return ['status', 'what is happening?', 'explain status', '현재 상태', '상태'].includes(text.trim().toLowerCase());
}
export function isConversationChoiceRequest(text:string, kind?:string):boolean {
  const aliases:Record<string,string[]>= {
    robot_presence:['simulation only','no physical robot','no robot','로봇 없음','use my robot','i have a robot','physical robot','로봇 있음'],
    robot_selection:['burger3','turtlebot3 burger','burger'],
  };
  return !!kind && !!aliases[kind]?.includes(text.trim().toLowerCase());
}
