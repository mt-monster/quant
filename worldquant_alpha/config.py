import json
import os
from os.path import expanduser
from dotenv import load_dotenv

# 配置文件路径
ENV_FILE = expanduser('.env')

def load_credentials_from_env():
    """从环境变量加载凭证"""
    # 尝试加载.env文件
    load_dotenv(ENV_FILE)
    
    username = os.environ.get('WQ_USERNAME')
    password = os.environ.get('WQ_PASSWORD')
    
    return username, password

def get_credentials():
    """获取凭证，优先使用环境变量，其次使用配置文件"""
    # 首先尝试从环境变量获取
    username, password = load_credentials_from_env()
    
    return username, password

def save_credentials_to_env(username, password):
    """保存凭证到环境变量文件"""
    try:
        # 检查是否存在.env文件
        if os.path.exists(ENV_FILE):
            # 读取现有内容
            with open(ENV_FILE, 'r') as f:
                lines = f.readlines()
            
            # 更新或添加凭证
            updated_username = False
            updated_password = False
            
            for i, line in enumerate(lines):
                if line.startswith('WQ_USERNAME='):
                    lines[i] = f'WQ_USERNAME={username}\n'
                    updated_username = True
                elif line.startswith('WQ_PASSWORD='):
                    lines[i] = f'WQ_PASSWORD={password}\n'
                    updated_password = True
            
            # 如果没有找到相应的行，添加到文件末尾
            if not updated_username:
                lines.append(f'WQ_USERNAME={username}\n')
            if not updated_password:
                lines.append(f'WQ_PASSWORD={password}\n')
            
            # 写回文件
            with open(ENV_FILE, 'w') as f:
                f.writelines(lines)
        else:
            # 创建新文件
            with open(ENV_FILE, 'w') as f:
                f.write(f'WQ_USERNAME={username}\n')
                f.write(f'WQ_PASSWORD={password}\n')
        
        return True
    except Exception as e:
        print(f"保存凭证到环境变量文件时出错: {e}")
        return False 