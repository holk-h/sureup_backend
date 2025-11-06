"""
工具函数 - 初始化 Appwrite 客户端
"""
import os
from appwrite.client import Client
from appwrite.services.databases import Databases


def get_appwrite_client() -> Client:
    """创建 Appwrite 客户端"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://api.delvetech.cn/v1'))
    client.set_project(os.environ.get('APPWRITE_PROJECT_ID', '6901942c30c3962e66eb'))
    client.set_key(os.environ.get('APPWRITE_API_KEY', ''))
    return client


def get_databases() -> Databases:
    """获取数据库服务实例"""
    client = get_appwrite_client()
    return Databases(client)

