"""
This file is for parsing the .json data.
And insert them into Current Database.

Author: Xie zhuokui
Date: 2023-04-01
"""

import json
import os
from database import database


def parse_data(dir_path: str):
    """
    Parse the data from .json files.
    :param dir_path: the path of the .json files.
    :return: None
    """
    db = database()
    for root, dirs, files in os.walk(dir_path):  #使用 os.walk() 遍历指定目录 dir_path 及其子目录，获取文件路径。对于每个文件，如果它的扩展名是 .json，则会继续处理。
        for filename in files:
            if filename.endswith('.json'):
                with open(os.path.join(root, filename), "r") as f:
                    json_data = json.load(f)

                for class_data in json_data:
                    # Get class data
                    project_name = class_data['project_name']
                    class_name = class_data['class_name']
                    class_path = class_data['class_path']
                    c_sig = class_data['c_sig']  #从 class_data 中提取该类所属的项目名称、类名、类路径和类签名

                    if class_data['superclass']:
                        super_class = class_data['superclass'].split(' ')[1]
                    else:
                        super_class = ""  #检查类是否有父类。如果有，提取父类的名称；如果没有父类，则将其设置为空字符串。

                    if class_data['imports']:
                        imports = "\n".join(class_data['imports'])
                    else:
                        imports = ""  #检查类是否有导入的包。如果有，将它们合并成一个字符串（每个包名占一行）；如果没有，则设置为空字符串。

                    if "package" in class_data:
                        package = class_data["package"]
                    else:
                        package = ""  #检查类是否有 package 字段，如果有，则提取包名；否则，设置为空字符串。

                    has_constructor = class_data['has_constructor']  #提取类是否有构造函数的信息。

                    # Get field data
                    fields = []
                    for field in class_data['fields']:
                        if field['original_string'] not in fields:
                            fields.append(field['original_string'])
                    fields = "\n".join(fields)  #遍历类的字段数据，提取每个字段的 original_string（字段的原始字符串），并去重。然后将字段信息合并成一个字符串，每个字段占一行。

                    # Will append from all constructors
                    c_deps = {}  #初始化一个空字典 c_deps 用于存储构造函数的依赖关系。

                    # Get method data
                    methods = class_data['methods']
                    for method_data in methods:  #遍历该类的所有方法，method_data 是每个方法的详细信息。
                        m_sig = method_data['m_sig']
                        method_name = method_data['method_name']
                        source_code = method_data['source_code']
                        use_field = method_data['use_field']
                        parameters = method_data['parameters']
                        if "public" in method_data['modifiers']:
                            is_public = True
                        else:
                            is_public = False
                        is_constructor = method_data['is_constructor']
                        is_get_set = method_data['is_get_set']
                        m_deps = method_data['m_deps']  #从 method_data 中提取方法的签名、方法名、源代码、使用的字段、参数、修饰符、是否是构造函数、是否是 getter/setter 方法以及方法的依赖。

                        # Add dependencies from constructor
                        if is_constructor:
                            for dep_class in m_deps:
                                if dep_class not in c_deps:
                                    c_deps[dep_class] = []
                                c_deps[dep_class].append(m_deps[dep_class])  #如果方法是构造函数，遍历方法的依赖类，将这些依赖类添加到 c_deps 字典中。

                        # insert method data into table method
                        db.insert("method", row={"project_name": project_name,
                                                 "signature": m_sig,
                                                 "method_name": method_name,
                                                 "parameters": parameters,
                                                 "source_code": source_code,
                                                 "class_name": class_name,
                                                 "dependencies": str(m_deps),
                                                 "use_field": use_field,
                                                 "is_constructor": is_constructor,
                                                 "is_get_set": is_get_set,
                                                 "is_public": is_public})  #将提取的每个方法的数据插入到 method 表中。

                    # insert class data into table class
                    db.insert("class", row={"project_name": project_name,
                                            "class_name": class_name,
                                            "class_path": class_path,
                                            "signature": c_sig,
                                            "super_class": super_class,
                                            "package": package,
                                            "imports": imports,
                                            "fields": fields,
                                            "has_constructor": has_constructor,
                                            "dependencies": str(c_deps)})  #将提取的类数据插入到 class 表中。
                    print(class_name, "FINISHED!")


if __name__ == '__main__':
    print("This action will alter the information in database.")
    confirm = input("Are you sure to parse the data? (y/n) ")
    if confirm == "y":
        parse_data("/Users/chenyi/Desktop/ChatTester/TestGPT_ASE/information/Lang")
    else:
        print("Canceled.")
