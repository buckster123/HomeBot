# api.py
# Handles API calls to xAI Grok, with streaming and tool handling. Optimized loop (max 5 iters, better partial handling).

from openai import OpenAI
import json
import time
import base64
import traceback
from tools import TOOLS, fs_read_file, fs_write_file, fs_list_files, fs_mkdir, get_current_time, code_execution, git_ops, db_query, shell_exec, code_lint, api_simulate, langsearch_web_search
from db import memory_insert, memory_query, advanced_memory_consolidate, advanced_memory_retrieve, advanced_memory_prune
import streamlit as st

def call_xai_api(model, messages, sys_prompt, stream=True, image_files=None, enable_tools=False):
    client = OpenAI(api_key=st.secrets["XAI_API_KEY"], base_url="https://api.x.ai/v1", timeout=3600)
    api_messages = [{"role": "system", "content": sys_prompt}] + messages
    if image_files and messages and messages[-1]['role'] == 'user':
        content_parts = [{"type": "text", "text": messages[-1]['content']}]
        for img_file in image_files:
            img_file.seek(0)
            img_data = base64.b64encode(img_file.read()).decode('utf-8')
            content_parts.append({"type": "image_url", "image_url": {"url": f"data:{img_file.type};base64,{img_data}"}})
        api_messages[-1]['content'] = content_parts

    full_response = ""
    def generate(current_messages):
        nonlocal full_response
        max_iterations = 5  # Reduced from 10
        iteration = 0
        previous_tool_names = set()
        progress_metric = 0
        while iteration < max_iterations:
            iteration += 1
            tools_param = TOOLS if enable_tools else None
            response = client.chat.completions.create(
                model=model,
                messages=current_messages,
                tools=tools_param,
                tool_choice="auto" if enable_tools else None,
                stream=stream
            )
            if not stream:
                full_response = response.choices[0].message.content
                yield full_response
                return
            # Handle streaming with proper partial tool call merging
            tool_call_chunks = {}
            chunk_response = ""
            for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    content = delta.content
                    chunk_response += content
                    yield content
                if delta.tool_calls:
                    for tc_chunk in delta.tool_calls:
                        idx = tc_chunk.index
                        if idx not in tool_call_chunks:
                            tool_call_chunks[idx] = {"id": "", "function": {"name": "", "arguments": ""}}
                        if tc_chunk.id:
                            tool_call_chunks[idx]["id"] = tc_chunk.id
                        if tc_chunk.function.name:
                            tool_call_chunks[idx]["function"]["name"] += tc_chunk.function.name
                        if tc_chunk.function.arguments:
                            tool_call_chunks[idx]["function"]["arguments"] += tc_chunk.function.arguments
            full_response += chunk_response
            if not tool_call_chunks:
                break
            yield "\nProcessing tools...\n"
            # Batch and process tool calls
            current_tool_names = {tc["function"]["name"] for tc in tool_call_chunks.values()}
            if current_tool_names == previous_tool_names and len(full_response) == progress_metric and iteration > 1:
                yield "Detected tool loop—breaking."
                break
            previous_tool_names = current_tool_names.copy()
            progress_metric = len(full_response)
            for idx, tc in tool_call_chunks.items():
                func_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                    user = st.session_state.get('user', '')
                    convo_id = st.session_state.get('current_convo_id', 0)
                    if func_name == "fs_read_file":
                        result = fs_read_file(**args)
                    elif func_name == "fs_write_file":
                        result = fs_write_file(**args)
                    elif func_name == "fs_list_files":
                        result = fs_list_files(args.get('dir_path', ""))
                    elif func_name == "fs_mkdir":
                        result = fs_mkdir(**args)
                    elif func_name == "get_current_time":
                        result = get_current_time(args.get('sync', False), args.get('format', 'iso'))
                    elif func_name == "code_execution":
                        result = code_execution(**args)
                    elif func_name == "memory_insert":
                        result = memory_insert(st.session_state['db_conn'], user, convo_id, **args)
                    elif func_name == "memory_query":
                        result = memory_query(st.session_state['db_conn'], user, convo_id, args.get('mem_key'), args.get('limit', 10))
                    elif func_name == "git_ops":
                        result = git_ops(**args)
                    elif func_name == "db_query":
                        result = db_query(**args)
                    elif func_name == "shell_exec":
                        result = shell_exec(**args)
                    elif func_name == "code_lint":
                        result = code_lint(**args)
                    elif func_name == "api_simulate":
                        result = api_simulate(**args)
                    elif func_name == "advanced_memory_consolidate":
                        result = advanced_memory_consolidate(st.session_state['db_conn'], user, convo_id, **args)
                    elif func_name == "advanced_memory_retrieve":
                        result = advanced_memory_retrieve(st.session_state['db_conn'], user, convo_id, **args)
                    elif func_name == "advanced_memory_prune":
                        result = advanced_memory_prune(st.session_state['db_conn'], user, convo_id)
                    elif func_name == "langsearch_web_search":
                        result = langsearch_web_search(**args)
                    else:
                        result = "Unknown tool."
                except Exception as e:
                    result = f"Tool error: {str(e)}"
                yield f"\n[Tool Result ({func_name}): {result}]\n"
                current_messages.append({"role": "tool", "content": result, "tool_call_id": tc["id"]})
        if iteration >= max_iterations:
            yield "Max iterations reached."

    try:
        return generate(api_messages)
    except Exception as e:
        error_msg = f"API Error: {traceback.format_exc()}"
        st.error(error_msg)
        time.sleep(1)  # Exponential backoff start; max 3 retries
        for retry in range(1, 3):
            time.sleep(2 ** retry)
            try:
                return generate(api_messages)
            except:
                pass
        raise e
