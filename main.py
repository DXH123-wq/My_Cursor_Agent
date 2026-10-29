import os
import subprocess
import webview
import json
from openai import OpenAI
from dotenv import load_dotenv


# ================= 1. 四个核心工具 =================
def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return "".join([f"{i + 1} | {line}" for i, line in enumerate(lines)]) or "(空文件)"
    except Exception as e:
        return f"报错: {e}"


def write_file(path, content):
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return "写入成功"
    except Exception as e:
        return f"报错: {e}"


def edit_file(path, old_str, new_str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        count = content.count(old_str)
        if count == 0: return "报错：找不到要替换的内容"
        if count > 1: return f"报错：找到 {count} 处匹配，请提供更多上下文"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content.replace(old_str, new_str))
        return "修改成功"
    except Exception as e:
        return f"报错: {e}"


def run_bash(command):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return f"Exit Code: {result.returncode}\nStdout: {result.stdout}\nStderr: {result.stderr}"
    except subprocess.TimeoutExpired:
        return "报错：命令超时"
    except Exception as e:
        return f"报错: {e}"


available_tools = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "run_bash": run_bash
}

# ================= 2. 简化的工具 Schema（防止语法报错） =================
tools_schema = [
    {"type": "function", "function": {"name": "read_file", "description": "读取文件",
                                      "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                                                     "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "写入文件", "parameters": {"type": "object",
                                                                                                      "properties": {
                                                                                                          "path": {
                                                                                                              "type": "string"},
                                                                                                          "content": {
                                                                                                              "type": "string"}},
                                                                                                      "required": [
                                                                                                          "path",
                                                                                                          "content"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "修改文件", "parameters": {"type": "object",
                                                                                                     "properties": {
                                                                                                         "path": {
                                                                                                             "type": "string"},
                                                                                                         "old_str": {
                                                                                                             "type": "string"},
                                                                                                         "new_str": {
                                                                                                             "type": "string"}},
                                                                                                     "required": [
                                                                                                         "path",
                                                                                                         "old_str",
                                                                                                         "new_str"]}}},
    {"type": "function", "function": {"name": "run_bash", "description": "执行命令",
                                      "parameters": {"type": "object", "properties": {"command": {"type": "string"}},
                                                     "required": ["command"]}}}
]

# ================= 3. 大模型连接 =================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
window = None


# ================= 4. API 接口 =================
class API:
    def chat(self, text):
        messages = [{"role": "user", "content": text}]
        try:
            response = client.chat.completions.create(
                model="deepseek-chat", messages=messages, tools=tools_schema, tool_choice="auto"
            )
            response_message = response.choices[0].message

            if response_message.tool_calls:
                messages.append(response_message)
                for tool_call in response_message.tool_calls:
                    name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)

                    if window:
                        window.evaluate_js(
                            f"updateLog('>>> 准备调用工具: {name}，参数: {json.dumps(args, ensure_ascii=False)}')")

                    result = available_tools[name](**args) if name in available_tools else "工具不存在"

                    if window:
                        window.evaluate_js(f"updateLog('--- 执行结果:\\n{result.replace(chr(10), ' ')}')")

                    messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": name, "content": result})

                second_response = client.chat.completions.create(model="deepseek-chat", messages=messages)
                return second_response.choices[0].message.content
            else:
                return response_message.content
        except Exception as e:
            return f"大模型返回异常: {e}"

    def stop(self):
        return "已中断"


if __name__ == '__main__':
    api = API()
    window = webview.create_window("我的 Cursor", "ui/index.html", js_api=api, width=1000, height=700)
    webview.start()