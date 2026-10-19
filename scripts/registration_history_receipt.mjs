// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Pure checks on observed App response bodies. Never submits a product action.
export function registrationHistory(chat,robots){
 if(!chat?.session_id||!robots?.length)throw Error('No observed chat/robots');
 const entries=robots.map(robot=>{
  const matches=chat.events.filter(e=>e.type==='fleet_sim_registered'&&e.payload.registration.robot_id===robot.robot_id);
  if(matches.length!==1)throw Error('Missing or duplicate registration event for '+robot.label);
  const event=matches[0],r=event.payload.registration;
  const action=chat.messages.find(m=>m.message_id===event.payload.menu_message_id),reply=chat.messages.find(m=>m.message_id===event.payload.message_id);
  if(r.label!==robot.label||r.model_id!=='turtlebot3_burger'||r.source_twin_context.project_id!==chat.project_id||r.source_twin_context.conversation_session_id!==chat.session_id||
     !action?.content.startsWith('Menu action · Add SIM robot:')||!reply?.content.startsWith('SIM robot registered: '+robot.label+'.')||
     action.role!=='user'||reply.role!=='assistant'||reply.reply_to!==action.message_id||!reply.content.includes('does not connect, display or move'))throw Error('Registration receipt is not factual, linked menu history');
  return {event,action,reply};
 });
 return {project_id:chat.project_id,session_id:chat.session_id,entries:structuredClone(entries)};
}
