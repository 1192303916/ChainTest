from bs4 import BeautifulSoup
import os
from html import unescape
import re


def get_uncovered_lines_from_html(filepath, output_base):
    """
    解析单个 HTML 文件，提取未覆盖的代码行，保存到输出目录中，文件名为 包名_类名_uncovered.txt
    """
    with open(filepath, 'r', encoding='utf-8') as file:
        html_content = file.read()

    soup = BeautifulSoup(html_content, 'html.parser')

    # 提取包名
    breadcrumbs_div = soup.find('div', class_='breadCrumbs')
    package_name = 'unknown.package'
    if breadcrumbs_div:
        links = breadcrumbs_div.find_all('a')
        if len(links) >= 2:
            package_name = links[-1].get_text().strip()


    # 提取类名
    h1_tag = soup.find('h1')
    if not h1_tag:
        print(f"未找到类名标签: {filepath}")
        return
    text = h1_tag.get_text()
    start_index = text.find("Class: ") + len("Class: ")
    end_index = text.find(" (")
    class_name = text[start_index:end_index].strip()

    print(f"识别到: 包名={package_name}, 类名={class_name}")

    code_block = soup.find('code', class_='sourceCode')
    if not code_block:
        print(f"未找到代码块: {filepath}")
        return

    lines = code_block.find_all('b')

    # 构造输出路径和文件名（将 . 替换为 _，用于文件名）
    sanitized_package_name = package_name
    output_filename = f"{sanitized_package_name}_{class_name}_uncovered.txt"
    output_path = os.path.join(output_base, output_filename)
    os.makedirs(output_base, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as output_file:
        has_uncovered = False
        for line in lines:
            if 'nc' in line.get('class', []):  # 未覆盖行
                output_file.write(f"{unescape(line.get_text().strip())}\n")
                has_uncovered = True
        if not has_uncovered:
            output_file.write("none.")


def process_all_ns_directories(project_root):
    """
    遍历 htmlReport/ 下所有符合 ns-* 格式的目录（包括ns-1、ns-a、ns-b等），提取所有类的未覆盖代码行
    """
    # 定义匹配 ns-开头 的目录正则（支持字母、数字、下划线）
    ns_dir_pattern = re.compile(r'^ns-[a-zA-Z0-9]+$')

    # 拼接 htmlReport 根路径
    html_report_root = os.path.join(project_root, "htmlReport")
    if not os.path.exists(html_report_root):
        print(f"未找到 htmlReport 目录: {html_report_root}")
        return

    # 遍历 htmlReport 下所有目录，筛选出 ns-* 格式的目录
    ns_dirs = []
    for dir_name in os.listdir(html_report_root):
        dir_path = os.path.join(html_report_root, dir_name)
        if os.path.isdir(dir_path) and ns_dir_pattern.match(dir_name):
            ns_dirs.append(dir_path)

    if not ns_dirs:
        print("未找到任何 ns-* 格式的目录")
        return

    # 处理每个符合条件的 ns-* 目录
    for ns_dir in ns_dirs:
        sources_dir = os.path.join(ns_dir, "sources")
        if not os.path.exists(sources_dir):
            print(f"跳过无 sources 子目录的 ns 目录: {ns_dir}")
            continue

        print(f"\n处理目录: {sources_dir}")
        for root, _, files in os.walk(sources_dir):
            for file in files:
                if file.endswith(".html"):
                    full_path = os.path.join(root, file)
                    output_subdir = os.path.join(project_root, "uncovered")
                    get_uncovered_lines_from_html(full_path, output_subdir)


# 替换为你的项目根路径
java_project_root = "C:/Users/11923/Desktop/dataset2/binance-connector-java-master/common"
process_all_ns_directories(java_project_root)