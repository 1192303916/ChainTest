import copy
import os.path
import sys
import textwrap
import time
import openai
from tools import *
import random
import concurrent.futures
import javalang
import jinja2
from colorama import Fore, Style, init
from task import Task
from database import database
from typing import Dict, List, Tuple

init()
# Create a jinja2 environment
env = jinja2.Environment(loader=jinja2.FileSystemLoader('../prompt'))


def ask_chatgpt(messages, save_path):
    """
    Send messages to GPT, and save its response.
    :param messages: The messages to send to OpenAI.
    :param save_path: The path to save the result.
    :return: [{"role":"user","content":"..."}]
    """
    # Send a request to OpenAI
    openai.api_key = api_key
    openai.api_base = "https://api.f2gpt.com/v1"
    max_try = 5
    while max_try:
        try:
            completion = openai.ChatCompletion.create(messages=messages,
                                                      model=model,
                                                      temperature=temperature,  #生成文本的随机性。
                                                      top_p=top_p,  #采样的概率分布控制。
                                                      frequency_penalty=frequency_penalty,
                                                      presence_penalty=presence_penalty)  #frequency_penalty / presence_penalty：对重复词汇或句子的惩罚参数。
            with open(save_path, "w") as f:
                json.dump(completion, f)   #写入文件，如../result/scope_test%20250102195840%/1%Chart%BankAccount%BankAccount%d1/1/1_GPT_1.json
            que_save_path = os.path.join(os.path.dirname(save_path),os.path.splitext(os.path.basename(save_path))[0].replace("GPT","QUE") + ".txt")
            with open(que_save_path, "w",encoding="utf-8") as f:
                f.write(json.dumps(messages, ensure_ascii=False, indent=2))
            return True  #请求成功后，将响应保存为 JSON 格式到 save_path，并返回 True。
        except Exception as e:
            print(Fore.RED + str(e), Style.RESET_ALL)
            if "This model's maximum context length is 4097 tokens." in str(e):
                break  #如果错误提示上下文长度超出模型限制，直接退出重试。
            time.sleep(10)
            # If rate limit reached we wait a random sleep time
            if "Rate limit reached" in str(e):
                sleep_time = random.randint(60, 120)
                time.sleep(sleep_time)  #如果触发速率限制错误，随机等待 60 到 120 秒后重试。
        max_try -= 1
    return False


def generate_prompt(template_name, context: dict):
    """
    Generate prompt via jinja2 engine
    :param template_name: the name of the prompt template
    :param context: the context to render the template
    :return:
    """
    # Load template
    template = env.get_template(template_name)  #从指定的模板路径中加载名称为 template_name 的模板。
    prompt = template.render(context)  #使用 Jinja2 的 render 方法将上下文变量应用到模板中，生成渲染后的内容。上下文字典中的键值对会被注入到模板中，替换其中对应的占位符。

    return prompt


def load_context_file(context_file):
    if isinstance(context_file, str):
        with open(context_file, "r") as f:
            return json.load(f)
    return context_file


def generate_messages(template_name, context_file):
    """
    This function generates messages before asking GPT, using user and system templates.
    :param template_name: The template name of the user template.
    :param context_file: The context JSON file or dict to render the template.
    :return: A list of generated messages.
    """
    context = load_context_file(context_file)
    messages = []

    system_name = f"{template_name.split('.')[0]}_system.jinja2"  #根据 template_name 推导出系统模板的文件名，如d1_3_system.jinja2
    system_path = os.path.join("../prompt", system_name)   #构造系统模板的路径
    if os.path.exists(system_path):
        system_message = generate_prompt(system_name, context)
        messages.append({"role": "system", "content": system_message})  #将生成的系统消息追加到 messages 列表

    user_message = generate_prompt(template_name, context)
    messages.append({"role": "user", "content": user_message})  #将用户消息追加到 messages 列表

    return messages


def complete_code(code):
    """
    To complete the code
    :param code:
    :return:
    """

    # We delete the last incomplete test.
    code = code.split("@Test\n")
    code = "@Test\n".join(code[:-1]) + '}'
    return code


def process_error_message(error_message, allowed_tokens):
    """
    Process the error message
    :param error_message:
    :param allowed_tokens:
    :return:
    """
    if allowed_tokens <= 0:
        return ""
    while count_tokens(error_message) > allowed_tokens:
        if len(error_message) > 50:
            error_message = error_message[:-50]
        else:
            break
    return error_message


def if_code_is_valid(code) -> bool:
    """
    Check if the code is valid
    :param code:
    :return: True or False
    """
    if "{" not in code or "}" not in code:
        return False
    try:
        javalang.parse.parse(code)
        return True
    except Exception:
        return False


def syntactic_check(code):
    """
    Syntactic repair
    :param code:
    :return: has_syntactic_error, code
    """
    if is_syntactic_correct(code):
        return False, code
    else:
        stop_point = [";", "}", "{", " "]  # Stop point
        for idx in range(len(code) - 1, -1, -1):
            if code[idx] in stop_point:
                code = code[:idx + 1]
                break
        left_bracket = code.count("{")
        right_bracket = code.count("}")
        for idx in range(left_bracket - right_bracket):
            code += "}\n"

        if is_syntactic_correct(code):
            return True, code

        matches = list(re.finditer(r"(?<=\})[^\}]+(?=@)", code))
        if matches:
            code = code[:matches[-1].start() + 1]
            left_count = code.count("{")
            right_count = code.count("}")
            for _ in range(left_count - right_count):
                code += "\n}"
        if is_syntactic_correct(code):
            return True, code
        else:
            return True, ""


def is_syntactic_correct(code):
    """
    Check if the code is syntactically correct
    :param code:
    :return:
    """
    try:
        javalang.parse.parse(code)
        return True
    except Exception as e:
        return False


def extract_code(string):
    """
    Check if the string is valid code and extract it.
    :param string:
    :return: has_code, extracted_code, has_syntactic_error
    """
    # if the string is valid code, return True
    if is_syntactic_correct(string):  #调用 is_syntactic_correct 检查整个字符串是否是语法正确的代码。
        return True, string, False

    has_code = False
    extracted_code = ""
    has_syntactic_error = False

    # Define regex pattern to match the code blocks
    pattern = r"```[java]*([\s\S]*?)```"

    # Find all matches in the text
    matches = re.findall(pattern, string)
    if matches:
        # Filter matches to only include ones that contain "@Test"
        filtered_matches = [match.strip() for match in matches if
                            "@Test" in match and "class" in match and "import" in match]
        if filtered_matches:
            for match in filtered_matches:
                has_syntactic_error, extracted_code = syntactic_check(match)
                if extracted_code != "":
                    has_code = True
                    break

    if not has_code:
        if "```java" in string:
            separate_string = string.split("```java")[1]
            if "@Test" in separate_string:
                has_syntactic_error, temp_code = syntactic_check(separate_string)
                if temp_code != "":
                    extracted_code = temp_code
                    has_code = True
        elif "```" in string:
            separate_strings = string.split("```")
            for separate_string in separate_strings:
                if "@Test" in separate_string:
                    has_syntactic_error, temp_code = syntactic_check(separate_string)
                    if temp_code != "":
                        extracted_code = temp_code
                        has_code = True
                        break
        else:  # Define boundary
            allowed = ["import", "packages", "", "@"]
            code_lines = string.split("\n")
            start, anchor, end = -1, -1, -1
            allowed_lines = [False for _ in range(len(code_lines))]
            left_brace = {x: 0 for x in range(len(code_lines))}
            right_brace = {x: 0 for x in range(len(code_lines))}
            for i, line in enumerate(code_lines):
                left_brace[i] += line.count("{")
                right_brace[i] += line.count("}")
                striped_line = line.strip()

                for allow_start in allowed:
                    if striped_line.startswith(allow_start):
                        allowed_lines[i] = True
                        break

                if re.search(r'public class .*Test', line) and anchor == -1:
                    anchor = i

            if anchor != -1:
                start = anchor
                while start:
                    if allowed_lines[start]:
                        start -= 1

                end = anchor
                left_sum, right_sum = 0, 0
                while end < len(code_lines):
                    left_sum += left_brace[end]
                    right_sum += right_brace[end]
                    if left_sum == right_sum and left_sum >= 1 and right_sum >= 1:
                        break
                    end += 1

                temp_code = "\n".join(code_lines[start:end + 1])
                has_syntactic_error, temp_code = syntactic_check(temp_code)
                if temp_code != "":
                    extracted_code = temp_code
                    has_code = True

    extracted_code = extracted_code.strip()
    return has_code, extracted_code, has_syntactic_error


def extract_and_run(input_string, output_path, class_name, method_id, test_num, project_name, package):
    """
    Extract the code and run it
    :param project_name:
    :param test_num:
    :param method_id:
    :param class_name:
    :param input_string:
    :param output_path:
    :return:
    """
    result = {}
    # 1. Extract the code
    has_code, extracted_code, has_syntactic_error = extract_code(input_string)  #extract_code 函数解析 input_string，提取代码并返回以下值：has_code: 是否成功提取到代码。extracted_code: 提取的代码内容。has_syntactic_error: 是否存在语法错误。
    if not has_code:
        return False, True  #如果未能提取代码，则直接返回：False 表示测试未通过。True 表示发生致命错误。
    #######移除包信息
    if extracted_code.startswith("package "):
        extracted_code = "\n".join(extracted_code.split("\n")[1:])
    ##########
    result["has_code"] = has_code
    result["source_code"] = extracted_code
    if package:
        result["source_code"] = repair_package(extracted_code, package)  #修复代码中的包导入路径
    result["has_syntactic_error"] = has_syntactic_error
    # 2. Run the code
    temp_dir = os.path.join(os.path.dirname(output_path), "temp")  #os.path.dirname(path)结果是path的上一级目录,如../result/scope_test%20250102195840%/1%Chart%BankAccount%BankAccount%d1/1/temp
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)  #创建一个临时目录 temp用于存储测试过程中生成的文件。

    export_method_test_case(os.path.abspath(temp_dir), class_name, method_id, test_num,
                            change_class_name(result["source_code"], class_name, method_id, test_num))  #根据类名、方法 ID 和测试编号，生成并导出测试用例到临时目录。

    # run test
    response_dir = os.path.abspath(os.path.dirname(output_path))  #保存测试输出的路径如../result/scope_test%20250102195840%/1%Chart%BankAccount%BankAccount%d1/1
    target_dir = os.path.abspath(project_dir)  #项目目录，包含代码文件
    Task.test(response_dir, target_dir)

    # 3. Read the result
    if "compile_error.txt" in os.listdir(temp_dir):
        with open(os.path.join(temp_dir, "compile_error.txt"), "r") as f:
            result["compile_error"] = f.read()

    if "runtime_error.txt" in os.listdir(temp_dir):
        with open(os.path.join(temp_dir, "runtime_error.txt"), "r") as f:
            result["runtime_error"] = f.read()
    if "coverage.html" in os.listdir(temp_dir):
        result["coverage_html"] = True
    if "coverage.xml" in os.listdir(temp_dir):
        result["coverage_xml"] = True

    test_passed = False
    if "coverage_xml" in result or "coverage_html" in result:
        test_passed = True

    # 4. Save the result
    with open(output_path, "w") as f:
        json.dump(result, f)

    return test_passed, False


def remain_prompt_tokens(messages):
    return MAX_PROMPT_TOKENS - get_messages_tokens(messages)

###########以下为新的内容，提取evosuite测试用例的单个方法
def extract_method_block(content, start_pos):
    """辅助函数：从起始位置提取完整的方法代码块（补全大括号匹配）"""
    block = []
    brace_count = 0
    in_string = False
    escape = False

    for i in range(start_pos, len(content)):
        char = content[i]

        # 处理字符串中的大括号（避免误判）
        if char == '"' and not escape:
            in_string = not in_string
        elif char == '\\' and not escape:
            escape = True
        else:
            escape = False

        # 统计大括号层级
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    block.append(char)
                    break

        block.append(char)

    return ''.join(block)


def extract_tests(test_method, file_path, output_dir):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 移除文件顶部注释块 /* ... */
    content = re.sub(r'^/\*.*?\*/\s*', '', content, flags=re.DOTALL)

    # 匹配所有以 @Test 或 @Test(...) 开头的测试方法定义
    method_start_pattern = re.compile(
        r'@Test(?:\s*\([^)]*\))?\s*public void (test\d+)\s*\(\)\s*throws Throwable\s*\{',
        re.DOTALL
    )

    matches = list(method_start_pattern.finditer(content))

    output_file_path = output_dir
    count = 0

    with open(output_file_path, 'w', encoding='utf-8') as out_file:
        for match in matches:
            method_name = match.group(1)
            full_block = extract_method_block(content, match.start())

            # ========== 核心修改：方法名前后无字母的精准匹配 ==========
            # 构建正则：匹配 test_method 作为独立单词（前后非字母）
            # \W 匹配非字母数字下划线，^/$ 匹配开头/结尾，确保无字母拼接
            exact_pattern = re.compile(
                rf'(?<!\w){re.escape(test_method)}(?!\w)',  # 负向断言：前后无字母/数字/下划线
                re.IGNORECASE  # 可选：忽略大小写，根据需求调整
            )

            # 仅当精准匹配到独立的 test_method 时才提取
            if exact_pattern.search(full_block):
                if count == 0:
                    # 提取类定义前缀（如 package、import、class）
                    header_pattern = re.compile(r'(?s)(.*?public class\s+\w+\s+extends\s+\w+\s*\{)')
                    header_match = header_pattern.search(content)
                    header = header_match.group(1) if header_match else ''
                    out_file.write(header + "\n\n")

                # 缩进输出
                indented = textwrap.indent(full_block, '    ')
                out_file.write(indented + "\n\n")
                count += 1

        if count == 0:
            out_file.write("No test cases have been generated yet. You need to create a new one on your own, covering all branch paths as much as possible and following the same rules.")
            print(f"未找到与方法名 '{test_method}' 相关的测试，已写入到 {output_file_path}")
            return "null"
        else:
            out_file.write("}")

    # 再次确认类结束符存在
    with open(output_file_path, 'r+', encoding='utf-8') as check_file:
        file_content = check_file.read()
        if count > 0 and not file_content.strip().endswith('}'):
            check_file.write("}")

#############################^^^^^^^^^^
def get_step_and_round(save_dir: str) :

    # 定义匹配文件名的正则表达式
    # 匹配：数字_GPT_数字.json 格式，捕获两个数字组
    pattern = re.compile(r'^(\d+)_GPT_(\d+)\.json$')

    # 存储有效文件的(step, round)元组
    valid_files = []

    # 检查目录是否存在
    if not os.path.isdir(save_dir):
        return 0, 0

    # 遍历目录下的所有文件
    for filename in os.listdir(save_dir):
        # 匹配文件名格式
        match = pattern.match(filename)
        if match:
            try:
                # 提取并转换为整数
                step = int(match.group(1))
                round_num = int(match.group(2))
                valid_files.append((step, round_num))
            except ValueError:
                # 理论上正则已确保是数字，此处为容错处理
                continue

    # 无有效文件时返回(0, 0)
    if not valid_files:
        return 0, 0

    # 找到step最大的文件（根据题目规律，step最大对应round也最大）
    max_item = max(valid_files, key=lambda x: x[0])
    return max_item[0]+2, max_item[1]


def get_complex_flag(project_dir: str, method_id: int, max_rounds: int) -> int:
    """
    第二个方法：根据ID获取complex.txt中对应的标记，并返回对应倍数的max_rounds
    """
    complex_file_path = os.path.join(project_dir, "complex.txt")

    # 检查文件是否存在
    if not os.path.isfile(complex_file_path):
        raise FileNotFoundError(f"complex.txt文件不存在: {complex_file_path}")

    # 读取文件并构建ID到标记的映射
    id_flag_map: Dict[int, int] = {}
    with open(complex_file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            # 清理行首尾空白字符
            line = line.strip()
            if not line:
                continue  # 跳过空行
            # 分割行内容（兼容多个空格/制表符分隔）
            parts = line.split()
            if len(parts) != 2:
                print(f"警告：complex.txt第{line_num}行格式错误，跳过（内容：{line}）")
                continue
            try:
                file_id = int(parts[0])
                flag = int(parts[1])
                # 确保标记只能是1或0
                if flag not in (0, 1):
                    print(f"警告：complex.txt第{line_num}行标记无效（{flag}），强制设为0")
                    flag = 0
                id_flag_map[file_id] = flag
            except ValueError:
                print(f"警告：complex.txt第{line_num}行数字解析失败，跳过（内容：{line}）")
                continue

    # ========== 核心修改：根据标记计算返回值 ==========
    target_flag = id_flag_map.get(method_id, 0)  # ID不存在默认返回0
    if target_flag == 1:
        return 2 * max_rounds
    else:
        return max_rounds

# def whole_process(test_num, base_name, base_dir, repair, submits, total):  #测试和修复流程，用于对某个方法执行多轮的测试和修复操作。
#     """
#     Multiprocess version of start_generation
#     :param test_num:
#     :param base_name:
#     :param base_dir:
#     :param repair:
#     :param submits:
#     :param total:
#     :return:
#     """
#     progress = '[' + str(submits) + ' / ' + str(total) + ']'  #用于显示当前任务的进度。
#     # Create subdirectories for each test
#     save_dir = os.path.join(base_dir, str(test_num))  #如../result/scope_test%20250102195840%/1%Chart%BankAccount%BankAccount%d1/1
#     if not os.path.exists(save_dir):
#         os.makedirs(save_dir)
#     run_temp_dir = os.path.join(save_dir, "runtemp")  #../result/scope_test%20250116160617%/1%Chart%BankAccount%BankAccount%d1/1/temp
#
#     #steps, rounds = 0, 0
#     steps, rounds = get_step_and_round(save_dir)
#     method_id, project_name, class_name, method_name = parse_file_name(base_name)  #通过 parse_file_name 从 base_name如1%Chart%BankAccount%BankAccount%d1.json 中提取方法 ID、项目名、类名和方法名。
#
#     if method_id  != "461":
#         return
#
#     # 1. Get method data
#     with open(get_dataset_path(method_id, project_name, class_name, method_name, "raw"), "r") as f:
#         raw_data = json.load(f)  #从数据集中读取与当前方法相关的原始数据。
#
#     package = raw_data["package"]
#     imports = raw_data["imports"]
#     package_name = package.replace("package ", "").replace(";", "")
#
# ##################################提取evosuite测试用例
#     evo_dir = os.path.join(project_dir, "extrated_method")
#     os.makedirs(evo_dir, exist_ok=True)
#     evo_path = os.path.join(evo_dir, f"{package_name}_{class_name}_{method_name}.txt")
#     if os.path.exists(evo_path):
#         pass
#     else:
#         input_file = os.path.join(project_dir, "evosuite-tests", package_name.replace('.', os.sep),
#                                   f"{class_name}_ESTest.java")
#         if not os.path.exists(input_file):
#             print(f"Evosuite文件不存在{input_file}")
#             evo = "null"
#         else:
#             evo = extract_tests(method_name, input_file, evo_path)
#     with open(evo_path, 'r') as file:
#         evo = file.read()
#     if evo == None :
#         print("读取测试用例失败！")
#
#
#
# ################^^^^^^^^^^^^^^^^^^^^^^^^^###########
#         # 2. Get data from direction_1 as well as direction_3
#     with open(get_dataset_path(method_id, project_name, class_name, method_name, 1), "r") as f:
#         context_d_1 = json.load(f)
#         context_d_1["evo"] = evo
#
#     with open(get_dataset_path(method_id, project_name, class_name, method_name, 3), "r") as f:
#         context_d_3 = json.load(f)
#         context_d_3["evo"] = evo
#
# ####################################生成代码描述
#     code_description_gpt = project_dir+"code_description/"+package_name+"_"+class_name+"_"+method_name+".json"
#     code_description_path = project_dir+"code_description/"+package_name+"_"+class_name+"_"+method_name+".txt"
#     description_dir = os.path.join(project_dir, "code_description")
#     if not os.path.exists(description_dir):
#         os.makedirs(description_dir)
#     if os.path.isfile(code_description_path):
#         with open(code_description_path, "r", encoding="utf-8") as f:
#             code_description = f.read()
#     else:
#         matched_file = None
#         javafile = {"content": ""}
#         print(f"generating code description for method {method_name}...")
#         target_filename = class_name + ".java"
#         package_path = package_name.replace(".", os.sep)
#         for dirpath, _, filenames in os.walk(project_dir):
#             full_path = os.path.join(dirpath, target_filename)
#             if package_path in os.path.relpath(full_path, project_dir) and os.path.isfile(full_path):
#                 matched_file = full_path
#                 break  # 找到第一个符合要求的文件就停止
#         if matched_file:
#             # 读取并保存文件内容
#             with open(matched_file, "r", encoding="utf-8") as src_file:
#                 javafile["content"] = src_file.read()
#                 javafile["method_name"] = method_name
#                 javafile["class_name"] = class_name
#             messages = generate_messages(TEMPLATE_CODEDESCRIPTION, javafile)
#
#             num = 1
#             dependencies_info = "/n Here is the code information of some methods that may be dependencies of this method(If it is not a dependency of this method, please ignore.):\n"
#             for filename in os.listdir("../dataset/direction_1"):
#                 if filename.endswith('.json'):
#                     # 分割文件名以提取类名和方法名
#                     parts = filename.split('%')
#                     class_name_2 = parts[2]  # 第三部分为类名
#                     method_name_2 = parts[3]  # 第四部分为方法名
#
#                     # 获取上下文信息字符串
#                     info_text = context_d_1['information']
#
#                     # 检查类名和方法名是否都包含在 info_text 中
#                     if class_name_2 == class_name:
#                         continue
#                     if class_name_2 in info_text and method_name_2 in info_text:
#                         with open("../dataset/direction_1/"+filename, "r") as f:
#                             context = json.load(f)
#                             dependencies_info += f"""
#                             Here is the code information for the {num}th relevant method:
#                             {context["information"]}
#                             """
#                             num += 1
#
#             for i in reversed(range(len(messages))):
#                 if messages[i]["role"] == "user":
#                     messages[i]["content"] += dependencies_info
#                     break
#
#             status = ask_chatgpt(messages, code_description_gpt)  # ask_chatgpt成功运行则返回true
#             if not status:
#                 print(progress, Fore.RED + 'OpenAI Fail generating code description', Style.RESET_ALL)
#             else:
#                 with open(code_description_gpt, "r") as f:
#                     gpt_result = json.load(f)  # 打开并读取指定的 GPT 输出文件,gpt_result 是一个字典，通常包含 GPT 的响应内容
#                 code_description = gpt_result["choices"][0]['message']["content"]
#                 with open(code_description_path,"w",encoding="utf-8") as f:
#                     f.write(code_description)
#         else:
#             print("未找到符合条件的 Java 文件")
# ######^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#
#     # 2. Get data from direction_1 as well as direction_3
#     context_d_1["code_description"] = code_description
#     context_d_3["code_description"]= code_description
#
# #####################获取未覆盖行数信息###########################################################
#     uncover_path = project_dir + "uncovered/" + package_name + "_" + class_name + "_" + method_name+"_uncovered.txt"
#     try:
#         with open(uncover_path, 'r') as file:
#             uncover = file.read()
#     except FileNotFoundError:
#         uncover = "none."
#     context_d_1["uncover"]=uncover
#     context_d_3["uncover"]=uncover
# #######################^^^^^^^^^^^^^^^^^^^########################################################
#
#     def _remove_imports_context(strings):
#         if imports:
#             strings = strings.replace(imports, "")
#         if package:
#             strings = strings.replace(package, "")
#         strings = strings.strip()
#         return strings
#
#     def _remove_signatures_context(strings):
#         db = database()
#         methods = [x[0] for x in db.select(table_name="method",
#                                            conditions={"class_name": class_name,
#                                                        "project_name": project_name},
#                                            result_cols=["signature"])]
#         methods.remove(raw_data["signature"])
#         methods = "\n".join(methods)
#         if methods:
#             strings = strings.replace(methods, "")
#         strings = strings.strip()
#         return strings
#
#     try:
#         MAX_rounds = get_complex_flag(project_dir,int(method_id),max_rounds)
#         while rounds < MAX_rounds:
#             # 1. Ask GPT
#             steps += 1  #首次运行由0变为1
#             rounds += 1  #每轮测试更新 steps 和 rounds。
#             print(progress, method_id, "test_" + str(test_num), "Asking ChatGPT...", "rounds", rounds)
#             gpt_file_name = os.path.join(save_dir, str(steps) + "_GPT_" + str(rounds) + ".json")  #GPT生成内容的保存路径，如../result/scope_test%20250102195840%/1%Chart%BankAccount%BankAccount%d1/1/1_GPT_1.json
#             # Need to generate new messages
#             if rounds != 1:
#                 last_round_result = get_latest_file(save_dir)
#                 with open(last_round_result, "r") as f:
#                     last_round_result = json.load(f)
#                 last_raw = get_latest_file(save_dir, suffix="raw")
#                 with open(last_raw, "r") as f:
#                     last_raw = json.load(f)
#
#                 # Prepare the error message
#                 context = {"class_name": context_d_1["class_name"], "method_name": context_d_1["focal_method"],
#                            "unit_test": last_raw["source_code"], "method_code": context_d_1["information"],"code_description":code_description}
#                 # Required, cannot truncate
#
#                 # Adaptive generate error message
#                 messages = generate_messages(TEMPLATE_ERROR, context)
#                 allow_tokens = remain_prompt_tokens(messages)
#                 if allow_tokens < MIN_ERROR_TOKENS:
#                     context["method_code"] = _remove_imports_context(context["method_code"])
#                     messages = generate_messages(TEMPLATE_ERROR, context)
#                     allow_tokens = remain_prompt_tokens(messages)
#                 if allow_tokens < MIN_ERROR_TOKENS:
#                     context["method_code"] = context_d_3["full_fm"]
#                     messages = generate_messages(TEMPLATE_ERROR, context)
#                     allow_tokens = remain_prompt_tokens(messages)
#                 if allow_tokens < MIN_ERROR_TOKENS:
#                     context["method_code"] = _remove_imports_context(context_d_3["full_fm"])
#                     messages = generate_messages(TEMPLATE_ERROR, context)
#                     allow_tokens = remain_prompt_tokens(messages)
#                 if allow_tokens >= MIN_ERROR_TOKENS:
#                     if "compile_error" in last_round_result:
#                         context["error_type"] = "compiling"
#                         error_mes = process_error_message(last_round_result["compile_error"], allow_tokens)
#                         context["error_message"] = error_mes
#                     if "runtime_error" in last_round_result:
#                         context["error_type"] = "running"
#                         error_mes = process_error_message(last_round_result["runtime_error"], allow_tokens)
#                         context["error_message"] = error_mes
#                 else:
#                     print(progress, Fore.RED + method_id, "Tokens not enough, test fatal error...",
#                           Style.RESET_ALL)  # Fatal error
#                     break
#                 if "compile_error" not in last_round_result and "runtime_error" not in last_round_result:
#                     print(progress, Fore.RED + method_id, "Timeout error, test fatal error...", Style.RESET_ALL)
#                     break
#                 messages = generate_messages(TEMPLATE_ERROR, context)
#                 # print('-------------------')
#                 # print(context["error_message"])
#             else:  # 第一轮：
#                 if not context_d_3["c_deps"] and not context_d_3["m_deps"]:  # No dependencies d_1。如果两者都为空，说明没有依赖，可以直接使用 context_d_1 生成消息
#                     context = copy.deepcopy(context_d_1)  #复制上下文：避免修改原始数据。
#                     messages = generate_messages(TEMPLATE_NO_DEPS, context)     #使用 TEMPLATE_NO_DEPS 模板和 context_d_1 生成测试所需的消息。
#                     if remain_prompt_tokens(messages) < 0:  # 如果生成的消息超出 Token 限制，需要截断信息。
#                         context["information"] = _remove_signatures_context(context["information"])  #去除上下文中其他方法签名
#                         messages = generate_messages(TEMPLATE_NO_DEPS, context)
#                         if remain_prompt_tokens(messages) < 0:  # Failed generating messages
#                             messages = generate_messages(TEMPLATE_NO_DEPS_2, context)
#                             if remain_prompt_tokens(messages) < 0:  # Failed generating messages
#                                 messages = []  # 如果仍然无法生成符合长度限制的消息，直接将 messages 置为空。
#
#                 else:  # Has dependencies 以 context_d_3 为基础生成消息
#                     context = copy.deepcopy(context_d_3)
#                     messages = generate_messages(TEMPLATE_WITH_DEPS, context)   #使用 TEMPLATE_WITH_DEPS 模板，适用于包含依赖的上下文
#                     if remain_prompt_tokens(messages) < 0:  # Need Truncate information
#                         context["full_fm"] = _remove_imports_context(context["full_fm"])
#                         messages = generate_messages(TEMPLATE_WITH_DEPS, context)
#                         if remain_prompt_tokens(messages) < 0:  # Failed generating messages
#                             messages = generate_messages(TEMPLATE_WITH_DEPS_2, context)
#                             if remain_prompt_tokens(messages) < 0:  # Failed generating messages
#                                 messages = generate_messages(TEMPLATE_WITH_DEPS_3, context)
#                                 if remain_prompt_tokens(messages) < 0:  # Failed generating messages
#                                     messages = []  # 如果仍然无法生成符合长度限制的消息，直接将 messages 置为空。
#
#                 if not messages:  # Turn to minimum messages
#                     context = copy.deepcopy(context_d_1)  # use direction 1 as template
#                     context["information"] = context_d_3["full_fm"]  # use full_fm d_3 as context使用 context_d_1 的模板，但将 context_d_3["full_fm"] 作为 information。
#                     messages = generate_messages(TEMPLATE_NO_DEPS, context)
#                     if remain_prompt_tokens(messages) < 0:
#                         context["information"] = _remove_imports_context(context["information"])
#                         messages = generate_messages(TEMPLATE_NO_DEPS, context)  # !! MINIMUM MESSAGES!!
#                         if remain_prompt_tokens(messages) < 0:  # Failed generating messages
#                             print(progress, Fore.RED + "Tokens not enough, test fatal error...", Style.RESET_ALL)  #如果经过所有努力仍无法生成有效消息，则打印错误信息并中止。
#                             break
#                 # print(Fore.BLUE, messages[1]['content'], Style.RESET_ALL)
#
#             status = ask_chatgpt(messages, gpt_file_name)  #ask_chatgpt成功运行则返回true
#             if not status:
#                 print(progress, Fore.RED + 'OpenAI Fail processing messages', Style.RESET_ALL)
#                 break
#
#
#             with open(gpt_file_name, "r") as f:
#                 gpt_result = json.load(f)  #打开并读取指定的 GPT 输出文件,gpt_result 是一个字典，通常包含 GPT 的响应内容
#
#             # 2. Extract information from GPT, and RUN save the result
#             steps += 1
#
#             raw_file_name = os.path.join(save_dir, str(steps) + "_raw_" + str(rounds) + ".json")
#
#             # extract the test and save the result in raw_file_name
#             input_string = gpt_result["choices"][0]['message']["content"]  #input_string 是 GPT 返回的代码内容。
#
#             ##############新内容，修复生成的测试用例
#
#             if rounds == 1:
#                 has_code, extracted_code, has_syntactic_error = extract_code(input_string)  # extract_code 函数解析 input_string，提取代码并返回以下值：has_code: 是否成功提取到代码。extracted_code: 提取的代码内容。has_syntactic_error: 是否存在语法错误。
#                 if not has_code:
#                     print(progress,"generation error!\n")
#                     break
#                 print(progress,"start enhancement...")
#                 first_gptfile = os.path.join(save_dir, "1_GPT_" + str(rounds) + ".txt")
#                 with open(first_gptfile,"w",encoding= "utf-8") as f:
#                     f.write(extracted_code)
#                 os.remove(gpt_file_name)
#                 context['loaded_data'] = extracted_code
#                 if not context_d_3["c_deps"] and not context_d_3["m_deps"]:  # 如果没有依赖
#                     context = copy.deepcopy(context_d_1)  # 复制上下文：避免修改原始数据。
#                     messages = generate_messages(TEMPLATE_ENHANCE_NO_DEPS, context)
#
#                 else:
#                     context = copy.deepcopy(context_d_3)  # 复制上下文：避免修改原始数据。
#                     messages = generate_messages(TEMPLATE_ENHANCE_DEPS, context)
#
#                 status = ask_chatgpt(messages, gpt_file_name)  # ask_chatgpt成功运行则返回true
#                 if not status:
#                     print(progress, Fore.RED + 'OpenAI Fail processing messages', Style.RESET_ALL)
#                     break
#                 print(progress,"test case enhancement succeed!")
#
#                 with open(gpt_file_name, "r") as f:
#                     gpt_result = json.load(f)  # 打开并读取指定的 GPT 输出文件,gpt_result 是一个字典，通常包含 GPT 的响应内容
#
#                 # extract the test and save the result in raw_file_name
#                 input_string = gpt_result["choices"][0]['message']["content"]  # input_string 是 GPT 返回的代码内容。
#             #####################^^^^^^^^^^^^^^^^^^^^^^^
#
#             test_passed, fatal_error = extract_and_run(input_string, raw_file_name, class_name, method_id, test_num,
#                                                        project_name,
#                                                        package)  #test_passed：代码是否通过测试。fatal_error：运行过程中是否发生了致命错误。
#
#             if test_passed:
#                 print(progress, Fore.GREEN + method_id, "test_" + str(test_num), "steps", steps, "rounds", rounds,
#                       "test passed",
#                       Style.RESET_ALL)
#                 break
#
#             if not os.path.exists(raw_file_name):
#                 print(progress, Fore.RED + method_id, "test_" + str(test_num), "steps", steps, "rounds", rounds,
#                       "no code in raw result", Style.RESET_ALL)
#                 break
#
#             # Open up the raw result
#             with open(get_latest_file(save_dir), "r") as f:
#                 raw_result = json.load(f)  #调用 get_latest_file 获取最新生成的结果文件路径并加载内容。raw_result 包含运行后的源代码信息（如 source_code 字段）。
#
#
#             # 4. Start imports Repair
#             steps += 1
#             # print(progress, method_id, "test_" + str(test_num), "Fixing imports", "rounds", rounds)
#             imports_file_name = os.path.join(save_dir, str(steps) + "_imports_" + str(rounds) + ".json")
#             # run imports repair
#             source_code = raw_result["source_code"]
#             source_code = repair_imports(source_code, imports)
#             test_passed, fatal_error = extract_and_run(source_code, imports_file_name, class_name, method_id, test_num,
#                                                        project_name,
#                                                        package)
#             if test_passed:
#                 print(progress, Fore.GREEN + method_id, "test_" + str(test_num), "steps", steps, "rounds", rounds,
#                       "test passed",
#                       Style.RESET_ALL)
#                 break
#             if fatal_error:
#                 print(progress, Fore.RED + method_id, "test_" + str(test_num), "steps", steps, "rounds", rounds,
#                       "fatal error",
#                       Style.RESET_ALL)
#                 break
#
#             print(progress, Fore.YELLOW + method_id, "test_" + str(test_num), "Test failed, fixing...", "rounds",
#                   rounds,
#                   Style.RESET_ALL)
#             if not repair:  # If we do not want to repair the code, we don't need to second round
#                 break
#     except Exception as e:
#         print(progress, Fore.RED + str(e), Style.RESET_ALL)
#     # if os.path.exists(run_temp_dir):
#     #     run_temp_dir = os.path.abspath(run_temp_dir)
#     #     shutil.rmtree(run_temp_dir)  #删除临时运行目录 run_temp_dir，释放磁盘空间。
def whole_process(test_num, base_name, base_dir, repair, submits, total):  #测试和修复流程，用于对某个方法执行多轮的测试和修复操作。
    """
    Multiprocess version of start_generation
    :param test_num:
    :param base_name:
    :param base_dir:
    :param repair:
    :param submits:
    :param total:
    :return:
    """
    progress = '[' + str(submits) + ' / ' + str(total) + ']'  #用于显示当前任务的进度。
    # Create subdirectories for each test
    save_dir = os.path.join(base_dir, str(test_num))  #如../result/scope_test%20250102195840%/1%Chart%BankAccount%BankAccount%d1/1
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    run_temp_dir = os.path.join(save_dir, "runtemp")  #../result/scope_test%20250116160617%/1%Chart%BankAccount%BankAccount%d1/1/temp

    #steps, rounds = 0, 0
    steps, rounds = get_step_and_round(save_dir)
    method_id, project_name, class_name, method_name = parse_file_name(base_name)  #通过 parse_file_name 从 base_name如1%Chart%BankAccount%BankAccount%d1.json 中提取方法 ID、项目名、类名和方法名。

    if method_id != "443":

        return


    if os.path.exists(f"{save_dir}/temp/coverage.xml"):
        print("skip\n")
        return


    # 1. Get method data
    with open(get_dataset_path(method_id, project_name, class_name, method_name, "raw"), "r") as f:
        raw_data = json.load(f)  #从数据集中读取与当前方法相关的原始数据。

    package = raw_data["package"]
    imports = raw_data["imports"]
    package_name = package.replace("package ", "").replace(";", "")

##################################提取evosuite测试用例
    evo_dir = os.path.join(project_dir, "extrated_method")
    os.makedirs(evo_dir, exist_ok=True)
    evo_path = os.path.join(evo_dir, f"{package_name}_{class_name}_{method_name}.txt")
    if os.path.exists(evo_path):
        with open(evo_path, 'r') as file:
            evo = file.read()
    else:
        input_file = os.path.join(project_dir, "evosuite-tests", package_name.replace('.', os.sep),
                                  f"{class_name}_ESTest.java")
        if not os.path.exists(input_file):
            print(f"Evosuite文件不存在{input_file}")
            evo = "No test cases have been generated yet. You need to create a new one, covering all branch paths as much as possible and following the same rules."
            with open(evo_path, 'w') as file:
                file.write(evo)
        else:
            evo = extract_tests(method_name, input_file, evo_path)
    with open(evo_path, 'r') as file:
        evo = file.read()
    if evo == None :
        print("读取测试用例失败！")

################^^^^^^^^^^^^^^^^^^^^^^^^^###########result/scope_test%20250927130706%
        # 2. Get data from direction_1 as well as direction_3
    with open(get_dataset_path(method_id, project_name, class_name, method_name, 1), "r") as f:
        context_d_1 = json.load(f)
        context_d_1["evo"] = evo

    with open(get_dataset_path(method_id, project_name, class_name, method_name, 3), "r") as f:
        context_d_3 = json.load(f)
        context_d_3["evo"] = evo



####################################生成代码描述
    code_description_gpt = project_dir+"code_description/"+method_id+"_"+package_name+"_"+class_name+"_"+method_name+".json"
    code_description_path = project_dir+"code_description/"+method_id+"_"+package_name+"_"+class_name+"_"+method_name+".txt"
    description_dir = os.path.join(project_dir, "code_description")
    if not os.path.exists(description_dir):
        os.makedirs(description_dir)
    if os.path.isfile(code_description_path):
        with open(code_description_path, "r", encoding="utf-8") as f:
            code_description = f.read()
    else:
        matched_file = None
        javafile = {"content": ""}
        print(f"generating code description for method {method_name}...")
        target_filename = class_name + ".java"
        package_path = package_name.replace(".", os.sep)
        for dirpath, _, filenames in os.walk(project_dir):
            full_path = os.path.join(dirpath, target_filename)
            if package_path in os.path.relpath(full_path, project_dir) and os.path.isfile(full_path):
                matched_file = full_path
                break  # 找到第一个符合要求的文件就停止
        if matched_file:
            # 读取并保存文件内容
            with open(matched_file, "r", encoding="utf-8") as src_file:
                javafile["content"] = src_file.read()
                javafile["method_name"] = method_name
                javafile["class_name"] = class_name
                javafile["full_fm"] = context_d_3["full_fm"]
            messages = generate_messages(TEMPLATE_CODEDESCRIPTION, javafile)
            #print(messages)

            num = 1
            dependencies_info = "/n Here is the code information of some methods that may be dependencies of this method(If it is not a dependency of this method, please ignore.):\n"
            for filename in os.listdir("../dataset/direction_3"):
                if filename.endswith('.json'):
                    # 分割文件名以提取类名和方法名
                    parts = filename.split('%')
                    class_name_2 = parts[2]  # 第三部分为类名
                    method_name_2 = parts[3]  # 第四部分为方法名

                    # 获取上下文信息字符串
                    info_text = context_d_3['full_fm']

                    # 检查类名和方法名是否都包含在 info_text 中
                    if class_name_2 == class_name:
                        continue
                    pattern_class = r'\b{}\b'.format(re.escape(class_name_2))
                    pattern_method = r'\b{}\b'.format(re.escape(method_name_2))
                    if re.search(pattern_class, info_text) and re.search(pattern_method, info_text):
                        with open("../dataset/direction_3/"+filename, "r") as f:
                            context = json.load(f)
                            dependencies_info += f"""
                            Here is the code information for the {num}th relevant method, including the fields in the class where it resides:
                            {context["full_fm"]}
                            """
                            num += 1

            for i in reversed(range(len(messages))):
                if messages[i]["role"] == "user":
                    messages[i]["content"] += dependencies_info
                    break

            status = ask_chatgpt(messages, code_description_gpt)  # ask_chatgpt成功运行则返回true
            if not status:
                print(progress, Fore.RED + 'OpenAI Fail generating code description', Style.RESET_ALL)
            else:
                with open(code_description_gpt, "r") as f:
                    gpt_result = json.load(f)  # 打开并读取指定的 GPT 输出文件,gpt_result 是一个字典，通常包含 GPT 的响应内容
                code_description = gpt_result["choices"][0]['message']["content"]
                with open(code_description_path,"w",encoding="utf-8") as f:
                    f.write(code_description)
        else:
            print("未找到符合条件的 Java 文件")
######^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

    # 2. Get data from direction_1 as well as direction_3
    context_d_1["code_description"] = code_description
    context_d_3["code_description"]= code_description

#####################获取未覆盖行数信息###########################################################
    uncover_path = project_dir + "uncovered/" + package_name + "_" + class_name + "_uncovered.txt"
    if "No test cases have been generated yet. " in evo :
        valid_uncover = "none."
    else:

        with open(uncover_path, 'r') as file:
            uncover = file.read()
        uncover_lines = [line.strip() for line in uncover.splitlines()]
        # 2. 初始化有效信息列表
        valid_lines = []
        # 3. 遍历每一行，筛选包含在context_d_3["full_fm"]中的行
        full_fm = context_d_3.get("full_fm", "")
        # 遍历每行进行筛选
        for line in uncover_lines:
            if not line:
                continue
            if line in full_fm:
                valid_lines.append(line)
        # 4. 可选：将有效行拼接回字符串（如果需要保留原换行格式）
        valid_uncover = "\n".join(valid_lines)
        if not valid_uncover:  # 空字符串在布尔判断中为False
            valid_uncover = "none."

    context_d_1["uncover"]=valid_uncover
    context_d_3["uncover"]=valid_uncover
#######################^^^^^^^^^^^^^^^^^^^########################################################

    def _remove_imports_context(strings):
        if imports:
            strings = strings.replace(imports, "")
        if package:
            strings = strings.replace(package, "")
        strings = strings.strip()
        return strings

    def _remove_signatures_context(strings):
        db = database()
        methods = [x[0] for x in db.select(table_name="method",
                                           conditions={"class_name": class_name,
                                                       "project_name": project_name},
                                           result_cols=["signature"])]
        methods.remove(raw_data["signature"])
        methods = "\n".join(methods)
        if methods:
            strings = strings.replace(methods, "")
        strings = strings.strip()
        return strings

    print("经过了这里")
    MAX_rounds = get_complex_flag(project_dir, int(method_id), max_rounds)
    while rounds < MAX_rounds:
        # 1. Ask GPT
        steps += 1  # 首次运行由0变为1
        rounds += 1  # 每轮测试更新 steps 和 rounds。
        print(progress, method_id, "test_" + str(test_num), "Asking ChatGPT...", "rounds", rounds)
        gpt_file_name = os.path.join(save_dir, str(steps) + "_GPT_" + str(
            rounds) + ".json")  # GPT生成内容的保存路径，如../result/scope_test%20250102195840%/1%Chart%BankAccount%BankAccount%d1/1/1_GPT_1.json
        # Need to generate new messages
        if rounds != 1:
            last_round_result = get_latest_file(save_dir)
            with open(last_round_result, "r") as f:
                last_round_result = json.load(f)
            last_raw = get_latest_file(save_dir, suffix="raw")
            with open(last_raw, "r") as f:
                last_raw = json.load(f)

            # Prepare the error message
            context = {"class_name": context_d_1["class_name"], "method_name": context_d_1["focal_method"],
                       "unit_test": last_raw["source_code"], "method_code": context_d_3["full_fm"],
                       "code_description": code_description}
            # Required, cannot truncate

            # Adaptive generate error message
            messages = generate_messages(TEMPLATE_ERROR, context)
            allow_tokens = remain_prompt_tokens(messages)
            if allow_tokens < MIN_ERROR_TOKENS:
                context["method_code"] = _remove_imports_context(context["method_code"])
                messages = generate_messages(TEMPLATE_ERROR, context)
                allow_tokens = remain_prompt_tokens(messages)
            if allow_tokens < MIN_ERROR_TOKENS:
                context["method_code"] = context_d_3["full_fm"]
                messages = generate_messages(TEMPLATE_ERROR, context)
                allow_tokens = remain_prompt_tokens(messages)
            if allow_tokens < MIN_ERROR_TOKENS:
                context["method_code"] = _remove_imports_context(context_d_3["full_fm"])
                messages = generate_messages(TEMPLATE_ERROR, context)
                allow_tokens = remain_prompt_tokens(messages)
            if allow_tokens >= MIN_ERROR_TOKENS:
                if "compile_error" in last_round_result:
                    context["error_type"] = "compiling"
                    error_mes = process_error_message(last_round_result["compile_error"], allow_tokens)
                    context["error_message"] = error_mes
                if "runtime_error" in last_round_result:
                    context["error_type"] = "running"
                    error_mes = process_error_message(last_round_result["runtime_error"], allow_tokens)
                    context["error_message"] = error_mes
            else:
                print(progress, Fore.RED + method_id, "Tokens not enough, test fatal error...",
                      Style.RESET_ALL)  # Fatal error
                break
            if "compile_error" not in last_round_result and "runtime_error" not in last_round_result:
                context["error_type"] = "Timeout error"
                context["error_message"] = "Timeout error"
                context["error_message"] = "None."
                # print(progress, Fore.RED + method_id, "Timeout error, test fatal error...", Style.RESET_ALL)
                # break

            ####################生成错误知识库
            error_base_name = os.path.join(save_dir, "error_base_" + str(rounds) + ".json")
            last_error_base_name = os.path.join(save_dir, "error_base_" + str(rounds-1) + ".txt")
            if os.path.exists(last_error_base_name):
                with open(last_error_base_name, 'r', encoding='utf-8') as f:
                    context["error_knowledge_base"] = f.read()
            else:
                context["error_knowledge_base"] = None

            messages = generate_messages(TEMPLATE_ERRORDESCRIPTION, context)
            status = ask_chatgpt(messages, error_base_name)  # ask_chatgpt成功运行则返回true
            if not status:
                print(progress, Fore.RED + 'OpenAI Fail processing messages', Style.RESET_ALL)
                break

            with open(error_base_name, "r") as f:
                gpt_result = json.load(f)  # 打开并读取指定的 GPT 输出文件,gpt_result 是一个字典，通常包含 GPT 的响应内容
            error_base = gpt_result["choices"][0]['message']["content"]
            if os.path.exists(error_base_name):
                os.remove(error_base_name) #删除json文件
            txt_file_name = error_base_name.replace(".json", ".txt")
            with open(txt_file_name, "w", encoding="utf-8") as txt_f:
                txt_f.write(error_base)
            context["error_knowledge_base"] = error_base

            #############^^^^^^^^^^^^^^^^^^^^
            messages = generate_messages(TEMPLATE_ERROR, context)
        else:  # 第一轮：
            # if not context_d_3["c_deps"] and not context_d_3[
            #     "m_deps"]:  # No dependencies d_1。如果两者都为空，说明没有依赖，可以直接使用 context_d_1 生成消息
            #     context = copy.deepcopy(context_d_1)  # 复制上下文：避免修改原始数据。
            #     messages = generate_messages(TEMPLATE_NO_DEPS,
            #                                  context)  # 使用 TEMPLATE_NO_DEPS 模板和 context_d_1 生成测试所需的消息。
            #     if remain_prompt_tokens(messages) < 0:  # 如果生成的消息超出 Token 限制，需要截断信息。
            #         context["information"] = _remove_signatures_context(context["information"])  # 去除上下文中其他方法签名
            #         messages = generate_messages(TEMPLATE_NO_DEPS, context)
            #         if remain_prompt_tokens(messages) < 0:  # Failed generating messages
            #             messages = generate_messages(TEMPLATE_NO_DEPS_2, context)
            #             if remain_prompt_tokens(messages) < 0:  # Failed generating messages
            #                 messages = []  # 如果仍然无法生成符合长度限制的消息，直接将 messages 置为空。

            # else:  # Has dependencies 以 context_d_3 为基础生成消息
            context = copy.deepcopy(context_d_3)
            messages = generate_messages(TEMPLATE_WITH_DEPS, context)  # 使用 TEMPLATE_WITH_DEPS 模板，适用于包含依赖的上下文
            if remain_prompt_tokens(messages) < 0:  # Need Truncate information
                context["full_fm"] = _remove_imports_context(context["full_fm"])
                messages = generate_messages(TEMPLATE_WITH_DEPS, context)
                if remain_prompt_tokens(messages) < 0:  # Failed generating messages
                    messages = generate_messages(TEMPLATE_WITH_DEPS_2, context)
                    if remain_prompt_tokens(messages) < 0:  # Failed generating messages
                        messages = generate_messages(TEMPLATE_WITH_DEPS_3, context)
                        if remain_prompt_tokens(messages) < 0:  # Failed generating messages
                            messages = []  # 如果仍然无法生成符合长度限制的消息，直接将 messages 置为空。

            if not messages:  # Turn to minimum messages
                context = copy.deepcopy(context_d_1)  # use direction 1 as template
                context["information"] = context_d_3[
                    "full_fm"]  # use full_fm d_3 as context使用 context_d_1 的模板，但将 context_d_3["full_fm"] 作为 information。
                messages = generate_messages(TEMPLATE_NO_DEPS, context)
                if remain_prompt_tokens(messages) < 0:
                    context["information"] = _remove_imports_context(context["information"])
                    messages = generate_messages(TEMPLATE_NO_DEPS, context)  # !! MINIMUM MESSAGES!!
                    if remain_prompt_tokens(messages) < 0:  # Failed generating messages
                        print(progress, Fore.RED + "Tokens not enough, test fatal error...",
                              Style.RESET_ALL)  # 如果经过所有努力仍无法生成有效消息，则打印错误信息并中止。
                        break
            # print(Fore.BLUE, messages[1]['content'], Style.RESET_ALL)

        status = ask_chatgpt(messages, gpt_file_name)  # ask_chatgpt成功运行则返回true
        if not status:
            print(progress, Fore.RED + 'OpenAI Fail processing messages', Style.RESET_ALL)
            break

        with open(gpt_file_name, "r") as f:
            gpt_result = json.load(f)  # 打开并读取指定的 GPT 输出文件,gpt_result 是一个字典，通常包含 GPT 的响应内容

        # 2. Extract information from GPT, and RUN save the result
        steps += 1

        raw_file_name = os.path.join(save_dir, str(steps) + "_raw_" + str(rounds) + ".json")

        # extract the test and save the result in raw_file_name
        input_string = gpt_result["choices"][0]['message']["content"]  # input_string 是 GPT 返回的代码内容。

        ##############新内容，增强生成的测试用例

        if rounds == 1:
            has_code, extracted_code, has_syntactic_error = extract_code(
                input_string)  # extract_code 函数解析 input_string，提取代码并返回以下值：has_code: 是否成功提取到代码。extracted_code: 提取的代码内容。has_syntactic_error: 是否存在语法错误。
            if not has_code:
                print(progress, "generation error!\n")
                break
            print(progress, "start enhancement...")
            first_gptfile = os.path.join(save_dir, "1_GPT_" + str(rounds) + ".txt")
            with open(first_gptfile, "w", encoding="utf-8") as f:
                f.write(extracted_code)
            os.remove(gpt_file_name)
            # if not context_d_3["c_deps"] and not context_d_3["m_deps"]:  # 如果没有依赖
            #     context = copy.deepcopy(context_d_1)  # 复制上下文：避免修改原始数据。
            #     messages = generate_messages(TEMPLATE_ENHANCE_NO_DEPS, context)
            #
            # else:
            context = copy.deepcopy(context_d_3)  # 复制上下文：避免修改原始数据。
            context['loaded_data'] = extracted_code
            messages = generate_messages(TEMPLATE_ENHANCE_DEPS, context)

            status = ask_chatgpt(messages, gpt_file_name)  # ask_chatgpt成功运行则返回true
            if not status:
                print(progress, Fore.RED + 'OpenAI Fail processing messages', Style.RESET_ALL)
                break
            print(progress, "test case enhancement succeed!")

            with open(gpt_file_name, "r") as f:
                gpt_result = json.load(f)  # 打开并读取指定的 GPT 输出文件,gpt_result 是一个字典，通常包含 GPT 的响应内容

            # extract the test and save the result in raw_file_name
            input_string = gpt_result["choices"][0]['message']["content"]  # input_string 是 GPT 返回的代码内容。
        #####################^^^^^^^^^^^^^^^^^^^^^^^

        test_passed, fatal_error = extract_and_run(input_string, raw_file_name, class_name, method_id, test_num,
                                                   project_name,
                                                   package)  # test_passed：代码是否通过测试。fatal_error：运行过程中是否发生了致命错误。

        if test_passed:
            print(progress, Fore.GREEN + method_id, "test_" + str(test_num), "steps", steps, "rounds", rounds,
                  "test passed",
                  Style.RESET_ALL)
            break

        if not os.path.exists(raw_file_name):
            print(progress, Fore.RED + method_id, "test_" + str(test_num), "steps", steps, "rounds", rounds,
                  "no code in raw result", Style.RESET_ALL)
            break

        # Open up the raw result
        with open(get_latest_file(save_dir), "r") as f:
            raw_result = json.load(f)  # 调用 get_latest_file 获取最新生成的结果文件路径并加载内容。raw_result 包含运行后的源代码信息（如 source_code 字段）。

        # 4. Start imports Repair
        steps += 1
        # print(progress, method_id, "test_" + str(test_num), "Fixing imports", "rounds", rounds)
        imports_file_name = os.path.join(save_dir, str(steps) + "_imports_" + str(rounds) + ".json")
        # run imports repair
        source_code = raw_result["source_code"]
        source_code = repair_imports(source_code, imports)
        test_passed, fatal_error = extract_and_run(source_code, imports_file_name, class_name, method_id, test_num,
                                                   project_name,
                                                   package)
        if test_passed:
            print(progress, Fore.GREEN + method_id, "test_" + str(test_num), "steps", steps, "rounds", rounds,
                  "test passed",
                  Style.RESET_ALL)
            break
        if fatal_error:
            print(progress, Fore.RED + method_id, "test_" + str(test_num), "steps", steps, "rounds", rounds,
                  "fatal error",
                  Style.RESET_ALL)
            break

        print(progress, Fore.YELLOW + method_id, "test_" + str(test_num), "Test failed, fixing...", "rounds",
              rounds,
              Style.RESET_ALL)
        if not repair:  # If we do not want to repair the code, we don't need to second round
            break
    # if os.path.exists(run_temp_dir):
    #     run_temp_dir = os.path.abspath(run_temp_dir)
    #     shutil.rmtree(run_temp_dir)  #删除临时运行目录 run_temp_dir，释放磁盘空间。

def generate_complex_txt(project_dir):
    """
    第一个方法：
    1. 读取指定目录下所有JSON文件，提取ID和information字段行数
    2. 按行数排序后计算前30%阈值，生成1/0标记
    3. 在project_dir下生成complex.txt文件

    Args:
        project_dir: 生成complex.txt的目标目录（直接使用该变量名）
    """
    complex_file_path = os.path.join(project_dir, "complex.txt")
    if os.path.exists(complex_file_path):
        print(f"提示：{complex_file_path} 已生成")
        return
    # 定义数据源目录
    data_dir = "../dataset/direction_1"
    # 存储ID和对应information行数的字典 {ID: 行数}
    id_line_count: Dict[int, int] = {}

    # ========== 步骤1：遍历JSON文件，提取ID和information行数 ==========
    if not os.path.isdir(data_dir):
        raise FileNotFoundError(f"数据源目录不存在: {data_dir}")

    # 遍历目录下所有文件
    for filename in os.listdir(data_dir):
        # 仅处理JSON文件
        if not filename.endswith(".json"):
            continue

        # 提取文件名中的首个数字（ID）
        try:
            # 分割文件名，提取首个数字（处理如"1%2_a4j%SimilarProducts%getProduct%d1.json"的格式）
            id_str = ""
            for char in filename:
                if char.isdigit():
                    id_str += char
                else:
                    break
            if not id_str:
                print(f"警告：文件{filename}未提取到有效ID，跳过")
                continue
            file_id = int(id_str)
        except (ValueError, IndexError):
            print(f"警告：文件{filename}的ID解析失败，跳过")
            continue

        # 读取JSON文件，提取information字段的行数
        file_path = os.path.join(data_dir, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                # 加载JSON数据
                json_data = json.load(f)
                # 获取information字段（兼容字段不存在/为空的情况）
                information = json_data.get("information", "")
                # 计算行数（按换行符分割，空字符串行数为0）
                line_count = len(information.strip().splitlines()) if information else 0
                id_line_count[file_id] = line_count
        except (json.JSONDecodeError, IOError) as e:
            print(f"警告：文件{file_path}读取/解析失败: {e}，跳过")
            continue

    # 处理无有效文件的情况
    if not id_line_count:
        print("警告：未找到有效JSON文件，生成空的complex.txt")
        with open(complex_file_path, "w", encoding="utf-8") as f:
            pass
        return

    # ========== 步骤2：按行数排序，计算前30%阈值 ==========
    # 将{ID:行数}转换为列表并按行数降序排序
    sorted_items: List[Tuple[int, int]] = sorted(
        id_line_count.items(),
        key=lambda x: x[1],
        reverse=True  # 行数从高到低排序
    )

    # 计算前30%的数量（向上取整，避免0的情况）
    total_count = len(sorted_items)
    top_30_percent_count = math.ceil(total_count * 0.3)

    # ========== 步骤3：生成1/0标记并写入complex.txt ==========
    # 创建project_dir目录（如果不存在）
    complex_file_path = os.path.join(project_dir, "complex.txt")

    with open(complex_file_path, "w", encoding="utf-8") as f:
        for idx, (file_id, line_count) in enumerate(sorted_items):
            # 前30%标记为1，其余为0
            flag = 1 if idx < top_30_percent_count else 0
            # 写入格式：ID 标记（每行两个数字）
            f.write(f"{file_id} {flag}\n")

    print(f"成功生成complex.txt，路径：{complex_file_path}")
    print(f"总计处理{total_count}个ID，前{top_30_percent_count}个标记为1，其余标记为0")

def start_whole_process(source_dir, result_path, multiprocess=False, repair=True):
    """
    Start repair process
    :param repair:  Whether to repair the code
    :param multiprocess: Whether to use multiprocess
    :param source_dir: The directory of the dataset or scoped dataset.
    :return:
    """
    # Get a list of all file paths
    multiprocess = True
    file_paths = []
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith(".json"):
                file_paths.append(os.path.join(root, file))  #使用 os.walk 遍历 direction_1 及其子目录，寻找所有以 .json 结尾的文件。将符合条件的文件路径添加到列表 file_paths 中，作为待处理的目标文件。

    generate_complex_txt(project_dir)

    submits = 0  #当前已提交任务数
    total = len(file_paths) * test_number  #任务总数，等于文件数量乘以每个文件需要的测试次数
    if multiprocess:
        print("Multi process executing!")
        # Create a process pool with maximum of process_number
        with concurrent.futures.ProcessPoolExecutor(max_workers=process_number) as executor:  #创建一个进程池，最大工作进程数为 process_number。
            for idx, file_path in enumerate(file_paths):
                _, base_name = os.path.split(file_path.replace("/dataset/", "/result/"))  #base_name：文件名（替换路径前缀 /dataset/ 为 /result/）。如1%Chart%BankAccount%BankAccount%d1.json
                base_dir = os.path.join(result_path, base_name.split(".json")[0])  #如../result/scope_test%20250116160617%/1%Chart%BankAccount%BankAccount%d1
                for test_num in range(1, test_number + 1):
                    submits += 1
                    executor.submit(whole_process, test_num, base_name, base_dir, repair, submits, total)  #每个文件被测试 test_number 次，通过 executor.submit 提交 whole_process 任务到进程池中。
        print("Main process executing!")
    else:
        print("Single process executing!")
        for idx, file_path in enumerate(file_paths):
            _, base_name = os.path.split(file_path.replace("/dataset/", "/result/"))  #base_name：文件名（替换路径前缀 /dataset/ 为 /result/）。如1%Chart%BankAccount%BankAccount%d1.json
            base_dir = os.path.join(result_path, base_name.split(".json")[0])  #如../result/scope_test%20250116160617%/1%Chart%BankAccount%BankAccount%d1
            for test_num in range(1, test_number + 1):
                submits += 1
                whole_process(test_num, base_name, base_dir, repair, submits, total)
