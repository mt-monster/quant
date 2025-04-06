import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os
from datetime import datetime
import json

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# 邮件配置
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.example.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
EMAIL_FROM = os.environ.get('EMAIL_FROM', 'alpha@example.com')
EMAIL_TO = os.environ.get('EMAIL_TO', 'user@example.com')

def send_email_notification(subject, body, html=False):
    """发送邮件通知"""
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.error("邮件配置不完整，无法发送邮件")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        msg['Subject'] = subject
        
        # 设置正文
        if html:
            msg.attach(MIMEText(body, 'html', 'utf-8'))
        else:
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # 连接SMTP服务器并发送
        if SMTP_PORT == 465:
            # 使用SSL连接
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            # 使用TLS连接
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()  # 启用TLS加密
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        
        logger.info(f"邮件发送成功，主题: {subject}")
        return True
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False

def send_alpha_test_notification(alpha_id, alpha_expression, result):
    """发送单个Alpha测试结果通知"""
    good_alpha = result.get('is_good_alpha', False)
    logger.info(f"准备发送Alpha测试结果通知，Alpha ID: {alpha_id}")
    subject = f"Alpha测试完成通知 (ID: {alpha_id})"
    if good_alpha:
        subject = f"发现优质alpha，Alpha测试通过 (ID: {alpha_id})"
    
    if result:
        # 记录原始结果格式以便调试
        try:
            logger.info(f"发送通知的原始结果数据: {json.dumps(result)[:300]}...")
        except:
            logger.info(f"发送通知的原始结果数据无法JSON序列化")
        
        # 兼容不同的结果格式
        if 'is' in result:
            # 新格式
            is_data = result.get('is', {})
            performance = f"""
            Sharpe值: {is_data.get('sharpe', 'N/A')}
            Fitness值: {is_data.get('fitness', 'N/A')}
            PNL: {is_data.get('pnl', 'N/A')}
            收益率: {is_data.get('returns', 'N/A')}
            最大回撤: {is_data.get('drawdown', 'N/A')}
            Turnover值: {is_data.get('turnover', 'N/A')}
            是否是优质alpha: {'是' if result.get('is_good_alpha', False) else '否'}
            """
            checks = is_data.get('checks', [])
            checks_info = "\n        ".join([f"{check['name']}: {check['result']}" for check in checks]) if checks else "无检查结果"
            
            status = "未提交" if result.get('status') == 'UNSUBMITTED' else result.get('status', '未知')
            grade = result.get('grade', 'N/A')
        else:
            # 旧格式
            performance = f"""
            Sharpe值: {result.get('sharpe', 'N/A')}
            Turnover值: {result.get('turnover', 'N/A')}
            Fitness值: {result.get('fitness', 'N/A')}
            """
            checks_info = "无检查结果"
            status = result.get('status', '未知')
            grade = "N/A"
    else:
        performance = "未能获取性能指标"
        checks_info = "未能获取检查结果"
        status = "失败"
        grade = "N/A"
    
    body = f"""
    尊敬的用户，您的Alpha因子测试已完成！

    Alpha ID: {alpha_id}
    平台ID: {result.get('platform_id') or result.get('id') or result.get('alpha_id') or 'N/A'}
    Alpha表达式: {alpha_expression}
    测试状态: {status}
    等级: {grade}
    测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    
    性能指标:
    {performance}
    
    检查结果:
    {checks_info}
    
    作者: {result.get('author', 'N/A')}
    创建日期: {result.get('dateCreated', 'N/A')}
    修改日期: {result.get('dateModified', 'N/A')}
    
    请登录系统查看更多详细信息。
    
    祝好，
    WorldQuant Alpha生成系统
    """
    
    success = send_email_notification(subject, body)
    if success:
        logger.info(f"Alpha测试结果通知发送成功，Alpha ID: {alpha_id}")
    else:
        logger.error(f"Alpha测试结果通知发送失败，Alpha ID: {alpha_id}")
    return success

def send_batch_completion_notification(total_count, success_count, good_alpha_count, ir_threshold=0.1):
    """发送批量测试完成通知"""
    subject = "Alpha批量测试完成通知"
    
    body = f"""
    尊敬的用户，您的批量Alpha因子测试已全部完成！

    测试总数: {total_count}
    成功测试: {success_count}
    测试失败: {total_count - success_count}
    优质Alpha数量 (IR > {ir_threshold}): {good_alpha_count}
    完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    
    请登录系统查看更多详细信息和分析结果。
    
    祝好，
    WorldQuant Alpha生成系统
    """
    
    return send_email_notification(subject, body)

def send_error_notification(error_message):
    """发送错误通知"""
    subject = "Alpha测试系统错误通知"
    
    body = f"""
    尊敬的用户，Alpha测试系统遇到错误：

    错误信息: {error_message}
    发生时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    
    请检查系统日志获取更多信息。
    
    祝好，
    WorldQuant Alpha生成系统
    """
    
    return send_email_notification(subject, body)

def send_backtest_results_notification(results):
    """发送回测结果通知"""
    if not results:
        logger.warning("无回测结果可发送")
        return False
    
    # 兼容新的结果格式
    if isinstance(results, dict) and 'results' in results:
        results_list = results.get('results', [])
        total_count = results.get('total_processed', 0)
        success_count = results.get('success_count', 0)
        good_alpha_count = results.get('good_alpha_count', 0)
        
        return send_batch_completion_notification(total_count, success_count, good_alpha_count)
    
    # 兼容旧格式
    valid_alphas = [r for r in results if r.get('status') == 'valid']
    invalid_alphas = [r for r in results if r.get('status') == 'invalid']
    
    subject = f"Alpha回测结果通知 ({len(valid_alphas)}/{len(results)}有效)"
    
    # 构建邮件正文
    body = f"""
    尊敬的用户，您的Alpha回测已完成！

    回测总数: {len(results)}
    有效Alpha数: {len(valid_alphas)}
    无效Alpha数: {len(invalid_alphas)}
    完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    
    有效Alpha列表:
    """
    
    for idx, alpha in enumerate(valid_alphas, 1):
        body += f"""
    {idx}. ID: {alpha.get('id')}
       表达式: {alpha.get('expression')[:50]}...
       Sharpe: {alpha.get('is', {}).get('sharpe', 'N/A')}
    """
    
    body += """
    请登录系统查看更多详细信息。
    
    祝好，
    WorldQuant Alpha生成系统
    """
    
    return send_email_notification(subject, body)

# 为了兼容main.py中的调用
def send_email(results):
    """兼容main.py中的调用，发送回测结果通知"""
    return send_backtest_results_notification(results) 