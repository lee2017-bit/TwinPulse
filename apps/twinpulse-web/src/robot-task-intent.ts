// SPDX-License-Identifier: Apache-2.0
/** UI routing only. The server validates the goal and exact model proposal. */
export function isImmediateRobotStop(text:string):boolean {
  const value=text.trim().toLowerCase();
  return /^(?:please\s+)?(?:stop|cancel|abort|pause)\s+(?:the\s+)?(?:current\s+)?(?:task|mission|survey|exploration|robot)\b/.test(value)
    || /\b(?:stop|abort|pause)\s+(?:now|immediately)\b|즉시.*(?:정지|멈)|(?:탐색|수집|측정|작업|미션).*(?:중지|취소)(?:해줘|해|줘)?[.!?]*$/.test(value);
}
export function isRobotTaskRequest(text:string,robotKind?:string):boolean {
  const value=text.trim().toLowerCase();
  if(isImmediateRobotStop(value))return false;
  if (/만들|생성|배치|옮겨|크기|\b(?:create|build|generate|place|resize|edit)\b/.test(value))return false;
  if (/^(?:정지|멈춰|stop|pause|all robots stop)[.!?]*$/.test(value))return false;
  if(robotKind==='physical'&&/\b(?:bed|chair|desk|sofa|table|wardrobe|storage|shelf)\b|침대|의자|책상|소파|식탁|수납|선반/.test(value)&&/\b(?:go|navigate|approach|move)\b|가줘|가라|이동|접근/.test(value))return true;
  return /둘러|탐색|돌아와|복귀|순찰|측정|수집|왕복|차례|반복|\b(?:survey|explore|inspect|patrol|collect|return|repeat)\b/.test(value)
    || /(?:하고|한\s*뒤|다음|후에|\bthen\b|\band\b).*(?:이동|전진|후진|회전|가줘|멈|돌아|move|forward|back|turn|go|stop)/.test(value);
}
