import logging
import pymysql
import json
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, JSON, Index, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

# 配置日志
# 日志由 main.py 统一配置，这里只获取 logger
logger = logging.getLogger(__name__)

# 加载环境变量 - 确保从当前文件目录加载
current_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(current_dir, '.env'))

# 数据库配置
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = int(os.environ.get('DB_PORT', 3306))
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
DB_NAME = os.environ.get('DB_NAME', 'worldquant_alpha')

# 创建数据库引擎
try:
    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(DATABASE_URL)
    logger.info("数据库连接引擎创建成功")
except Exception as e:
    logger.error(f"创建数据库引擎失败: {e}")
    raise

# 创建基类
Base = declarative_base()
# 在模块顶部添加
from datetime import datetime
import os

# 生成唯一后缀（优先从环境变量获取，避免重复）
TABLE_SUFFIX = os.getenv('ALPHA_TABLE_SUFFIX', datetime.now().strftime("%Y%m%d"))

# 定义Alpha表模型
class Alpha(Base):
    __tablename__ = f'alphas_{TABLE_SUFFIX}'  # 动态表名
    id = Column(Integer, primary_key=True, autoincrement=True)
    alpha_expression = Column(Text, nullable=False)
    template_name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    submitted_at = Column(DateTime, nullable=True)  # 记录提交到平台的时间
    status = Column(String(20), default='pending')  # pending, running, completed, failed
    settings = Column(JSON, nullable=False)
    is_tested = Column(Boolean, default=False)
    sharpe = Column(Float, nullable=True)  # 回测后的Sharpe比率
    
    __table_args__ = (
        Index('idx_alpha_expression', 'alpha_expression', mysql_length=255, unique=True),
    )
    
    def __repr__(self):
        return f"<Alpha(id={self.id}, expression={self.alpha_expression[:30]}...)>"

# 定义结果表模型
class AlphaResult(Base):
    __tablename__ = 'alpha_results'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    alpha_id = Column(Integer, nullable=False)
    alpha_platform_id = Column(String(100), nullable=True)  # WorldQuant平台返回的ID
    ic = Column(Float, nullable=True)
    ir = Column(Float, nullable=True)
    sharpe = Column(Float, nullable=True)
    turnover = Column(Float, nullable=True)
    fitness = Column(Float, nullable=True)
    color = Column(String(20), nullable=True)  # 颜色标记（GREEN/BLUE/PURPLE等）
    raw_result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    
    def __repr__(self):
        return f"<AlphaResult(id={self.id}, alpha_id={self.alpha_id}, ic={self.ic})>"

# 创建会话工厂
SessionFactory = sessionmaker(bind=engine)

def init_db():
    """初始化数据库，创建表"""
    try:
        # 创建表
        Base.metadata.create_all(engine)
        logger.info("数据库表创建成功")
        
        # 检查是否需要更新表结构
        try:
            update_db_schema(engine)
        except Exception as e:
            logger.error(f"更新数据库结构失败: {e}")
        
        return True
    except Exception as e:
        logger.error(f"创建数据库表失败: {e}")
        return False

def update_db_schema(engine):
    """更新数据库表结构"""
    try:
        # 获取检查器
        inspector = inspect(engine)
        
        # 获取所有以alphas_开头的表
        all_tables = inspector.get_table_names()
        alpha_tables = [table for table in all_tables if table.startswith('alphas_')]
        
        logger.info(f"找到 {len(alpha_tables)} 个alphas表: {alpha_tables}")
        
        # 为每个alphas表添加必要的列
        for table in alpha_tables:
            logger.info(f"检查表: {table}")
            
            # 获取表的列信息
            columns = [col['name'] for col in inspector.get_columns(table)]
            
            # 检查并添加submitted_at列（如果不存在）
            if 'submitted_at' not in columns:
                logger.info(f"正在添加submitted_at列到 {table} 表...")
                with engine.connect() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN submitted_at DATETIME NULL"))
                    conn.commit()
                logger.info(f"成功添加submitted_at列到 {table} 表")
            
            # 检查并添加sharpe列（如果不存在）
            if 'sharpe' not in columns:
                logger.info(f"正在添加sharpe列到 {table} 表...")
                with engine.connect() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN sharpe FLOAT NULL"))
                    conn.commit()
                logger.info(f"成功添加sharpe列到 {table} 表")
        
        # 检查alpha_results表，添加color列（如果不存在）
        if 'alpha_results' in all_tables:
            result_columns = [col['name'] for col in inspector.get_columns('alpha_results')]
            if 'color' not in result_columns:
                logger.info("正在添加color列到alpha_results表...")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE alpha_results ADD COLUMN color VARCHAR(20) NULL"))
                    conn.commit()
                logger.info("成功添加color列到alpha_results表")
        
        return True
    except Exception as e:
        logger.error(f"检查或更新数据库结构时出错: {e}")
        raise

def get_session():
    """获取数据库会话"""
    return SessionFactory()

def alpha_exists(alpha_expression):
    """检查Alpha表达式是否已存在于数据库"""
    session = get_session()
    try:
        exists = session.query(Alpha).filter_by(alpha_expression=alpha_expression).first() is not None
        return exists
    except Exception as e:
        logger.error(f"查询Alpha表达式是否存在时出错: {e}")
        return False
    finally:
        session.close()

def save_alpha(alpha_expression, template_name, settings):
    """保存Alpha到数据库"""
    session = get_session()
    try:
        # 检查是否已存在
        if alpha_exists(alpha_expression):
            logger.info(f"Alpha表达式已存在: {alpha_expression}")
            return None
        
        # 创建新Alpha记录
        alpha = Alpha(
            alpha_expression=alpha_expression,
            template_name=template_name,
            settings=settings,
            status='pending'
        )
        session.add(alpha)
        session.commit()
        logger.info(f"Alpha保存成功，ID: {alpha.id}")
        return alpha.id
    except Exception as e:
        session.rollback()
        logger.error(f"保存Alpha时出错: {e}")
        return None
    finally:
        session.close()

def update_alpha_status(alpha_id, status):
    """更新Alpha状态"""
    session = get_session()
    try:
        alpha = session.query(Alpha).filter_by(id=alpha_id).first()
        if alpha:
            alpha.status = status
            if status == 'completed':
                alpha.is_tested = True
            session.commit()
            logger.info(f"Alpha状态更新成功，ID: {alpha_id}, 新状态: {status}")
            return True
        else:
            logger.warning(f"未找到Alpha，ID: {alpha_id}")
            return False
    except Exception as e:
        session.rollback()
        logger.error(f"更新Alpha状态时出错: {e}")
        return False
    finally:
        session.close()

def save_alpha_result(alpha_id, platform_id=None, ic=None, ir=None, sharpe=None, turnover=None, fitness=None, color=None, raw_result=None):
    """保存Alpha回测结果"""
    session = get_session()
    try:
        result = AlphaResult(
            alpha_id=alpha_id,
            alpha_platform_id=platform_id,
            ic=ic,
            ir=ir,
            sharpe=sharpe,
            turnover=turnover,
            fitness=fitness,
            color=color,
            raw_result=raw_result
        )
        session.add(result)
        session.commit()
        logger.info(f"Alpha结果保存成功，Alpha ID: {alpha_id}, Color: {color}, Sharpe: {sharpe}")
        return result.id
    except Exception as e:
        session.rollback()
        logger.error(f"保存Alpha结果时出错: {e}")
        return None
    finally:
        session.close()

def get_pending_alphas(limit=100):
    """获取待测试的Alpha列表"""
    session = get_session()
    try:
        alphas = session.query(Alpha).filter_by(status='pending').limit(limit).all()
        return alphas
    except Exception as e:
        logger.error(f"获取待测试Alpha时出错: {e}")
        return []
    finally:
        session.close()

def get_good_alphas(ir_threshold=0.1, limit=100):
    """获取IR大于阈值的优质Alpha"""
    session = get_session()
    try:
        results = session.query(Alpha, AlphaResult).join(
            AlphaResult, Alpha.id == AlphaResult.alpha_id
        ).filter(
            AlphaResult.ir >= ir_threshold
        ).limit(limit).all()
        return results
    except Exception as e:
        logger.error(f"获取优质Alpha时出错: {e}")
        return []
    finally:
        session.close()

def has_successful_submission_today():
    """检查今天是否已经成功提交了有效的alpha"""
    session = get_session()
    try:
        today = datetime.now().date()
        successful_alpha = session.query(Alpha).filter(
            Alpha.submitted_at >= today,
            Alpha.submitted_at < today + timedelta(days=1),
            Alpha.status == 'completed'
        ).first()
        return successful_alpha is not None
    except Exception as e:
        logger.error(f"检查今日提交状态时出错: {e}")
        return False
    finally:
        session.close()

def update_alpha_submission_time(alpha_id):
    """更新alpha的提交时间"""
    session = get_session()
    try:
        alpha = session.query(Alpha).filter_by(id=alpha_id).first()
        if alpha:
            alpha.submitted_at = datetime.now()
            session.commit()
            logger.info(f"Alpha提交时间更新成功，ID: {alpha_id}")
            return True
        return False
    except Exception as e:
        session.rollback()
        logger.error(f"更新Alpha提交时间时出错: {e}")
        return False
    finally:
        session.close() 

def update_alpha_sharpe(alpha_id, sharpe):
    """更新alpha的Sharpe比率"""
    session = get_session()
    try:
        alpha = session.query(Alpha).filter_by(id=alpha_id).first()
        if alpha:
            alpha.sharpe = sharpe
            session.commit()
            logger.info(f"Alpha Sharpe比率更新成功，ID: {alpha_id}, Sharpe: {sharpe}")
            return True
        return False
    except Exception as e:
        session.rollback()
        logger.error(f"更新Alpha Sharpe比率时出错: {e}")
        return False
    finally:
        session.close()


def close_database():
    """关闭数据库连接池"""
    try:
        if 'engine' in globals() and engine is not None:
            engine.dispose()
            logger.info("数据库连接池已关闭")
    except Exception as e:
        logger.error(f"关闭数据库连接时出错: {e}")