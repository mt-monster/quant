"""WorldQuant API简化封装模块"""
import logging
import os
import time
import random
import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

# 本地自相关性计算器（延迟导入，避免循环依赖）
_local_selfcorr_calculator = None
_selfcorr_init_lock = threading.Lock()

# 加载环境变量
load_dotenv()

# 配置日志
logger = logging.getLogger(__name__)

# API基础URL
API_BASE_URL = "https://api.worldquantbrain.com/"

# ─────────────────────────────────────────────────────────
# 全局单例：整个进程共享同一个已认证的 Session，避免多线程
# 同时触发大量认证请求导致服务器强制断开连接（10054）
# ─────────────────────────────────────────────────────────
_global_session = None
_global_session_lock = threading.Lock()
_session_init_flag = threading.Event()   # 初始化完成标志
_last_refresh_time: float = 0.0          # 上次刷新时间戳（防抖用）
_MIN_REFRESH_INTERVAL = 30.0            # 最短刷新间隔（秒），防止多线程同时刷新


def _make_session_with_retry() -> requests.Session:
    """创建带 HTTPAdapter 重试的 Session（连接级自动重试）"""
    session = requests.Session()
    # urllib3 层重试：连接失败、读超时、502/503/504 自动重试
    retry_policy = Retry(
        total=5,
        backoff_factor=1.0,          # 重试间隔 = backoff_factor * (2 ** (retry-1))
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PATCH", "DELETE"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_policy,
                          pool_connections=4,
                          pool_maxsize=16)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _get_or_create_global_session(force_new: bool = False) -> requests.Session:
    """
    获取或创建全局共享 Session（线程安全单例）。
    force_new=True 时强制重新认证（用于 refresh）。
    """
    global _global_session
    username = os.environ.get('WQ_USERNAME')
    password = os.environ.get('WQ_PASSWORD')

    if not username or not password:
        raise ValueError("请在环境变量中设置 WQ_USERNAME 和 WQ_PASSWORD")

    with _global_session_lock:
        if _global_session is not None and not force_new:
            return _global_session

        # 带指数退避的认证重试（最多 5 次）
        last_exc = None
        for attempt in range(1, 6):
            try:
                session = _make_session_with_retry()
                session.auth = (username, password)
                resp = session.post(
                    f"{API_BASE_URL}authentication",
                    timeout=30
                )
                if resp.status_code not in (200, 201):
                    raise Exception(f"认证失败: HTTP {resp.status_code}")
                _global_session = session
                logger.info("WorldQuant API 全局会话初始化成功")
                _session_init_flag.set()
                return _global_session
            except Exception as exc:
                last_exc = exc
                wait = min(5 * (2 ** (attempt - 1)), 60) + random.uniform(0, 3)
                logger.warning(
                    f"认证失败（第 {attempt}/5 次），{wait:.1f}s 后重试: {exc}"
                )
                time.sleep(wait)

        logger.error(f"初始化WorldQuant API会话失败: {last_exc}")
        raise last_exc


def _get_selfcorr_calculator(session):
    """获取或初始化全局本地自相关性计算器（线程安全）"""
    global _local_selfcorr_calculator
    if _local_selfcorr_calculator is not None:
        return _local_selfcorr_calculator
    with _selfcorr_init_lock:
        if _local_selfcorr_calculator is not None:
            return _local_selfcorr_calculator
        try:
            from local_selfcorr import LocalSelfCorrCalculator
            _local_selfcorr_calculator = LocalSelfCorrCalculator(session)
            logger.info("本地自相关性计算器已初始化")
        except Exception as e:
            logger.warning("初始化本地自相关性计算器失败: %s", e)
    return _local_selfcorr_calculator


class WqApiSimple:
    """WorldQuant API的简化封装类"""

    # 添加类变量
    API_BASE_URL = API_BASE_URL

    def __init__(self, max_retry=3):
        """初始化API客户端"""
        self.max_retry = max_retry
        # 使用全局共享 Session，避免多实例并发认证
        self.session = _get_or_create_global_session()

    def initialize(self):
        """初始化/重新创建会话（兼容旧调用）"""
        self.session = _get_or_create_global_session(force_new=True)
        logger.info("WorldQuant API会话初始化成功")

    def refresh_session(self):
        """
        刷新会话（防抖 + 线程安全）。
        若 _MIN_REFRESH_INTERVAL 秒内已刷新过，则直接复用现有 Session，
        避免多个线程同时触发重复认证。
        """
        global _last_refresh_time
        now = time.time()

        # 快速路径：未到刷新间隔，直接复用
        with _global_session_lock:
            if now - _last_refresh_time < _MIN_REFRESH_INTERVAL and _global_session is not None:
                logger.debug("会话刷新防抖：距上次刷新不足 30s，复用现有会话")
                self.session = _global_session
                return True
            # 标记刷新时间（锁内更新，防止其他线程再进入）
            _last_refresh_time = now

        try:
            self.session = _get_or_create_global_session(force_new=True)
            logger.info("WorldQuant API会话刷新成功")
            return True
        except Exception as e:
            logger.error(f"刷新会话失败: {e}")
            return False

    def _retry_operation(self, func, *args, **kwargs):
        """
        带重试机制的操作执行。
        针对 ConnectionResetError / 10054 使用更长的退避时间，
        并加入随机抖动（jitter）避免多线程同时重试（雪崩效应）。
        """
        retry_count = 0
        last_exc = None

        while retry_count <= self.max_retry:
            try:
                result = func(*args, **kwargs)

                # 处理 429 Too Many Requests
                if hasattr(result, 'status_code') and result.status_code == 429:
                    retry_count += 1
                    if retry_count <= self.max_retry:
                        # 优先使用服务器返回的 Retry-After 头指定的等待时间
                        retry_after_val = None
                        if hasattr(result, 'headers'):
                            ra_str = result.headers.get('Retry-After')
                            if ra_str:
                                try:
                                    retry_after_val = float(ra_str)
                                except (ValueError, TypeError):
                                    pass
                        if retry_after_val is not None and retry_after_val > 0:
                            wait_time = retry_after_val + random.uniform(0, 2)
                            logger.warning(
                                f"请求过于频繁(429)，服务器要求等待 {retry_after_val:.0f}s，"
                                f"实际等待 {wait_time:.1f}s ({retry_count}/{self.max_retry})"
                            )
                        else:
                            wait_time = min(10 * (2 ** (retry_count - 1)), 120) + random.uniform(0, 5)
                            logger.warning(
                                f"请求过于频繁(429)，将在 {wait_time:.1f}s 后重试 "
                                f"({retry_count}/{self.max_retry})"
                            )
                        time.sleep(wait_time)
                    else:
                        logger.error("请求过于频繁(429)，已达到最大重试次数")
                        return result
                else:
                    return result

            except (ConnectionResetError, ConnectionError,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.ChunkedEncodingError) as e:
                # 连接级错误：较长退避 + 刷新 Session
                retry_count += 1
                last_exc = e
                if retry_count <= self.max_retry:
                    wait_time = min(10 * (2 ** (retry_count - 1)), 120) + random.uniform(1, 6)
                    logger.warning(
                        f"连接被重置，将在 {wait_time:.1f}s 后刷新会话并重试 "
                        f"({retry_count}/{self.max_retry}): {e}"
                    )
                    time.sleep(wait_time)
                    self.refresh_session()
                else:
                    logger.error(f"连接错误，已达到最大重试次数: {e}")
                    raise

            except Exception as e:
                retry_count += 1
                last_exc = e
                if retry_count <= self.max_retry:
                    wait_time = min(5 * (2 ** (retry_count - 1)), 60) + random.uniform(0, 3)
                    logger.warning(
                        f"操作失败，将在 {wait_time:.1f}s 后重试 "
                        f"({retry_count}/{self.max_retry}): {e}"
                    )
                    time.sleep(wait_time)
                    self.refresh_session()
                else:
                    logger.error(f"操作失败，已达到最大重试次数: {e}")
                    raise

        if last_exc:
            raise last_exc
        raise RuntimeError("_retry_operation: 未知状态导致退出循环")

    def get_alphas(self, limit=100, offset=0, filters=None):
        """获取Alpha列表"""
        url = f"{API_BASE_URL}users/self/alphas"

        params = {
            "limit": limit,
            "offset": offset,
        }

        # 添加过滤条件
        if filters:
            params.update(filters)

        try:
            response = self._retry_operation(
                lambda: self.session.get(url, params=params)
            )

            if response.status_code != 200:
                logger.error(f"获取Alpha列表失败: {response.status_code}")
                return []

            data = response.json()
            return data.get("results", [])
        except Exception as e:
            logger.error(f"获取Alpha列表时出错: {e}")
            return []

    def submit_simulation(self, alpha_expression, settings=None, thread_name=None, alpha_id=None, max_wait_time=None, stall_limit=None):
        """提交Alpha回测
        
        参数:
        - alpha_expression: Alpha表达式
        - settings: 回测设置
        - thread_name: 线程名称（可选），用于日志显示
        - alpha_id: 数据库Alpha ID（可选），用于日志显示
        - max_wait_time: 最大等待时间（秒），默认3600
        - stall_limit: 进度停滞阈值（秒），默认300
        """
        thread_prefix = f"[{thread_name}] " if thread_name else ""
        alpha_prefix = f"Alpha ID: {alpha_id} " if alpha_id is not None else ""
        if max_wait_time is None:
            max_wait_time = 3600  # 最大等待时间60分钟，EUR+RAM中性化回测较慢
        if stall_limit is None:
            stall_limit = 300  # 进度长时间不动（5分钟）则视为卡住
        
        if settings is None:
            settings = {
                "instrumentType": "EQUITY",
                "region": "EUR",
                "universe": "TOPCS1600",
                "delay": 1,
                "decay": 0,
                "neutralization": "SUBINDUSTRY",
                "truncation": 0.08,
                "pasteurization": "ON",
                "unitHandling": "VERIFY",
                "nanHandling": "ON",
                "language": "FASTEXPR",
                "visualization": False
            }

        url = f"{API_BASE_URL}simulations"

        simulation_data = {
            'type': 'REGULAR',
            'settings': settings,
            'regular': alpha_expression
        }
        

        try:
            response = self._retry_operation(
                lambda: self.session.post(url, json=simulation_data)
            )
            if response.status_code == 401:
                logger.warning(f"会话超时,重新登录: {response.status_code}, 响应: {response.text}")
                self.refresh_session()

            if response.status_code != 201:
                logger.error(f"提交回测失败: {response.status_code}, 响应: {response.text}")
                return False, None

            sim_progress_url = response.headers.get('Location')
            if not sim_progress_url:
                logger.error("回测请求没有返回Location头")
                return False, None

            # 等待回测结果
            wait_count = 0
            total_wait_time = 0
            last_progress = 0
            last_progress_time = time.time()
            sim_progress_resp = None  # 保存最后一次响应

            while True:
                # 检查是否超过最大等待时间
                if total_wait_time >= max_wait_time:
                    # ====== 超时诊断：打印所有可用信息 ======
                    logger.warning(
                        f"{thread_prefix}[TIMEOUT] 回测等待超过 {max_wait_time}s，"
                        f"当前进度={last_progress}%，总等待={total_wait_time:.1f}s"
                    )
                    logger.warning(f"{thread_prefix}[TIMEOUT] 进度URL: {sim_progress_url}")
                    logger.warning(f"{thread_prefix}[TIMEOUT] 表达式: {alpha_expression[:200]}")
                    logger.warning(f"{thread_prefix}[TIMEOUT] Settings: {settings}")
                    if sim_progress_resp is not None:
                        try:
                            logger.warning(f"{thread_prefix}[TIMEOUT] 响应状态码: {sim_progress_resp.status_code}")
                            logger.warning(f"{thread_prefix}[TIMEOUT] 响应头: {dict(sim_progress_resp.headers)}")
                            body = sim_progress_resp.json()
                            logger.warning(f"{thread_prefix}[TIMEOUT] 响应体: {body}")
                            # 尝试分析原因
                            status_field = body.get('status', '未知')
                            progress_field = body.get('progress', 0)
                            logger.warning(f"{thread_prefix}[TIMEOUT] 模拟状态={status_field}, 进度={progress_field}%")
                            if progress_field < 1:
                                logger.warning(f"{thread_prefix}[TIMEOUT] 分析: 进度接近0%，可能原因: "
                                               "1)服务器队列拥堵 2)表达式语法问题 3)数据字段不存在 4)并发过高被限速")
                            elif progress_field < 50:
                                logger.warning(f"{thread_prefix}[TIMEOUT] 分析: 进度{progress_field}%，表达式计算慢，"
                                               "建议减少并发数或简化表达式")
                        except Exception as diag_err:
                            logger.warning(f"{thread_prefix}[TIMEOUT] 无法解析响应体: {diag_err}")
                    # 超时后再尝试一次，看服务器是否已完成
                    logger.info(f"{thread_prefix}[TIMEOUT] 最后尝试获取结果...")
                    try:
                        final_resp = self._retry_operation(
                            lambda: self.session.get(sim_progress_url)
                        )
                        if final_resp.status_code == 200:
                            final_ra = float(final_resp.headers.get("Retry-After", 0))
                            if final_ra == 0:
                                logger.info(f"{thread_prefix}[TIMEOUT] 服务器已完成！Retry-After=0，使用最终结果")
                                sim_progress_resp = final_resp
                                break
                            else:
                                logger.warning(f"{thread_prefix}[TIMEOUT] 服务器仍未完成，Retry-After={final_ra}s，放弃")
                    except Exception:
                        pass
                    break

                sim_progress_resp = self._retry_operation(
                    lambda: self.session.get(sim_progress_url)
                )

                if sim_progress_resp.status_code == 200:
                    retry_after_sec = float(sim_progress_resp.headers.get("Retry-After", 0))
                    if retry_after_sec > 0:
                        time.sleep(retry_after_sec)
                        total_wait_time += retry_after_sec
                    else:
                        # Retry-After 为 0 表示回测完成
                        break
                    data = sim_progress_resp.json()
                    progress = data.get('progress', 0)

                    # 检测进度停滞：5分钟内进度没有变化
                    if progress > last_progress:
                        last_progress = progress
                        last_progress_time = time.time()
                    elif time.time() - last_progress_time > stall_limit:
                        logger.warning(
                            f"{thread_prefix}[STALL] 进度 {progress}% 已停滞 {stall_limit}s，"
                            f"响应头: {dict(sim_progress_resp.headers)}, 响应体: {data}"
                        )
                        last_progress_time = time.time()  # 重置，避免重复打印

                    if progress >= 100:
                        break
                    # 只打印回测进度，不打印具体表达式
                    logger.info(
                        f"{thread_prefix}{alpha_prefix}回测中 ({total_wait_time}s): 预计{retry_after_sec}s后完成, 进度{progress}%"
                    )
                    wait_count += 1
                elif sim_progress_resp.status_code == 429:
                    # 处理限流（Retry-After）- 轮询时被限流，按指定时间等待后继续
                    retry_after = sim_progress_resp.headers.get('Retry-After')
                    if retry_after:
                        wait_sec = float(retry_after)
                        logger.warning(f"{thread_prefix}进度轮询触发限流(429)，等待 {wait_sec:.0f}s 后重试")
                        time.sleep(wait_sec)
                        total_wait_time += wait_sec
                    else:
                        wait_sec = 30 + random.uniform(0, 5)
                        logger.warning(f"{thread_prefix}进度轮询触发限流(429)，等待 {wait_sec:.1f}s 后重试")
                        time.sleep(wait_sec)
                        total_wait_time += wait_sec
                    continue
                else:
                    logger.error(
                        f"{thread_prefix}检查回测进度失败: {sim_progress_resp.status_code}, "
                        f"响应头: {dict(sim_progress_resp.headers)}, 响应体: {sim_progress_resp.text[:500]}"
                    )
                    return False, None

            # 提取Alpha ID
            if sim_progress_resp is None:
                logger.error(f"{thread_prefix}未收到任何进度响应")
                return False, None
            try:
                result_data = sim_progress_resp.json()
            except Exception:
                logger.error(f"{thread_prefix}无法解析最终响应体: {sim_progress_resp.text[:500]}")
                return False, None
            alpha_id = result_data.get("alpha")
            if not alpha_id:
                logger.error(
                    f"{thread_prefix}未能获取Alpha ID，响应体: {result_data}, "
                    f"total_wait_time={total_wait_time:.1f}s, progress={last_progress}%"
                )
                return False, None

            return True, alpha_id
        except Exception as e:
            logger.error(f"提交回测时出错: {e}")
            self.refresh_session()
            return False, None

    def get_alpha_details(self, alpha_id):
        """获取Alpha详情"""
        url = f"{API_BASE_URL}alphas/{alpha_id}"

        try:
            response = self._retry_operation(
                lambda: self.session.get(url)
            )

            if response.status_code != 200:
                logger.error(f"获取Alpha详情失败: {response.status_code}")
                return {}

            return response.json()
        except Exception as e:
            logger.error(f"获取Alpha详情时出错: {e}")
            return {}

    def get_alpha_check(self, alpha_id):
        """获取Alpha检查结果"""
        url = f"{API_BASE_URL}alphas/{alpha_id}/check"

        try:
            response = self._retry_operation(
                lambda: self.session.get(url)
            )

            if response.status_code != 200:
                logger.error(f"获取Alpha检查结果失败: {response.status_code}, response: {response.text}")
                return {}

            try:
                return response.json()
            except Exception as e:
                logger.error(f"解析JSON失败: {e}, response text: {response.text[:200]}")
                return {}
        except Exception as e:
            logger.error(f"获取Alpha检查结果时出错: {e}")
            return {}

    def set_alpha_color(self, alpha_id, color):
        """设置Alpha颜色"""
        url = f"{API_BASE_URL}alphas/{alpha_id}"

        try:
            response = self._retry_operation(
                lambda: self.session.patch(url, json={"color": color})
            )

            if response.status_code != 200:
                logger.error(f"设置Alpha颜色失败: {response.status_code}")
                return False

            logger.info(f"成功将Alpha {alpha_id} 的颜色设置为 {color}")
            return True
        except Exception as e:
            logger.error(f"设置Alpha颜色时出错: {e}")
            return False

    def check_alpha_status(self, alpha_id, sharpe_threshold=1.5):
        """检查Alpha状态并设置颜色"""
        try:
            # 获取检查结果
            check_result = self.get_alpha_check(alpha_id)
            
            # 如果检查结果为空或无效，直接返回
            if not check_result or not check_result.get("is"):
                logger.warning(f"Alpha {alpha_id} 检查结果无效，跳过颜色设置")
                return False, None

            # 检查是否有失败项
            checks = check_result.get("is", {}).get("checks", [])
            for check in checks:
                if check.get("result") == "FAIL":
                    logger.info(f"Alpha {alpha_id} 检查失败: {check.get('name')}")
                    self.set_alpha_color(alpha_id, "YELLOW")
                    return False, "YELLOW"

            # 只有Sharpe >= 1.5 且 Fitness >= 1 才设置蓝色
            is_data = check_result.get("is", {})
            sharpe = is_data.get("sharpe", 0)
            fitness = is_data.get("fitness", 0)
            if sharpe < 1.5 or fitness < 1.0:
                logger.info(f"Alpha {alpha_id} Sharpe {sharpe} < 1.5 或 Fitness {fitness} < 1.0，不设置蓝色")
                return False, None
            
            # 设置为蓝色
            self.set_alpha_color(alpha_id, "BLUE")
            logger.info(f"Alpha {alpha_id} 已设置为蓝色")

            # 获取自相关性
            self_corr = None
            for check in checks:
                if check.get("name") == "SELF_CORRELATION":
                    self_corr = check.get("value")
                    break

            # 如果平台未返回自相关性，尝试本地计算
            if self_corr is None:
                self_corr = self.local_calc_self_corr(alpha_id)
                if self_corr is not None:
                    logger.info(f"Alpha {alpha_id} 本地计算自相关性: {self_corr:.4f}")

            # 根据自相关性设置颜色
            color = "BLUE"  # 默认蓝色
            if self_corr is not None and self_corr <= 0.7:
                self.set_alpha_color(alpha_id, "GREEN")
                logger.info(f"Alpha {alpha_id} 自相关性为 {self_corr}，设置为绿色")
                color = "GREEN"

            return True, color, self_corr
        except Exception as e:
            logger.error(f"检查Alpha状态时出错: {e}")
            return False, None, None

    def local_calc_self_corr(self, alpha_id, region=None):
        """使用本地方法计算自相关性（与平台结果0误差）
        
        Args:
            alpha_id: 平台 Alpha ID
            region: alpha 所属区域，不传则自动获取
        
        Returns:
            自相关性值 (float)，失败返回 None
        """
        try:
            calc = _get_selfcorr_calculator(self.session)
            if calc is None:
                return None
            return calc.calc_self_corr(alpha_id, region=region)
        except Exception as e:
            logger.debug("本地计算自相关性失败: %s", e)
            return None

    def local_calc_both_corr(self, alpha_id, region=None):
        """本地计算 self-corr 和 PPAC-corr
        
        Returns:
            (self_corr, ppac_corr) 或失败返回 (None, None)
        """
        try:
            calc = _get_selfcorr_calculator(self.session)
            if calc is None:
                return None, None
            return calc.calc_both_corr(alpha_id, region=region)
        except Exception as e:
            logger.debug("本地计算相关性失败: %s", e)
            return None, None

    def init_local_selfcorr(self):
        """初始化本地自相关性数据（下载OS alpha PnL）。
        在挖掘开始前调用一次，之后的 local_calc_self_corr 即可快速计算。
        """
        try:
            calc = _get_selfcorr_calculator(self.session)
            if calc:
                calc.download_data(flag_increment=True)
                logger.info("本地自相关性数据已更新")
                return True
        except Exception as e:
            logger.warning("下载本地自相关性数据失败: %s", e)
        return False

    def run_backtest(self, alpha_expression, settings=None, thread_name=None, alpha_id=None, max_wait_time=None, stall_limit=None):
        """运行Alpha回测并等待完成
        
        参数:
        - alpha_expression: Alpha表达式
        - settings: 回测设置
        - thread_name: 线程名称（可选），用于日志显示
        - alpha_id: 数据库Alpha ID（可选），用于日志显示
        - max_wait_time: 最大等待时间（秒），默认3600
        - stall_limit: 进度停滞阈值（秒），默认300
        """
        thread_prefix = f"[{thread_name}] " if thread_name else ""
        # alpha_id 参数是可选的数据库ID，如果没有传则为空
        db_alpha_id = alpha_id  # 保存传入的数据库Alpha ID
        try:
            # 只打印回测开始信息，不打印具体表达式
            logger.info(f"{thread_prefix}开始对Alpha进行回测...")

            # 提交回测请求
            success, platform_alpha_id = self.submit_simulation(alpha_expression, settings, thread_name=thread_name, alpha_id=alpha_id, max_wait_time=max_wait_time, stall_limit=stall_limit)
            if not success or not platform_alpha_id:
                return None

            details = self.get_alpha_details(platform_alpha_id)
            status = details.get('status')

            # 检查颜色
            color = None
            is_data = details.get('is', {})
            # 确保 sharpe 和 fitness 是数字类型
            try:
                sharpe = float(is_data.get('sharpe', 0)) if is_data.get('sharpe') is not None else 0
                fitness = float(is_data.get('fitness', 0)) if is_data.get('fitness') is not None else 0
            except (ValueError, TypeError):
                sharpe = 0
                fitness = 0
                logger.warning(f"{thread_prefix}无法解析sharpe或fitness值")

            if sharpe >= 1.5 and fitness >= 1.0:
                checks_ok, color, self_corr = self.check_alpha_status(platform_alpha_id)
            else:
                # 即使 sharpe < 1.5，也尝试本地计算自相关性（用于快速筛选）
                self_corr = self.local_calc_self_corr(platform_alpha_id)
                if self_corr is not None:
                    logger.info(f"{thread_prefix}[{platform_alpha_id}] 本地自相关性: {self_corr:.4f}")

            # 处理结果
            result = {
                'id': db_alpha_id,
                'expression': alpha_expression,
                'status': status,
                'sharpe': is_data.get('sharpe'),
                'turnover': is_data.get('turnover'),
                'fitness': is_data.get('fitness'),
                'drawdown': is_data.get('drawdown'),
                'color': color,
                'self_corr': self_corr,
                'platform_id': platform_alpha_id
            }

            logger.info(f"{thread_prefix}[{platform_alpha_id}] 处理完成，Alpha状态: {status}, 颜色: {color}, 自相关性: {self_corr}，夏普比率: {sharpe}, 健身值: {fitness}")
            return result

        except Exception as e:
            logger.error(f"回测过程中出错: {e}")
            return None


def get_api():
    """获取API封装实例"""
    return WqApiSimple()
