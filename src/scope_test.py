"""
This file is for starting a scope test for selected methods.
It will automatically create a new folder inside dataset as well as result folder.
The folder format is "scope_test_YYYYMMDDHHMMSS_Direction".
The dataset folder will contain all the information in the direction.
"""
from tools import *
from askGPT import start_whole_process
from database import database
from task import Task
from colorama import Fore, Style, init

init()
db = database()


def create_dataset_result_folder(direction):
    """
    Create a new folder for this scope test.
    :param direction: The direction of this scope test.
    :return: The path of the new folder.
    """
    # Get current time
    now = datetime.datetime.now()
    # format the time as a string
    time_str = now.strftime("%Y%m%d%H%M%S")
    #result_path = os.path.join(result_dir, "scope_test%" + time_str + "%" + direction)  #如../result/scope_test%20250116160617%
    result_path = os.path.join(result_dir, "scope_test%20250927130706%")
    if not os.path.exists(result_path):
        os.makedirs(result_path)
    # else:
    #     raise Exception("Result folder already exists.")
    return result_path


def create_new_folder(folder_path: str):
    """
    Create a new folder.
    :param folder_path: The folder path.
    :return: None
    """
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    else:
        raise Exception("Folder already exists.")


def find_all_files(folder_path: str, method_ids: list = None):
    """
    Find all the files in the folder.
    :param method_ids: The method ids need to be found.
    :param folder_path: The folder path.
    :return: The file list.
    """
    file_list = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.split("%")[0] not in method_ids:
                continue
            file_list.append(file)
    return file_list


def start_generation(sql_query, multiprocess=True, repair=True, confirmed=False):
    """
    Start the scope test.
    :param multiprocess: if it needs to
    :param repair:
    :param sql_query:
    :return:
    """
    match = re.search(r"project_name\s*=\s*'([\w-]*)'", sql_query)   #正则表达式寻找 project_name 字段，并获取其等号后面的值
    if match:
        project_name = match.group(1)
        print(project_name)
    else:
        raise RuntimeError("One project at one time.")
    # delete the old result
    remove_single_test_output_dirs(get_project_abspath())  #删除旧的测试输出目录

    method_ids = [x[0] for x in db.select(script=sql_query)]  #从数据库中获取方法 ID
    if not method_ids:
        raise Exception("Method ids cannot be None.")
    if not isinstance(method_ids[0], str):
        method_ids = [str(i) for i in method_ids]
    print("You are about to start the whole process of scope test.")  #
    print("The number of methods is ", len(method_ids), ".")
    print("The approximate cost will be", Fore.RED + "$", len(method_ids) * 0.0184 * test_number, ".", Style.RESET_ALL)
    #record = "This is a record of a scope test.\n"
    if not confirmed:
        confirm = input("Are you sure to start the scope test? (y/n): ")
        if confirm != "y":
            print("Scope test cancelled.")
            return  #如果用户输入 y，则继续测试；否则打印“Scope test cancelled.”并退出函数。

    # Create the new folder
    result_path = create_dataset_result_folder("")  #创建一个新的文件夹来存放测试结果，result_path 保存这个路径。如../result/scope_test%20250116160617%
    record = "This is a record of a scope test.\n"
    record += "Result path: " + result_path + "\n"
    record += 'SQL script: "' + sql_query + '"\n'
    record += "Included methods: " + str(method_ids) + "\n"  #初始化一个记录字符串 record，记录测试的相关信息：结果路径、SQL 查询和方法 ID

    record_path = os.path.join(result_path, "record.txt")  #如../result/scope_test%20250116160617%/record.txt
    with open(record_path, "w") as f:
        f.write(record)
    print(Fore.GREEN + "The record has been saved at", record_path, Style.RESET_ALL)  #将记录信息写入 record.txt 文件，并打印出文件保存的路径。

    # Find all the files
    source_dir = os.path.join(dataset_dir, "direction_1")  #如../dataset/direction_1

    start_whole_process(source_dir, result_path, multiprocess=multiprocess, repair=repair)
    print("WHOLE PROCESS FINISHED")
    # Run accumulated tests
    project_path = os.path.abspath(project_dir)
    print("START ALL TESTS")

    Task.all_test(result_path, project_path)
    try:
        with open(record_path, "a") as f:
            f.write("Whole test result at: " + find_result_in_projects() + "\n")
    except Exception as e:
        print("Cannot save whole test result.")
        print(e)

    print("SCOPE TEST FINISHED")


if __name__ == '__main__':
    sql_query = "SELECT id FROM method WHERE project_name='Lang_1_f' AND class_name='NumberUtils' AND is_constructor=0;"
    start_generation(sql_query, multiprocess=True, repair=True, confirmed=False)
