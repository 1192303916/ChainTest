import os
import subprocess

#使用Evosuite生成测试用例
def get_class_names_from_directory(directory):
    """
    遍历指定目录，查找所有的 .class 文件并返回完整的类名（包括包名）。
    """
    class_names = []

    # 遍历目录，查找所有的 .class 文件
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".class"):
                package_path = os.path.relpath(root, directory).replace(os.sep, ".")

                class_name = f"{package_path}.{file[:-6]}" if package_path else file[:-6]

                # 打印调试信息
                print(f"Found class: {class_name}")

                class_names.append(class_name)

    return class_names


def generate_test_case():
    evosuite_jar_path = "evosuite-1.2.0.jar" 
    project_dir = "C:/Users/11923/Desktop/dataset2/binance-connector-java-master/clients/common"  # 指向 target/classes 目录
    target_dir = os.path.join(project_dir, "target", "classes")  # 指向包含编译后的类文件的目录
    # lib_dir = os.path.join(project_dir, "lib")


    # 获取所有的类名
    class_names = get_class_names_from_directory(target_dir)

    # 如果没有找到任何类，提示错误并退出
    if not class_names:
        print("No .class files found in the specified directory.")
        return

    # 对每个类生成测试用例
    for target_class in class_names:
        print(f"Generating test case for: {target_class}")
        command = [
            "java",
            #"--illegal-access=permit",
            "-jar", evosuite_jar_path,
            "-class", target_class,
            # "-projectCP", target_dir+";"+lib_dir,
            "-projectCP", target_dir,
            "-Djunit","5",
            "-Dcoverage=true",  # 启用覆盖率收集
            #"-Dsearch_budget", "600",
            #"-Dcriterion","LINE"
        ]

        try:
            # 执行 EvoSuite 命令
            result = subprocess.run(command, cwd=project_dir, check=True, capture_output=True, text=True)
            print(f"Test case generated for {target_class}.")
            print(result.stdout)  # 打印标准输出
        except subprocess.CalledProcessError as e:
            # 捕获并打印错误
            print(f"EvoSuite failed for {target_class} with error:")
            print(f"Return code: {e.returncode}")
            print(f"Stdout: {e.stdout}")  # 打印标准输出
            print(f"Stderr: {e.stderr}")  # 打印标准错误

# 调用函数来生成所有类的测试用例
generate_test_case()

