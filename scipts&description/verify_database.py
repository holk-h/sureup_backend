#!/usr/bin/env python3
"""
数据库验证脚本

验证数据库和集合是否正确创建
"""

import os
import sys
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.storage import Storage

# 配置
APPWRITE_ENDPOINT = os.getenv('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1')
APPWRITE_PROJECT_ID = os.getenv('APPWRITE_PROJECT_ID', '')
APPWRITE_API_KEY = os.getenv('APPWRITE_API_KEY', '')

DATABASE_ID = 'main'

EXPECTED_COLLECTIONS = [
    'profiles',
    'user_knowledge_points',
    'knowledge_points_library',
    'questions',
    'mistake_records',
    'practice_sessions',
    'practice_answers',
    'question_feedbacks',
    'weekly_reports',
    'daily_tasks',
]

EXPECTED_BUCKETS = [
    'mistake-images',
    'question-images',
]


def init_client():
    """初始化Appwrite客户端"""
    if not APPWRITE_PROJECT_ID or not APPWRITE_API_KEY:
        print("❌ 错误：请设置环境变量 APPWRITE_PROJECT_ID 和 APPWRITE_API_KEY")
        sys.exit(1)
    
    client = Client()
    client.set_endpoint(APPWRITE_ENDPOINT)
    client.set_project(APPWRITE_PROJECT_ID)
    client.set_key(APPWRITE_API_KEY)
    
    return client


def verify_database(databases: Databases):
    """验证数据库"""
    try:
        db = databases.get(DATABASE_ID)
        print(f"✅ 数据库存在: {db['name']}")
        return True
    except Exception as e:
        print(f"❌ 数据库不存在: {e}")
        return False


def verify_collections(databases: Databases):
    """验证集合"""
    print("\n📋 检查集合...")
    
    existing_collections = []
    missing_collections = []
    
    for collection_id in EXPECTED_COLLECTIONS:
        try:
            collection = databases.get_collection(DATABASE_ID, collection_id)
            existing_collections.append(collection_id)
            
            # 获取属性数量
            attributes = collection.get('attributes', [])
            indexes = collection.get('indexes', [])
            
            print(f"  ✅ {collection['name']} ({len(attributes)} 属性, {len(indexes)} 索引)")
            
        except Exception as e:
            missing_collections.append(collection_id)
            print(f"  ❌ {collection_id} - 不存在")
    
    return existing_collections, missing_collections


def verify_buckets(storage: Storage):
    """验证存储桶"""
    print("\n🗂️  检查存储桶...")
    
    existing_buckets = []
    missing_buckets = []
    
    for bucket_id in EXPECTED_BUCKETS:
        try:
            bucket = storage.get_bucket(bucket_id)
            existing_buckets.append(bucket_id)
            
            max_size_mb = bucket['maximumFileSize'] / 1024 / 1024
            print(f"  ✅ {bucket['name']} (最大 {max_size_mb:.0f}MB)")
            
        except Exception as e:
            missing_buckets.append(bucket_id)
            print(f"  ❌ {bucket_id} - 不存在")
    
    return existing_buckets, missing_buckets


def check_collection_details(databases: Databases, collection_id: str):
    """检查集合详细信息"""
    try:
        collection = databases.get_collection(DATABASE_ID, collection_id)
        
        print(f"\n📊 {collection['name']} 详情:")
        print(f"  Collection ID: {collection['$id']}")
        print(f"  Document Security: {collection.get('documentSecurity', False)}")
        
        # 属性
        attributes = collection.get('attributes', [])
        print(f"\n  属性 ({len(attributes)}):")
        for attr in attributes:
            required = '必填' if attr.get('required', False) else '可选'
            array_mark = '[]' if attr.get('array', False) else ''
            print(f"    - {attr['key']}: {attr['type']}{array_mark} ({required})")
        
        # 索引
        indexes = collection.get('indexes', [])
        print(f"\n  索引 ({len(indexes)}):")
        for idx in indexes:
            idx_type = idx['type']
            attributes_str = ', '.join(idx['attributes'])
            print(f"    - {idx['key']}: {idx_type} ({attributes_str})")
        
    except Exception as e:
        print(f"❌ 获取集合详情失败: {e}")


def main():
    """主函数"""
    print("\n" + "="*60)
    print("稳了！数据库验证脚本")
    print("="*60 + "\n")
    
    # 初始化客户端
    print("📡 连接到 Appwrite...")
    client = init_client()
    databases = Databases(client)
    storage = Storage(client)
    print("✅ 连接成功\n")
    
    # 验证数据库
    print("📂 检查数据库...")
    db_exists = verify_database(databases)
    
    if not db_exists:
        print("\n❌ 数据库不存在，请先运行 init_database.py")
        return
    
    # 验证集合
    existing_collections, missing_collections = verify_collections(databases)
    
    # 验证存储桶
    existing_buckets, missing_buckets = verify_buckets(storage)
    
    # 汇总
    print("\n" + "="*60)
    print("📊 验证结果")
    print("="*60)
    
    print(f"\n集合：{len(existing_collections)}/{len(EXPECTED_COLLECTIONS)} 存在")
    if missing_collections:
        print(f"  ❌ 缺失: {', '.join(missing_collections)}")
    
    print(f"\n存储桶：{len(existing_buckets)}/{len(EXPECTED_BUCKETS)} 存在")
    if missing_buckets:
        print(f"  ❌ 缺失: {', '.join(missing_buckets)}")
    
    # 详细信息
    if len(sys.argv) > 1 and sys.argv[1] == '--details':
        print("\n" + "="*60)
        print("📋 集合详细信息")
        print("="*60)
        
        for collection_id in existing_collections:
            check_collection_details(databases, collection_id)
    
    # 最终结果
    all_ok = (len(missing_collections) == 0 and len(missing_buckets) == 0)
    
    print("\n" + "="*60)
    if all_ok:
        print("✅ 所有检查通过！数据库配置正确")
    else:
        print("⚠️  存在问题，请运行 init_database.py 进行修复")
    print("="*60)
    
    print("\n💡 提示：使用 --details 参数查看详细信息")
    print("   python verify_database.py --details\n")


if __name__ == '__main__':
    main()

