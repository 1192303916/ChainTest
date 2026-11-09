import os.path
import time

from tools import *
from database import *
from parse_data import parse_data
from export_data import export_data
from scope_test import start_generation
from parse_xml import result_analysis
from task import Task


def clear_dataset():
    """
    Clear the dataset folder.
    :return: None
    """
    # Delete the dataset folder
    if os.path.exists(dataset_dir):
        shutil.rmtree(dataset_dir) #如果文件夹存在，调用 shutil 模块中的 rmtree 函数递归地删除该文件夹及其所有内容（包括子文件和子文件夹）。


def run():
    """
    Generate the test cases with one-click.
    :return: None
    """
    # #Delete history data
    # drop_table()
    #
    # #Create the table
    # create_table()
    #
    # #Parse project
    # info_path = Task.parse(project_dir)  #如../classinfo/Chart
    #
    # #Parse data
    # parse_data(info_path)  #解析指定目录下的 .json 文件，提取其中的类和方法信息，并将这些信息存入数据库。
    #
    # #clear last dataset
    # clear_dataset()  #删除dataset目录
    #
    # #Export data for multi-process
    # export_data()  #从数据库导出方法和类的相关信息，并根据不同的方向（direction_1 和 direction_3）生成结构化的 JSON 文件存储在不同的文件夹中（如 direction_1、direction_3 和 raw_data）。

    project_name = os.path.basename(os.path.normpath(project_dir))  #从路径中提取最后一个文件或目录的名称并将其规范化

    # Modify SQL query to test the designated classes.
    sql_query = """
        SELECT id FROM method WHERE project_name='{}';
    """.format(project_name)

    # Start the whole process
    start_generation(sql_query, multiprocess=False, repair=True, confirmed=False)

    # Export the result
    result_analysis()


if __name__ == '__main__':
    print("Make sure the config.ini is correctly configured.")
    # seconds = 5
    # while seconds > 0:
    #     print(seconds)
    #     time.sleep(1)  # Pause for 1 second
    #     seconds -= 1
    run()
