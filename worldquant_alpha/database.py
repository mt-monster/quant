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
    fitness = Column(Float, nullable=True)  # 回测后的Fitness值
    turnover = Column(Float, nullable=True)  # 回测后的Turnover值
    
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
    self_corr = Column(Float, nullable=True)  # 自相关性
    raw_result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    
    def __repr__(self):
        return f"<AlphaResult(id={self.id}, alpha_id={alpha_id}, ic={self.ic})>"


class PipelineAlpha(Base):
    """Pipeline生成的Alpha存储模型"""
    __tablename__ = 'pipeline_alphas'

    id = Column(Integer, primary_key=True, autoincrement=True)
    alpha_expression = Column(Text, nullable=False)
    expression_hash = Column(String(64), nullable=False, index=True)  # 表达式哈希，用于快速比较
    order = Column(Integer, default=1)  # 阶数：1=一阶，2=二阶，3=三阶
    stage = Column(String(50), nullable=False)  # 阶段：first_order, second_order, third_order
    settings = Column(JSON, nullable=True)  # 回测设置
    created_at = Column(DateTime, default=datetime.now)

    # 关联的Alpha表ID（用于关联到主Alpha表）
    alpha_id = Column(Integer, nullable=True)

    # 回测结果
    is_tested = Column(Boolean, default=False)
    backtest_status = Column(String(20), default='pending')  # pending, running, completed, failed
    platform_alpha_id = Column(String(100), nullable=True)  # WorldQuant平台返回的ID
    sharpe = Column(Float, nullable=True)
    fitness = Column(Float, nullable=True)
    turnover = Column(Float, nullable=True)
    color = Column(String(20), nullable=True)  # 颜色标记
    self_corr = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)  # 错误信息
    backtested_at = Column(DateTime, nullable=True)  # 回测完成时间

    __table_args__ = (
        Index('idx_expression_hash', 'expression_hash', unique=True),
        Index('idx_order_stage', 'order', 'stage'),
    )

    def __repr__(self):
        return f"<PipelineAlpha(id={self.id}, order={self.order}, stage={self.stage}, tested={self.is_tested})>"


def get_pipeline_alpha_by_hash(session, expression_hash: str):
    """通过表达式哈希获取Pipeline Alpha"""
    return session.query(PipelineAlpha).filter_by(expression_hash=expression_hash).first()


def save_pipeline_alphas(session, alphas: list, order: int, stage: str, settings: dict = None):
    """批量保存Pipeline Alpha"""
    saved_count = 0
    skipped_count = 0
    error_count = 0

    logger.info(f"[DB] save_pipeline_alphas 开始保存: order={order}, stage={stage}, 数量={len(alphas)}")
    for idx, alpha_expr in enumerate(alphas):
        try:
            import hashlib
            if not isinstance(alpha_expr, str):
                logger.warning(f"[DB] alpha_expr[{idx}] 不是字符串类型: {type(alpha_expr)}")
                alpha_expr = str(alpha_expr)
            expr_hash = hashlib.sha256(alpha_expr.encode()).hexdigest()

            existing = get_pipeline_alpha_by_hash(session, expr_hash)
            if existing:
                skipped_count += 1
                continue

            new_alpha = PipelineAlpha(
                alpha_expression=alpha_expr,
                expression_hash=expr_hash,
                order=order,
                stage=stage,
                settings=settings,
                is_tested=False,
                backtest_status='pending'
            )
            session.add(new_alpha)
            saved_count += 1
        except Exception as e:
            error_count += 1
            logger.error(f"[DB] 保存第 {idx} 个 alpha 失败: {e}")

    session.commit()
    logger.info(f"[DB] save_pipeline_alphas 完成: 新增={saved_count}, 跳过={skipped_count}, 错误={error_count}")
    return saved_count, skipped_count


def get_untested_pipeline_alphas(session, order: int, stage: str):
    """获取未回测的Pipeline Alpha"""
    return session.query(PipelineAlpha).filter_by(
        order=order,
        stage=stage,
        is_tested=False,
        backtest_status='pending'
    ).all()


def update_pipeline_alpha_backtest(session, expression_hash: str, **kwargs):
    """更新Pipeline Alpha的回测结果"""
    logger.info(f"[DB] update_pipeline_alpha_backtest 被调用，hash={expression_hash[:16]}...")
    alpha = get_pipeline_alpha_by_hash(session, expression_hash)
    if alpha:
        for key, value in kwargs.items():
            if hasattr(alpha, key):
                setattr(alpha, key, value)
        session.commit()
        logger.info(f"[DB] 更新成功，alpha_id={alpha.id}, stage={alpha.stage}, order={alpha.order}")
        return True
    else:
        logger.warning(f"[DB] 未找到对应的Pipeline Alpha，hash={expression_hash[:16]}...")
        return False


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
        
        # 为每个alphas表添加必要的列（直接尝试添加，忽略已存在的错误）
        for table in alpha_tables:
            logger.info(f"检查表: {table}")
            
            # 直接尝试添加列，忽略已存在的错误
            columns_to_add = [
                ("submitted_at", "ADD COLUMN submitted_at DATETIME NULL"),
                ("sharpe", "ADD COLUMN sharpe FLOAT NULL"),
                ("fitness", "ADD COLUMN fitness FLOAT NULL"),
                ("turnover", "ADD COLUMN turnover FLOAT NULL"),
            ]
            
            for col_name, alter_stmt in columns_to_add:
                try:
                    with engine.connect() as conn:
                        conn.execute(text(f"ALTER TABLE {table} {alter_stmt}"))
                        conn.commit()
                    logger.info(f"成功添加{col_name}列到 {table} 表")
                except Exception as e:
                    # 忽略"列已存在"错误
                    if "Duplicate column" in str(e) or "already exists" in str(e).lower():
                        logger.debug(f"{col_name}列已存在于 {table} 表")
                    else:
                        logger.warning(f"添加{col_name}列到 {table} 表失败: {e}")
        
        # 检查alpha_results表，添加必要的列（直接尝试添加，忽略已存在的错误）
        if 'alpha_results' in all_tables:
            result_columns_to_add = [
                ("color", "ADD COLUMN color VARCHAR(20) NULL"),
                ("self_corr", "ADD COLUMN self_corr FLOAT NULL"),
            ]
            
            for col_name, alter_stmt in result_columns_to_add:
                try:
                    with engine.connect() as conn:
                        conn.execute(text(f"ALTER TABLE alpha_results {alter_stmt}"))
                        conn.commit()
                    logger.info(f"成功添加{col_name}列到alpha_results表")
                except Exception as e:
                    if "Duplicate column" in str(e) or "already exists" in str(e).lower():
                        logger.debug(f"{col_name}列已存在于alpha_results表")
                    else:
                        logger.warning(f"添加{col_name}列到alpha_results表失败: {e}")
        
        # 检查并更新pipeline_alphas表结构
        if 'pipeline_alphas' in all_tables:
            logger.info("检查pipeline_alphas表结构...")
            pipeline_columns_to_add = [
                ("alpha_id", "ADD COLUMN alpha_id INT NULL"),
                ("sharpe", "ADD COLUMN sharpe FLOAT NULL"),
                ("fitness", "ADD COLUMN fitness FLOAT NULL"),
                ("turnover", "ADD COLUMN turnover FLOAT NULL"),
                ("color", "ADD COLUMN color VARCHAR(20) NULL"),
                ("self_corr", "ADD COLUMN self_corr FLOAT NULL"),
            ]

            for col_name, alter_stmt in pipeline_columns_to_add:
                try:
                    with engine.connect() as conn:
                        conn.execute(text(f"ALTER TABLE pipeline_alphas {alter_stmt}"))
                        conn.commit()
                    logger.info(f"成功添加{col_name}列到pipeline_alphas表")
                except Exception as e:
                    if "Duplicate column" in str(e) or "already exists" in str(e).lower():
                        logger.debug(f"{col_name}列已存在于pipeline_alphas表")
                    else:
                        logger.warning(f"添加{col_name}列到pipeline_alphas表失败: {e}")
        
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

def get_alpha_id_by_expression(alpha_expression):
    """根据Alpha表达式获取数据库ID（用于已存在的Alpha）"""
    session = get_session()
    try:
        alpha = session.query(Alpha).filter_by(alpha_expression=alpha_expression).first()
        return alpha.id if alpha else None
    except Exception as e:
        logger.error(f"根据表达式查询Alpha ID时出错: {e}")
        return None
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

def save_alpha_result(alpha_id, platform_id=None, ic=None, ir=None, sharpe=None, turnover=None, fitness=None, color=None, self_corr=None, raw_result=None):
    """保存Alpha回测结果"""
    logger.info(f"save_alpha_result 接收到的参数: alpha_id={alpha_id}, sharpe={sharpe}, turnover={turnover}, fitness={fitness}, color={color}, self_corr={self_corr}")
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
            self_corr=self_corr,
            raw_result=raw_result
        )
        session.add(result)
        session.commit()
        logger.info(f"Alpha结果保存成功，Alpha ID: {alpha_id}, Color: {color}, Sharpe: {sharpe}, Self_Corr: {self_corr}")
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

def update_alpha_sharpe(alpha_id, sharpe, fitness=None, turnover=None):
    """更新alpha的回测结果（Sharpe、Fitness、Turnover）"""
    logger.info(f"update_alpha_sharpe 接收到的参数: alpha_id={alpha_id}, sharpe={sharpe}, fitness={fitness}, turnover={turnover}")
    session = get_session()
    try:
        alpha = session.query(Alpha).filter_by(id=alpha_id).first()
        if alpha:
            alpha.sharpe = sharpe
            if fitness is not None:
                alpha.fitness = fitness
            if turnover is not None:
                alpha.turnover = turnover
            session.commit()
            logger.info(f"Alpha回测结果更新成功，ID: {alpha_id}, Sharpe: {sharpe}, Fitness: {fitness}, Turnover: {turnover}")
            return True
        else:
            logger.warning(f"未找到Alpha记录，ID: {alpha_id}")
            return False
    except Exception as e:
        session.rollback()
        logger.error(f"更新Alpha回测结果时出错: {e}")
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