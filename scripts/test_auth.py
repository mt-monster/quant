#!/usr/bin/env python3
"""
WorldQuant BRAIN 平台认证测试脚本
"""

import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# 添加项目路径
def test_config():
    """测试配置文件是否存在及内容"""
    print("🔍 检查配置...")
    
    # 加载 .env 文件
    env_path = Path(".env")
    if env_path.exists():
        print("✅ .env 文件存在")
        load_dotenv(env_path)  # 加载环境变量
        
        with open(env_path, 'r', encoding='utf-8') as f:
            content = f.read()
            print(f"📄 .env 文件内容:\n{content}")
            
        # 检查环境变量
        wq_username = os.environ.get('WQ_USERNAME')
        wq_password = os.environ.get('WQ_PASSWORD')
        
        print(f"📧 WQ_USERNAME: {'已设置' if wq_username else '未设置'}")
        print(f"🔑 WQ_PASSWORD: {'已设置' if wq_password else '未设置'}")
        
        if wq_username and wq_password:
            print("✅ 环境变量已正确配置")
            return wq_username, wq_password
        else:
            print("❌ 环境变量未正确配置")
            return None, None
    else:
        print("❌ .env 文件不存在")
        return None, None

def test_mcp_import():
    """测试MCP导入是否正常"""
    print("\n🔍 测试MCP导入...")
    try:
        from cnhkmcp.untracked.mcp文件论坛版2_如果原版启动不了浏览器就试这个.platform_functions import authenticate, load_config
        print("✅ MCP模块导入成功")
        return True
    except ImportError as e:
        print(f"❌ MCP模块导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ MCP模块导入异常: {e}")
        return False

async def test_authentication(email, password):
    """测试认证功能"""
    print("\n🔍 测试认证功能...")
    try:
        from cnhkmcp.untracked.mcp文件论坛版2_如果原版启动不了浏览器就试这个.platform_functions import authenticate
        
        # 调用认证函数
        result = await authenticate(email=email, password=password)
        print(f"📊 认证结果: {result}")
        
        if 'error' in result:
            print(f"❌ 认证失败: {result['error']}")
            return False
        elif result.get('status') == 'authenticated':
            print("✅ 认证成功!")
            return True
        else:
            print(f"⚠️ 认证状态未知: {result}")
            return False
            
    except Exception as e:
        print(f"❌ 认证过程中发生异常: {e}")
        import traceback
        print(f"详细错误信息:\n{traceback.format_exc()}")
        return False

async def main():
    """主函数"""
    print("🚀 开始测试 WorldQuant BRAIN 平台认证...")
    
    # 检查配置
    username, password = test_config()
    
    if not username or not password:
        print("\n💡 提示: 请先在 .env 文件中配置 WQ_USERNAME 和 WQ_PASSWORD")
        print("示例内容:")
        print("# WorldQuant凭据")
        print("WQ_USERNAME=your_email@example.com")
        print("WQ_PASSWORD=your_password")
        return
    
    # 测试MCP导入
    if not test_mcp_import():
        print("\n❌ MCP导入失败，无法继续测试")
        return
    
    # 测试认证
    success = await test_authentication(username, password)
    
    if success:
        print("\n🎉 认证测试成功完成!")
    else:
        print("\n💥 认证测试失败!")

if __name__ == "__main__":
    asyncio.run(main())