import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CandidateDecision:
    checks_passed: bool
    candidate: bool
    sharpe: float
    fitness: float
    turnover: float
    self_corr: Optional[float]
    color: Optional[str]
    failed_checks: List[str]
    reason: str

    @property
    def candidate_status(self) -> str:
        return "candidate" if self.candidate else "tested"


@dataclass
class CandidateRule:
    sharpe_threshold: float = 1.5
    fitness_threshold: float = 1.0
    max_turnover: float = 0.5
    max_self_corr: float = 0.7
    require_green: bool = False
    use_local_selfcorr: bool = True  # 平台 self_corr 缺失时使用本地计算

    def evaluate(self, result: Dict[str, Any]) -> CandidateDecision:
        checks = result.get("checks") or []
        failed_checks = [
            check.get("name", "UNKNOWN")
            for check in checks
            if check.get("result") == "FAIL"
        ]
        checks_passed = not failed_checks

        sharpe = float(result.get("sharpe") or 0.0)
        fitness = float(result.get("fitness") or 0.0)
        turnover = abs(float(result.get("turnover") or 0.0))
        self_corr = result.get("self_corr")
        if self_corr is not None:
            self_corr = abs(float(self_corr))
        color = result.get("color")

        # 当平台未返回 self_corr 时，尝试本地计算（0误差方法）
        if self_corr is None and self.use_local_selfcorr:
            platform_id = result.get("platform_id") or result.get("platform_alpha_id")
            region = (result.get("settings") or {}).get("region")
            if platform_id:
                self_corr = self._try_local_selfcorr(platform_id, region)

        reasons: List[str] = []
        if not checks_passed:
            reasons.append(f"平台检查失败: {', '.join(failed_checks)}")
        if sharpe < self.sharpe_threshold:
            reasons.append(f"sharpe<{self.sharpe_threshold}")
        if fitness < self.fitness_threshold:
            reasons.append(f"fitness<{self.fitness_threshold}")
        if turnover > self.max_turnover:
            reasons.append(f"turnover>{self.max_turnover}")
        if self_corr is None:
            reasons.append("self_corr_missing")
        elif self_corr > self.max_self_corr:
            reasons.append(f"self_corr>{self.max_self_corr}")
        if self.require_green and color != "GREEN":
            reasons.append("color_not_green")

        return CandidateDecision(
            checks_passed=checks_passed,
            candidate=(len(reasons) == 0),
            sharpe=sharpe,
            fitness=fitness,
            turnover=turnover,
            self_corr=self_corr,
            color=color,
            failed_checks=failed_checks,
            reason="passed" if not reasons else "; ".join(reasons),
        )

    @staticmethod
    def _try_local_selfcorr(platform_id: str, region: Optional[str] = None) -> Optional[float]:
        """尝试使用本地方法计算 self-corr"""
        try:
            from local_selfcorr import get_selfcorr_calculator
            calc = get_selfcorr_calculator()
            sc = calc.calc_self_corr(platform_id, region=region)
            logger.debug("本地 self-corr(%s) = %.4f", platform_id, sc)
            return sc
        except Exception:
            return None


DEFAULT_CANDIDATE_RULE = CandidateRule()
