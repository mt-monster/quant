import logging
from typing import Dict, Optional

from .engine import PipelineEngine

try:
    from worldquant_alpha.database import get_session, list_pipeline_candidates
except ImportError:
    from database import get_session, list_pipeline_candidates


logger = logging.getLogger(__name__)


def run_submittable_candidate_pipeline(
    config_path: Optional[str] = None,
    datasets: Optional[list] = None,
    region: str = "USA",
    universe: str = "TOP3000",
    delay: int = 1,
    instrument_type: str = "EQUITY",
    first_order_limit: int = 200,
    template_names: Optional[list] = None,
    state_file: str = ".submittable_candidates_state.json",
    force: bool = False,
) -> Dict[str, int]:
    engine = PipelineEngine(
        config_path=config_path,
        state_file=state_file,
        first_order_limit=first_order_limit,
        dataset=(datasets[0] if datasets and len(datasets) == 1 else None),
        region=region,
        universe=universe,
        delay=delay,
        instrument_type=instrument_type,
        template_names=template_names,
    )

    if datasets and len(datasets) > 1:
        engine.config.data.datasets = datasets

    engine.config.settings.region = region
    engine.config.settings.universe = universe
    engine.config.settings.delay = delay
    engine.config.settings.instrument_type = instrument_type
    engine.config.data.search_scope.update({
        "instrumentType": instrument_type,
        "region": region,
        "delay": delay,
        "universe": universe,
    })

    # 子流程只做到可提交候选，不进入二阶/三阶扩展。
    engine.config.stages.second_order.enabled = False
    engine.config.stages.third_order.enabled = False
    engine.config.stages.first_order_filter.sharpe_threshold = 1.5
    engine.config.stages.first_order_filter.fitness_threshold = 1.0
    engine.config.stages.first_order_filter.max_turnover = 0.5

    engine.run(end_stage="first_order_filter", force=force)

    session = get_session()
    try:
        candidates = list_pipeline_candidates(
            session,
            candidate_status="candidate",
            stage="first_order",
            order=1,
        )
        tested = list_pipeline_candidates(
            session,
            candidate_status="tested",
            stage="first_order",
            order=1,
        )
        summary = {
            "candidate_count": len(candidates),
            "tested_count": len(tested),
        }
        logger.info("可提交候选流程完成: %s", summary)
        return summary
    finally:
        session.close()
