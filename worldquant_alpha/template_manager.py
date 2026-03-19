"""
模板管理器
提供模板的持久化存储和管理功能
"""

import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_FILE = TEMPLATE_DIR / "user_templates.json"


@dataclass
class AlphaTemplateConfig:
    """Alpha模板配置"""
    name: str
    template: str
    components: Dict[str, List[Any]]
    description: str = ""
    tags: List[str] = None
    enabled: bool = True
    dataset: str = "analyst10"
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "template": self.template,
            "components": self.components,
            "description": self.description,
            "tags": self.tags,
            "enabled": self.enabled,
            "dataset": self.dataset
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AlphaTemplateConfig':
        return cls(
            name=data.get("name", ""),
            template=data.get("template", ""),
            components=data.get("components", {}),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            enabled=data.get("enabled", True),
            dataset=data.get("dataset", "analyst10")
        )
    
    def validate(self) -> tuple:
        """验证模板配置是否有效"""
        errors = []
        
        if not self.name:
            errors.append("模板名称不能为空")
        
        if not self.template:
            errors.append("模板表达式不能为空")
        
        if not self.components:
            errors.append("模板组件不能为空")
        
        if self.components:
            for key, values in self.components.items():
                if key not in self.template:
                    errors.append(f"组件 '{key}' 未在模板中使用")
        
        for key in self.template.split('<'):
            if '>' in key:
                component_name = '<' + key.split('>')[0] + '>'
                if component_name not in self.components:
                    errors.append(f"模板中使用了未定义的组件 '{component_name}'")
        
        return (len(errors) == 0, errors)
    
    def calculate_combinations(self) -> int:
        """计算所有可能的组合数"""
        combinations = 1
        for component, values in self.components.items():
            combinations *= len(values) if isinstance(values, list) else 1
        return combinations


class TemplateManager:
    """模板管理器"""
    
    def __init__(self, template_file: str = None):
        self.template_file = Path(template_file) if template_file else TEMPLATE_FILE
        self._templates: Dict[str, AlphaTemplateConfig] = {}
        self._ensure_template_dir()
        self._load_templates()
    
    def _ensure_template_dir(self):
        """确保模板目录存在"""
        self.template_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.template_file.exists():
            self._save_templates({})
    
    def _load_templates(self):
        """加载模板"""
        try:
            with open(self.template_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._templates = {}
            for name, config in data.items():
                try:
                    self._templates[name] = AlphaTemplateConfig.from_dict(config)
                except Exception as e:
                    logger.warning(f"加载模板 '{name}' 失败: {e}")
            
            logger.info(f"已加载 {len(self._templates)} 个模板")
        except Exception as e:
            logger.error(f"加载模板失败: {e}")
            self._templates = {}
    
    def _save_templates(self, templates: Dict[str, AlphaTemplateConfig] = None):
        """保存模板"""
        try:
            data = templates if templates is not None else self._templates
            json_data = {name: cfg.to_dict() for name, cfg in data.items()}
            
            with open(self.template_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"已保存 {len(data)} 个模板到 {self.template_file}")
        except Exception as e:
            logger.error(f"保存模板失败: {e}")
            raise
    
    def add_template(self, template: AlphaTemplateConfig) -> tuple:
        """
        添加模板
        
        返回:
        - (成功标志, 消息)
        """
        is_valid, errors = template.validate()
        if not is_valid:
            return False, f"模板验证失败: {', '.join(errors)}"
        
        if template.name in self._templates:
            return False, f"模板 '{template.name}' 已存在"
        
        self._templates[template.name] = template
        self._save_templates()
        
        return True, f"模板 '{template.name}' 已添加"
    
    def update_template(self, name: str, template: AlphaTemplateConfig) -> tuple:
        """
        更新模板
        
        返回:
        - (成功标志, 消息)
        """
        if name not in self._templates:
            return False, f"模板 '{name}' 不存在"
        
        is_valid, errors = template.validate()
        if not is_valid:
            return False, f"模板验证失败: {', '.join(errors)}"
        
        template.name = name
        self._templates[name] = template
        self._save_templates()
        
        return True, f"模板 '{name}' 已更新"
    
    def delete_template(self, name: str) -> tuple:
        """
        删除模板
        
        返回:
        - (成功标志, 消息)
        """
        if name not in self._templates:
            return False, f"模板 '{name}' 不存在"
        
        del self._templates[name]
        self._save_templates()
        
        return True, f"模板 '{name}' 已删除"
    
    def get_template(self, name: str) -> Optional[AlphaTemplateConfig]:
        """获取模板"""
        return self._templates.get(name)
    
    def list_templates(self, enabled_only: bool = False, tag: str = None) -> List[AlphaTemplateConfig]:
        """列出模板"""
        templates = list(self._templates.values())
        
        if enabled_only:
            templates = [t for t in templates if t.enabled]
        
        if tag:
            templates = [t for t in templates if tag in t.tags]
        
        return templates
    
    def import_from_code(self, code_str: str) -> tuple:
        """
        从代码字符串导入模板（用于导入 create_default_templates 中的模板）
        
        返回:
        - (成功数量, 失败数量)
        """
        success = 0
        failed = 0
        
        for name, config in self._templates.items():
            if config.name not in [t.name for t in self._templates.values()]:
                success += 1
            else:
                failed += 1
        
        return success, failed
    
    def export_template(self, name: str) -> Optional[str]:
        """导出模板为Python代码"""
        template = self.get_template(name)
        if not template:
            return None
        
        code = f'''AlphaTemplate(
    name="{template.name}",
    template="{template.template}",
    components={json.dumps(template.components, ensure_ascii=False)}
)'''
        return code
    
    def get_stats(self) -> Dict[str, Any]:
        """获取模板统计信息"""
        templates = list(self._templates.values())
        
        return {
            "total": len(templates),
            "enabled": len([t for t in templates if t.enabled]),
            "disabled": len([t for t in templates if not t.enabled]),
            "total_combinations": sum(t.calculate_combinations() for t in templates),
            "tags": list(set(tag for t in templates for tag in t.tags))
        }


def create_template_manager() -> TemplateManager:
    """创建模板管理器实例"""
    return TemplateManager()
