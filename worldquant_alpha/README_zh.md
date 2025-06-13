# WorldQuant Alpha策略生成和回测工具

这是一个用于自动生成、回测和分析WorldQuant Alpha策略的工具，通过wd_lib库与WorldQuant Brain平台集成，提供了完整的Alpha因子生命周期管理。

## 功能特点

- 自动生成Alpha策略表达式
- 批量回测Alpha策略
- 分析Alpha策略性能指标
- 筛选高质量Alpha
- 支持模板化生成
- 自动化流程管理

## 安装步骤

### 前提条件

- Python 3.7+
- MySQL数据库
- WorldQuant账号和API访问权限

### 安装过程

1. 克隆仓库

```bash
git clone <repository-url>
cd worldquant_a
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 创建并配置.env文件

```bash
cp .env.example .env
```

然后编辑.env文件，填入必要的配置信息。

## 环境变量配置

以下是必要的环境变量：

```
# WorldQuant 凭据
WQ_USERNAME=your_username
WQ_PASSWORD=your_password

# 数据库配置
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_db_password
DB_NAME=worldquant_alpha

# 邮件通知配置（可选）
SMTP_SERVER=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your_email
SMTP_PASSWORD=your_email_password
EMAIL_FROM=alpha@example.com
EMAIL_TO=user@example.com

# 日志级别
LOG_LEVEL=INFO
```

## 初始化系统

首次运行前，需要初始化系统：

```bash
python main.py init
```

或使用Click命令行接口：

```bash
python -m main init
```

这将创建必要的数据库表结构。

## 主要功能和命令

### 获取数据字段

获取WorldQuant平台上的基本面数据字段：

```bash
python -m main fetch --dataset model77
```

### 生成Alpha表达式

从模板生成Alpha表达式：

```bash
python -m main generate --template 0 --limit 1000
```

参数说明：
- `--template`: 模板索引，0-4之间的整数
- `--limit`: 生成的Alpha数量限制

### 批量生成Alpha表达式

从多个模板批量生成Alpha表达式：

```bash
python -m main generate_batch --start_template 5 --end_template 10 --limit_per_template 5
```

参数说明：
- `--start_template`: 起始模板索引
- `--end_template`: 结束模板索引
- `--limit_per_template`: 每个模板生成的Alpha数量限制

### 运行回测

对数据库中的Alpha进行回测：

```bash
python -m main backtest --from_db
```

参数说明：
- `--from_db`: 从数据库获取Alpha（必须指定）
- `--limit`: 回测的Alpha数量限制

### 分析结果

分析回测结果，获取优质Alpha：

```bash
python -m main analyze --ir_threshold 0.1 --limit 100
```

参数说明：
- `--ir_threshold`: IR阈值，用于筛选优质Alpha
- `--limit`: 分析的Alpha数量限制

### 运行完整流程

运行完整的Alpha生成、回测和分析流程：

```bash
python -m main pipeline --template 0 --limit 10 --ir_threshold 0.1
```

参数说明：
- `--template`: 模板索引
- `--limit`: 生成的Alpha数量限制
- `--ir_threshold`: IR阈值

## 使用示例

### 完整流程示例

以下是一个完整的Alpha生成、回测和分析流程示例：

1. 初始化系统
```bash
python -m main init
```

2. 获取数据字段
```bash
python -m main fetch --dataset fundamental6
```

3. 生成Alpha表达式
```bash
python -m main generate
```

4. 运行回测
```bash
python -m main backtest --from_db 
```

5. 分析结果
```bash
python -m main analyze --ir_threshold 0.15
```

### 自动化流程示例

使用pipeline命令自动执行完整流程：

```bash
python -m main pipeline --template 0 --limit 50 --ir_threshold 0.15
```

## 项目结构

- `main.py`: 主程序入口
- `wd_lib_wrapper.py`: WorldQuant API封装
- `backtest.py`: 回测功能实现
- `database.py`: 数据库操作
- `notification.py`: 通知功能
- `alpha_generator.py`: Alpha生成器

## 常见问题

### Q: 无法连接WorldQuant API
A: 请检查您的WQ_USERNAME和WQ_PASSWORD是否正确，以及是否有API访问权限。

### Q: 数据库连接失败
A: 请确保MySQL数据库已启动，并且DB_HOST、DB_PORT、DB_USER、DB_PASSWORD和DB_NAME配置正确。

### Q: 回测结果为空
A: 请检查您的Alpha表达式是否有效，以及是否已正确保存到数据库。

### Q: 邮件通知未发送
A: 请确保SMTP_SERVER、SMTP_PORT、SMTP_USERNAME、SMTP_PASSWORD、EMAIL_FROM和EMAIL_TO配置正确。

## 贡献

欢迎提交问题和Pull Request。

## 许可证

[MIT](LICENSE) 