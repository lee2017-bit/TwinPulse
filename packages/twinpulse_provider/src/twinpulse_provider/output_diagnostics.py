# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Content-free output measurements, not a quality verdict or retry authority."""
from collections.abc import Mapping

# Host ceiling only. Providers may impose a smaller output/context limit.
# Defaults stay unchanged, and raising this does not grant more spending.
MAX_STAGE_OUTPUT_TOKENS = 40000


def output_diagnostics(payload):
    if not isinstance(payload, Mapping):
        return {}
    choices = payload.get('choices')
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], Mapping):
        return {}
    choice = choices[0]
    message = choice.get('message')
    if not isinstance(message, Mapping):
        return {}
    visible = message.get('content')
    reasoning = message.get('reasoning_content', message.get('reasoning'))
    visible = visible if isinstance(visible, str) else ''
    reasoning = reasoning if isinstance(reasoning, str) else ''
    usage = payload.get('usage')
    usage = usage if isinstance(usage, Mapping) else {}
    details = usage.get('completion_tokens_details')
    details = details if isinstance(details, Mapping) else {}
    count = usage.get('reasoning_tokens', details.get('reasoning_tokens'))
    reasoning_tokens = count if type(count) is int and count >= 0 else None
    whitespace = sum(c.isspace() for c in visible)
    final_empty = not bool(visible.strip())
    at_limit = choice.get('finish_reason') == 'length'
    if at_limit and final_empty and (reasoning.strip() or (reasoning_tokens or 0) > 0):
        pattern = 'hidden_reasoning_without_final_at_limit'
    elif at_limit and visible and whitespace / len(visible) >= .9:
        pattern = 'visible_whitespace_dominated_at_limit'
    elif at_limit:
        pattern = 'incomplete_final_at_limit'
    elif final_empty:
        pattern = 'empty_final_without_length'
    else:
        pattern = 'final_output_present'
    # Describes this response, not the model's root cause. Never promotes
    # hidden reasoning to scene JSON or changes the output-limit stop rule.
    result = dict(output_pattern=pattern, final_empty=final_empty,
        visible_chars=len(visible), visible_nonwhitespace_chars=len(visible)-whitespace,
        visible_trailing_whitespace_chars=len(visible)-len(visible.rstrip()),
        reasoning_chars=len(reasoning),
        reasoning_nonwhitespace_chars=sum(not c.isspace() for c in reasoning))
    if reasoning_tokens is not None:
        result['reasoning_tokens'] = reasoning_tokens
    if isinstance(choice.get('finish_reason'), str):
        result['finish_reason'] = choice['finish_reason']
    return result
