import json
import logging
import os
from typing import Any, Dict, Iterable, List, Optional


logger = logging.getLogger(__name__)


def get_search_scope(
    instrument_type: str = "EQUITY",
    region: str = "USA",
    delay: int = 1,
    universe: str = "TOP3000",
) -> Dict[str, Any]:
    return {
        "instrumentType": instrument_type,
        "region": region,
        "delay": delay,
        "universe": universe,
    }


def fetch_dataset_fields(
    client,
    datasets: Iterable[str],
    search_scope: Dict[str, Any],
    cache_dir: Optional[str] = None,
    save_cache: bool = False,
) -> List[str]:
    all_fields: List[str] = []
    datasets = [dataset_id.strip() for dataset_id in datasets if dataset_id and dataset_id.strip()]

    for dataset_id in datasets:
        try:
            df = client.get_datafields(
                search_scope=search_scope,
                dataset_id=dataset_id,
                field_type="MATRIX",
            )
            if df.empty:
                logger.warning("数据集 %s 未返回字段", dataset_id)
                continue

            fields = df["id"].tolist()
            all_fields.extend(fields)
            logger.info("数据集 %s 获取 %s 个字段", dataset_id, len(fields))

            if save_cache and cache_dir:
                os.makedirs(cache_dir, exist_ok=True)
                region = search_scope.get("region", "USA")
                cache_path = os.path.join(cache_dir, f"{dataset_id}_{region}_datafields.json")
                with open(cache_path, "w", encoding="utf-8") as file:
                    json.dump(fields, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("获取数据集 %s 失败: %s", dataset_id, exc)

    return all_fields
