import re

# Read the file
with open('d:/codes/quant/quant/.venv/Lib/site-packages/cnhkmcp/untracked/mcp文件论坛版2_如果原版启动不了浏览器就试这个/platform_functions.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the import section
content = content.replace('# Import the new forum client\ntry:\n    from forum_functions import forum_client\nexcept ImportError as e:\n    print(f"Warning: forum_functions module not available: {e}", file=sys.stderr)\n    forum_client = None', '# Import the new forum client\nforum_client = None  # 默认设为None，稍后动态导入\ndef _import_forum_client():\n    global forum_client\n    if forum_client is None:\n        try:\n            from forum_functions import forum_client as fc\n            forum_client = fc\n        except ImportError as e:\n            print(f"Warning: forum_functions module not available: {e}", file=sys.stderr)\n')

# Write the file back
with open('d:/codes/quant/quant/.venv/Lib/site-packages/cnhkmcp/untracked/mcp文件论坛版2_如果原版启动不了浏览器就试这个/platform_functions.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Import section updated successfully!')