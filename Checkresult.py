import os
import re
import json
from pathlib import Path


def process_json_files(folder_path):
    """处理指定文件夹中的JSON文件，提取数据并保存为文本文件"""
    # 确保文件夹路径存在
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        print(f"错误：文件夹 {folder_path} 不存在或不是一个有效文件夹")
        return

    # 定义文件名匹配模式：如3_imports_1.json、6_imports_2.json等
    file_pattern = re.compile(r'^(\d+)_imports_(\d+)\.json$')

    # 遍历文件夹中的所有文件
    for file_path in folder.glob('*.json'):
        file_name = file_path.name
        match = file_pattern.match(file_name)

        if match:
            # 提取文件名中的数字部分
            prefix, suffix = match.groups()
            print(f"处理文件: {file_name}")

            try:
                # 读取JSON文件内容
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 提取所需字段
                source_code = data.get('source_code', '')
                compile_error = data.get('compile_error', '')
                runtime_error = data.get('runtime_error', '')

                # 保存source_code到source_code_{suffix}.txt
                if source_code:
                    save_to_file(source_code, f"source_code_{suffix}.txt", folder_path)


                # 保存compile_error到compile_error_{suffix}.txt
                if compile_error:
                    save_to_file(compile_error, f"compile_error_{suffix}.txt", folder_path)

                # 保存runtime_error到runtime_error_{suffix}.txt
                if runtime_error:
                    save_to_file(runtime_error, f"runtime_error_{suffix}.txt", folder_path)

                print(f"成功处理文件 {file_name}，已保存数据")

            except json.JSONDecodeError:
                print(f"错误：文件 {file_name} 不是有效的JSON格式")
            except Exception as e:
                print(f"处理文件 {file_name} 时发生错误: {str(e)}")
        else:
            print(f"跳过不匹配的文件: {file_name}")


def save_to_file(content, file_name, folder_path):
    """将内容保存到指定的文本文件中"""
    file_path = os.path.join(folder_path, file_name)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)


if __name__ == "__main__":
    # 直接指定要处理的文件夹路径
    folder_path = "1"
    print(f"开始处理文件夹: {folder_path}")
    process_json_files(folder_path)
    print("所有文件处理完成")