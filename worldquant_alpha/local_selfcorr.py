"""
本地0误差计算自相关性模块（即插即用版）

基于 WorldQuant BRAIN 社区帖子方法:
- 下载用户所有 OS 阶段 alpha 的 PnL 数据
- 本地计算新 alpha 与已有 alpha 的最大相关性（self-corr 和 PPAC）
- 结果与平台一致（0误差），无需等待平台 check 接口

用法:
    from local_selfcorr import LocalSelfCorrCalculator

    calc = LocalSelfCorrCalculator(session)
    calc.download_data()  # 首次使用需下载，之后增量更新

    # 计算单个 alpha 的 self-corr
    self_corr = calc.calc_self_corr(alpha_id, region="USA")
    ppac_corr = calc.calc_self_corr(alpha_id, region="USA", tag="PPAC")
"""

import logging
import os
import pickle
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 数据缓存默认目录
DEFAULT_DATA_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / ".selfcorr_cache"


class LocalSelfCorrCalculator:
    """本地自相关性计算器（与平台结果0误差）"""

    def __init__(self, session, data_path: Optional[Path] = None, max_workers: int = 10):
        """
        初始化计算器。

        Args:
            session: 已认证的 requests.Session（来自 wd_lib_wrapper）
            data_path: OS alpha 数据缓存目录，默认为 .selfcorr_cache/
            max_workers: 下载 PnL 时的并发线程数
        """
        self.session = session
        self.data_path = data_path or DEFAULT_DATA_DIR
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.max_workers = max_workers

        # 内存缓存（避免重复磁盘读取）
        self._os_alpha_ids: Optional[Dict[str, List[str]]] = None
        self._os_alpha_pnls: Optional[pd.DataFrame] = None
        self._ppac_alpha_ids: Optional[List[str]] = None
        self._os_alpha_rets_cache: Dict[str, pd.DataFrame] = {}  # tag -> rets

    # ── 序列化 ──────────────────────────────────────────

    @staticmethod
    def _save_obj(obj: object, path: str) -> None:
        with open(path + ".pickle", "wb") as f:
            pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def _load_obj(path: str) -> object:
        with open(path + ".pickle", "rb") as f:
            return pickle.load(f)

    # ── API 请求 ────────────────────────────────────────

    def _wait_get(self, url: str, max_retries: int = 10):
        """带 Retry-After 感知的 GET 请求"""
        retries = 0
        resp = None
        while retries < max_retries:
            while True:
                resp = self.session.get(url)
                retry_after = resp.headers.get("Retry-After", 0)
                if retry_after == 0 or retry_after == "0":
                    break
                time.sleep(float(retry_after))
            if resp.status_code < 400:
                break
            else:
                time.sleep(2 ** retries)
                retries += 1
        return resp

    def _get_alpha_pnl(self, alpha_id: str) -> pd.DataFrame:
        """获取单个 alpha 的 PnL 数据"""
        resp = self._wait_get(
            f"https://api.worldquantbrain.com/alphas/{alpha_id}/recordsets/pnl"
        )
        pnl = resp.json()
        df = pd.DataFrame(
            pnl["records"],
            columns=[item["name"] for item in pnl["schema"]["properties"]],
        )
        df = df.rename(columns={"date": "Date", "pnl": alpha_id})
        df = df[["Date", alpha_id]]
        return df

    # ── OS Alpha 获取 ──────────────────────────────────

    def _get_os_alphas(self, limit: int = 100, get_first: bool = False) -> List[Dict]:
        """获取 OS 阶段的所有已提交 alpha"""
        fetched = []
        offset = 0
        total = 100
        while len(fetched) < total:
            url = (
                f"https://api.worldquantbrain.com/users/self/alphas"
                f"?stage=OS&limit={limit}&offset={offset}&order=-dateSubmitted"
            )
            res = self._wait_get(url).json()
            if offset == 0:
                total = res.get("count", 0)
            alphas = res.get("results", [])
            fetched.extend(alphas)
            if len(alphas) < limit:
                break
            offset += limit
            if get_first:
                break
        return fetched[:total]

    def _get_alpha_pnls_batch(
        self,
        alphas: List[Dict],
        alpha_pnls: Optional[pd.DataFrame] = None,
        alpha_ids: Optional[Dict[str, List]] = None,
    ) -> Tuple[Dict[str, List], pd.DataFrame]:
        """批量获取 alpha PnL 数据，按 region 分类"""
        if alpha_ids is None:
            alpha_ids = defaultdict(list)
        if alpha_pnls is None:
            alpha_pnls = pd.DataFrame()

        new_alphas = [a for a in alphas if a["id"] not in alpha_pnls.columns]
        if not new_alphas:
            return alpha_ids, alpha_pnls

        for a in new_alphas:
            alpha_ids[a["settings"]["region"]].append(a["id"])

        fetch_fn = lambda aid: self._get_alpha_pnl(aid).set_index("Date")
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            results = list(executor.map(fetch_fn, [a["id"] for a in new_alphas]))

        alpha_pnls = pd.concat([alpha_pnls] + results, axis=1)
        alpha_pnls.sort_index(inplace=True)
        return alpha_ids, alpha_pnls

    # ── 数据下载与加载 ─────────────────────────────────

    def download_data(self, flag_increment: bool = True) -> None:
        """
        下载 OS alpha 数据并缓存到磁盘。

        Args:
            flag_increment: True=增量更新（只下载新alpha），False=全量重新下载
        """
        os_alpha_ids = None
        os_alpha_pnls = None
        exist_alpha: List[str] = []
        ppac_alpha_ids: List[str] = []

        if flag_increment:
            try:
                os_alpha_ids = self._load_obj(str(self.data_path / "os_alpha_ids"))
                os_alpha_pnls = self._load_obj(str(self.data_path / "os_alpha_pnls"))
                ppac_alpha_ids = self._load_obj(str(self.data_path / "ppac_alpha_ids"))
                exist_alpha = [a for ids in os_alpha_ids.values() for a in ids]
                logger.info("已加载缓存的 OS Alpha 数据")
            except FileNotFoundError:
                logger.info("首次运行，将下载全部 OS Alpha 数据…")
                os_alpha_ids = None
                os_alpha_pnls = None
            except Exception as e:
                logger.warning("加载缓存失败，重新下载: %s", e)
                os_alpha_ids = None
                os_alpha_pnls = None

        if os_alpha_ids is None:
            alphas = self._get_os_alphas(limit=100, get_first=False)
        else:
            alphas = self._get_os_alphas(limit=30, get_first=True)

        alphas = [a for a in alphas if a["id"] not in exist_alpha]
        ppac_alpha_ids += [
            a["id"]
            for a in alphas
            for cls in a.get("classifications", [])
            if cls.get("name") == "Power Pool Alpha"
        ]

        os_alpha_ids, os_alpha_pnls = self._get_alpha_pnls_batch(
            alphas, alpha_pnls=os_alpha_pnls, alpha_ids=os_alpha_ids
        )

        self._save_obj(os_alpha_ids, str(self.data_path / "os_alpha_ids"))
        self._save_obj(os_alpha_pnls, str(self.data_path / "os_alpha_pnls"))
        self._save_obj(ppac_alpha_ids, str(self.data_path / "ppac_alpha_ids"))

        # 更新内存缓存
        self._os_alpha_ids = os_alpha_ids
        self._os_alpha_pnls = os_alpha_pnls
        self._ppac_alpha_ids = ppac_alpha_ids
        self._os_alpha_rets_cache.clear()

        new_count = len(alphas)
        total_count = os_alpha_pnls.shape[1] if os_alpha_pnls is not None else 0
        logger.info("新下载 alpha 数量: %d, 总共: %d", new_count, total_count)

    def _ensure_data_loaded(self) -> None:
        """确保内存中已加载数据"""
        if self._os_alpha_ids is not None:
            return
        try:
            self._os_alpha_ids = self._load_obj(str(self.data_path / "os_alpha_ids"))
            self._os_alpha_pnls = self._load_obj(str(self.data_path / "os_alpha_pnls"))
            self._ppac_alpha_ids = self._load_obj(str(self.data_path / "ppac_alpha_ids"))
            logger.debug("从磁盘加载了 selfcorr 缓存数据")
        except FileNotFoundError:
            raise RuntimeError(
                "本地 selfcorr 缓存不存在，请先调用 download_data() 下载 OS Alpha 数据。"
            )

    def load_data(self, tag: Optional[str] = None) -> Tuple[Dict[str, List], pd.DataFrame]:
        """
        加载已缓存数据并计算收益率。

        Args:
            tag: 过滤标签
                 - "PPAC"：仅返回 PPAC 池中的 alpha
                 - "SelfCorr"：仅返回非 PPAC 的 alpha
                 - None：返回所有 alpha

        Returns:
            (alpha_ids_by_region, alpha_returns_df)
        """
        cache_key = tag or "__all__"
        if cache_key in self._os_alpha_rets_cache:
            # 返回缓存的 rets
            return self._filtered_ids(tag), self._os_alpha_rets_cache[cache_key]

        self._ensure_data_loaded()

        filtered_ids = self._filtered_ids(tag)
        exist_alpha = [a for ids in filtered_ids.values() for a in ids]

        if not exist_alpha:
            logger.warning("没有找到符合 tag=%s 的 alpha 数据", tag)
            return filtered_ids, pd.DataFrame()

        pnls = self._os_alpha_pnls[exist_alpha]
        rets = pnls - pnls.ffill().shift(1)
        # 只保留最近4年
        rets = rets[
            pd.to_datetime(rets.index)
            > pd.to_datetime(rets.index).max() - pd.DateOffset(years=4)
        ]
        self._os_alpha_rets_cache[cache_key] = rets
        return filtered_ids, rets

    def _filtered_ids(self, tag: Optional[str]) -> Dict[str, List]:
        """按 tag 过滤 alpha id"""
        self._ensure_data_loaded()
        import copy
        ids = copy.deepcopy(self._os_alpha_ids)
        ppac = set(self._ppac_alpha_ids or [])

        if tag == "PPAC":
            for region in ids:
                ids[region] = [a for a in ids[region] if a in ppac]
        elif tag == "SelfCorr":
            for region in ids:
                ids[region] = [a for a in ids[region] if a not in ppac]
        return ids

    # ── 核心计算 ────────────────────────────────────────

    def calc_self_corr(
        self,
        alpha_id: str,
        region: Optional[str] = None,
        tag: Optional[str] = None,
        alpha_pnls: Optional[pd.DataFrame] = None,
    ) -> float:
        """
        计算指定 alpha 与同 region 已有 OS alpha 的最大自相关性。

        Args:
            alpha_id: 目标 alpha ID
            region: alpha 所属 region（如 "USA"），不传则自动从平台获取
            tag: "PPAC" / "SelfCorr" / None
            alpha_pnls: 可选的预加载 PnL 数据（避免重复下载）

        Returns:
            最大自相关性值 (0~1)，无法计算时返回 0
        """
        os_alpha_ids, os_alpha_rets = self.load_data(tag=tag)

        if os_alpha_rets.empty:
            logger.warning("OS alpha 收益率数据为空，无法计算 self-corr")
            return 0.0

        # 获取 alpha 信息（主要是 region）
        if region is None:
            alpha_result = self._wait_get(
                f"https://api.worldquantbrain.com/alphas/{alpha_id}"
            ).json()
            region = alpha_result.get("settings", {}).get("region", "USA")

        if region not in os_alpha_ids or not os_alpha_ids[region]:
            logger.warning("region %s 无已有 OS alpha，self-corr 返回 0", region)
            return 0.0

        # 获取目标 alpha 的 PnL
        if alpha_pnls is None:
            try:
                pnl_df = self._get_alpha_pnl(alpha_id).set_index("Date")
                target_pnls = pnl_df[alpha_id]
            except Exception as e:
                logger.error("获取 alpha %s PnL 失败: %s", alpha_id, e)
                return 0.0
        else:
            if alpha_id in alpha_pnls.columns:
                target_pnls = alpha_pnls[alpha_id]
            else:
                target_pnls = alpha_pnls.iloc[:, 0] if not alpha_pnls.empty else None
            if target_pnls is None:
                return 0.0

        # 计算收益率
        alpha_rets = target_pnls - target_pnls.ffill().shift(1)
        alpha_rets = alpha_rets[
            pd.to_datetime(alpha_rets.index)
            > pd.to_datetime(alpha_rets.index).max() - pd.DateOffset(years=4)
        ]

        # 计算与同 region 所有 OS alpha 的相关系数，取最大值
        region_ids = os_alpha_ids[region]
        # 确保 region_ids 中的 alpha 都在 rets 中
        valid_ids = [aid for aid in region_ids if aid in os_alpha_rets.columns]
        if not valid_ids:
            return 0.0

        corr = os_alpha_rets[valid_ids].corrwith(alpha_rets)
        self_corr = corr.max()

        if np.isnan(self_corr):
            return 0.0

        return float(self_corr)

    def calc_both_corr(
        self,
        alpha_id: str,
        region: Optional[str] = None,
    ) -> Tuple[float, float]:
        """
        同时计算 self-corr（非PPAC）和 PPAC-corr。

        Returns:
            (self_corr, ppac_corr)
        """
        self_corr = self.calc_self_corr(alpha_id, region=region, tag="SelfCorr")
        ppac_corr = self.calc_self_corr(alpha_id, region=region, tag="PPAC")
        return self_corr, ppac_corr

    def is_corr_ok(
        self,
        alpha_id: str,
        region: Optional[str] = None,
        threshold: float = 0.7,
    ) -> Tuple[bool, float]:
        """
        快速判断 alpha 是否通过自相关性检查。

        Returns:
            (passed, max_self_corr)  passed=True 表示自相关性 <= threshold
        """
        self_corr = self.calc_self_corr(alpha_id, region=region, tag=None)
        return self_corr <= threshold, self_corr


# ── 便捷工厂函数（与项目全局 session 集成） ──────────────

_global_calculator: Optional[LocalSelfCorrCalculator] = None


def get_selfcorr_calculator(
    session=None, data_path: Optional[Path] = None
) -> LocalSelfCorrCalculator:
    """
    获取全局单例的 LocalSelfCorrCalculator。
    首次调用时需传入 session，之后可省略。
    """
    global _global_calculator
    if _global_calculator is None:
        if session is None:
            raise ValueError("首次调用 get_selfcorr_calculator 必须传入已认证的 session")
        _global_calculator = LocalSelfCorrCalculator(session, data_path=data_path)
    return _global_calculator


def ensure_selfcorr_data(session=None, data_path: Optional[Path] = None) -> LocalSelfCorrCalculator:
    """
    确保 selfcorr 数据已下载（增量更新），返回计算器实例。
    适合在挖掘脚本初始化时调用一次。
    """
    calc = get_selfcorr_calculator(session, data_path)
    calc.download_data(flag_increment=True)
    return calc
