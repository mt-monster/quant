"""
Pipeline状态管理模块

提供断点续传功能，每个阶段完成后保存状态。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class StageState:
    """单个阶段的状态"""
    name: str
    status: str = "pending"  # pending, running, completed, failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    input_count: int = 0
    output_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "input_count": self.input_count,
            "output_count": self.output_count,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StageState":
        return cls(
            name=data["name"],
            status=data.get("status", "pending"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            input_count=data.get("input_count", 0),
            output_count=data.get("output_count", 0),
            metadata=data.get("metadata", {})
        )


@dataclass
class PipelineState:
    """
    Pipeline状态管理类

    用于保存和恢复Pipeline执行状态，支持断点续传。
    """
    pipeline_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    current_stage: Optional[str] = None
    stages: Dict[str, StageState] = field(default_factory=dict)
    global_metadata: Dict[str, Any] = field(default_factory=dict)

    # 状态文件路径
    STATE_FILE: str = field(default=".pipeline_state.json", repr=False)

    def __post_init__(self):
        """初始化后设置状态文件路径"""
        if not hasattr(self, '_state_file_path'):
            self._state_file_path = Path(self.STATE_FILE)

    def mark_stage_started(self, stage_name: str, input_count: int = 0):
        """标记阶段开始"""
        now = datetime.now().isoformat()
        if stage_name not in self.stages:
            self.stages[stage_name] = StageState(name=stage_name)

        self.stages[stage_name].status = "running"
        self.stages[stage_name].started_at = now
        self.stages[stage_name].input_count = input_count
        self.current_stage = stage_name
        self.updated_at = now
        self.save()
        logger.info(f"阶段 {stage_name} 开始，输入数量: {input_count}")

    def mark_stage_completed(self, stage_name: str, output_count: int = 0, metadata: Dict[str, Any] = None):
        """标记阶段完成"""
        now = datetime.now().isoformat()
        if stage_name not in self.stages:
            self.stages[stage_name] = StageState(name=stage_name)

        self.stages[stage_name].status = "completed"
        self.stages[stage_name].completed_at = now
        self.stages[stage_name].output_count = output_count
        if metadata:
            self.stages[stage_name].metadata.update(metadata)

        self.updated_at = now
        self.save()
        logger.info(f"阶段 {stage_name} 完成，输出数量: {output_count}")

    def mark_stage_failed(self, stage_name: str, error: str = None):
        """标记阶段失败"""
        now = datetime.now().isoformat()
        if stage_name not in self.stages:
            self.stages[stage_name] = StageState(name=stage_name)

        self.stages[stage_name].status = "failed"
        self.stages[stage_name].completed_at = now
        if error:
            self.stages[stage_name].metadata["error"] = error

        self.updated_at = now
        self.save()
        logger.error(f"阶段 {stage_name} 失败: {error}")

    def is_stage_completed(self, stage_name: str) -> bool:
        """检查阶段是否已完成"""
        if stage_name not in self.stages:
            return False
        return self.stages[stage_name].status == "completed"

    def get_stage_state(self, stage_name: str) -> Optional[StageState]:
        """获取阶段状态"""
        return self.stages.get(stage_name)

    def set_state_file(self, filepath: str):
        """设置状态文件路径"""
        self._state_file_path = Path(filepath)

    def save(self):
        """保存状态到文件"""
        try:
            state_dict = {
                "pipeline_id": self.pipeline_id,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "current_stage": self.current_stage,
                "stages": {name: stage.to_dict() for name, stage in self.stages.items()},
                "global_metadata": self.global_metadata
            }

            with open(self._state_file_path, "w", encoding="utf-8") as f:
                json.dump(state_dict, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"保存状态文件失败: {e}")

    @classmethod
    def load(cls, filepath: str = None) -> Optional["PipelineState"]:
        """从文件加载状态"""
        filepath = filepath or ".pipeline_state.json"
        path = Path(filepath)

        if not path.exists():
            logger.info(f"状态文件不存在: {filepath}，创建新状态")
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            state = cls(
                pipeline_id=data["pipeline_id"],
                created_at=data["created_at"],
                updated_at=data["updated_at"],
                current_stage=data.get("current_stage"),
                stages={name: StageState.from_dict(s) for name, s in data.get("stages", {}).items()},
                global_metadata=data.get("global_metadata", {})
            )
            state._state_file_path = path

            logger.info(f"成功加载状态文件: {filepath}")
            return state

        except Exception as e:
            logger.error(f"加载状态文件失败: {e}")
            return None

    def reset(self):
        """重置所有状态"""
        self.stages.clear()
        self.current_stage = None
        self.updated_at = datetime.now().isoformat()
        self.global_metadata.clear()
        self.save()
        logger.info("Pipeline状态已重置")

    def get_summary(self) -> str:
        """获取状态摘要"""
        lines = [
            f"Pipeline ID: {self.pipeline_id}",
            f"创建时间: {self.created_at}",
            f"更新时间: {self.updated_at}",
            f"当前阶段: {self.current_stage or '无'}",
            "\n阶段状态:"
        ]

        for name, stage in self.stages.items():
            lines.append(f"  {name}: {stage.status}")
            if stage.input_count > 0:
                lines.append(f"    输入: {stage.input_count}, 输出: {stage.output_count}")
            if stage.started_at:
                lines.append(f"    开始: {stage.started_at}")
            if stage.completed_at:
                lines.append(f"    完成: {stage.completed_at}")

        return "\n".join(lines)

    def get_last_completed_stage(self) -> Optional[str]:
        """获取最后一个完成的阶段"""
        completed = [
            (name, stage.completed_at)
            for name, stage in self.stages.items()
            if stage.status == "completed" and stage.completed_at
        ]

        if not completed:
            return None

        # 按完成时间排序
        completed.sort(key=lambda x: x[1], reverse=True)
        return completed[0][0]

    def get_next_stage(self, stage_order: List[str]) -> Optional[str]:
        """
        获取下一个待执行的阶段

        参数:
        - stage_order: 阶段顺序列表

        返回:
        - 下一个待执行的阶段名称，如果全部完成则返回None
        """
        for stage_name in stage_order:
            if not self.is_stage_completed(stage_name):
                return stage_name
        return None
