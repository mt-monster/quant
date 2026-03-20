"""
Pipeline CLI模块

提供命令行接口。
"""

import click
import logging
import sys
from pathlib import Path

from .engine import PipelineEngine
from .config.loader import ConfigLoader

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@click.group()
def pipeline_cli():
    """三阶Alpha生成Pipeline命令行工具"""
    pass


@pipeline_cli.command()
@click.option('--config', '-c', default=None, help='配置文件名或路径')
@click.option('--from-stage', default=None, help='从指定阶段开始')
@click.option('--to-stage', default=None, help='执行到指定阶段结束')
@click.option('--force', is_flag=True, help='强制重新运行已完成的阶段')
@click.option('--state-file', default='.pipeline_state.json', help='状态文件路径')
@click.option('--first-order-limit', type=int, default=0, help='第一阶段生成Alpha数量限制，0表示不限制')
@click.option('--first-order-to-second-count', type=int, default=0, help='第一阶段到第二阶段的数量，0表示不限制')
@click.option('--first-order-to-second-ids', type=str, default='', help='第一阶段到第二阶段的指定Alpha ID')
@click.option('--second-order-to-third-count', type=int, default=0, help='第二阶段到第三阶段的数量，0表示不限制')
@click.option('--second-order-to-third-ids', type=str, default='', help='第二阶段到第三阶段的指定Alpha ID')
@click.option('--third-order-test-ids', type=str, default='', help='第三阶段测试的指定Alpha ID')
@click.option('--dataset', '-d', type=str, default=None, help='数据集ID（如 analyst14, fundamental6）')
@click.option('--region', '-r', type=str, default=None, help='地区（如 USA, EUR, CHN）')
@click.option('--universe', '-u', type=str, default=None, help='股票池（如 TOP3000, TOP2500, TOPCS1600）')
@click.option('--delay', type=int, default=None, help='延迟天数（1 或 0）')
@click.option('--instrument-type', type=str, default=None, help='工具类型（如 EQUITY, FUTURES）')
@click.option('--template-names', type=str, default='', help='模板名称（逗号分隔）')
@click.option('--operations', type=str, default='', help='操作符列表（逗号分隔）')
@click.option('--time-windows', type=str, default='', help='时间窗口（逗号分隔）')
def run(config, from_stage, to_stage, force, state_file,
        first_order_limit, first_order_to_second_count,
        first_order_to_second_ids, second_order_to_third_count,
        second_order_to_third_ids, third_order_test_ids,
        dataset, region, universe, delay, instrument_type,
        template_names, operations, time_windows):
    """运行Pipeline"""
    try:
        first_ids = [int(x.strip()) for x in first_order_to_second_ids.split(',') if x.strip()] if first_order_to_second_ids else []
        second_ids = [int(x.strip()) for x in second_order_to_third_ids.split(',') if x.strip()] if second_order_to_third_ids else []
        third_ids = [int(x.strip()) for x in third_order_test_ids.split(',') if x.strip()] if third_order_test_ids else []
        template_name_list = [x.strip() for x in template_names.split(',') if x.strip()] if template_names else None
        operations_list = [x.strip() for x in operations.split(',') if x.strip()] if operations else None
        time_windows_list = [int(x.strip()) for x in time_windows.split(',') if x.strip()] if time_windows else None

        logger.info("启动Pipeline...")

        engine = PipelineEngine(
            config_path=config,
            state_file=state_file,
            first_order_limit=first_order_limit,
            first_order_to_second_count=first_order_to_second_count,
            first_order_to_second_ids=first_ids,
            second_order_to_third_count=second_order_to_third_count,
            second_order_to_third_ids=second_ids,
            third_order_test_ids=third_ids,
            dataset=dataset,
            region=region,
            universe=universe,
            delay=delay,
            instrument_type=instrument_type,
            template_names=template_name_list,
            operations=operations_list,
            time_windows=time_windows_list
        )

        engine.run(
            start_stage=from_stage,
            end_stage=to_stage,
            force=force
        )

        click.echo("Pipeline执行完成!")

    except Exception as e:
        logger.exception("Pipeline执行失败")
        click.echo(f"错误: {e}", err=True)
        sys.exit(1)


@pipeline_cli.command()
@click.option('--state-file', default='.pipeline_state.json', help='状态文件路径')
def resume(state_file):
    """从上次中断处恢复执行"""
    try:
        logger.info("恢复Pipeline执行...")

        engine = PipelineEngine(state_file=state_file)
        engine.resume()

        click.echo("Pipeline恢复执行完成!")

    except Exception as e:
        logger.exception("Pipeline恢复失败")
        click.echo(f"错误: {e}", err=True)
        sys.exit(1)


@pipeline_cli.command()
@click.option('--state-file', default='.pipeline_state.json', help='状态文件路径')
def status(state_file):
    """查看Pipeline状态"""
    try:
        engine = PipelineEngine(state_file=state_file)
        summary = engine.status()
        click.echo(summary)

    except Exception as e:
        logger.exception("获取状态失败")
        click.echo(f"错误: {e}", err=True)
        sys.exit(1)


@pipeline_cli.command()
@click.option('--config', '-c', required=True, help='配置文件路径')
def validate(config):
    """验证配置文件"""
    try:
        loader = ConfigLoader()
        cfg = loader.load(config)

        click.echo(f"配置名称: {cfg.name}")
        click.echo(f"配置版本: {cfg.version}")
        click.echo(f"地区: {cfg.settings.region}")
        click.echo(f"Universe: {cfg.settings.universe}")
        click.echo(f"数据集: {', '.join(cfg.data.datasets)}")
        click.echo("\n阶段配置:")
        click.echo(f"  一阶生成: {'启用' if cfg.stages.first_order.enabled else '禁用'}")
        click.echo(f"  二阶生成: {'启用' if cfg.stages.second_order.enabled else '禁用'}")
        click.echo(f"  三阶生成: {'启用' if cfg.stages.third_order.enabled else '禁用'}")
        click.echo(f"\n回测模式: {cfg.backtest.mode.value}")
        click.echo(f"最大并发: {cfg.backtest.max_workers}")

        click.echo("\n配置验证通过!")

    except Exception as e:
        logger.exception("配置验证失败")
        click.echo(f"配置错误: {e}", err=True)
        sys.exit(1)


@pipeline_cli.command()
def list_configs():
    """列出可用配置"""
    try:
        loader = ConfigLoader()
        configs = loader.list_configs()

        if configs:
            click.echo("可用配置文件:")
            for cfg in configs:
                click.echo(f"  - {cfg}")
        else:
            click.echo("未找到配置文件")

    except Exception as e:
        logger.exception("列出配置失败")
        click.echo(f"错误: {e}", err=True)
        sys.exit(1)


@pipeline_cli.command()
@click.option('--state-file', default='.pipeline_state.json', help='状态文件路径')
@click.confirmation_option(prompt='确定要重置Pipeline状态吗?')
def reset(state_file):
    """重置Pipeline状态"""
    try:
        engine = PipelineEngine(state_file=state_file)
        engine.reset()
        click.echo("Pipeline状态已重置")

    except Exception as e:
        logger.exception("重置失败")
        click.echo(f"错误: {e}", err=True)
        sys.exit(1)


@click.group(name='template')
def template_cli():
    """Alpha模板管理"""
    pass


@template_cli.command(name='list')
@click.option('--enabled-only', is_flag=True, help='只显示启用的模板')
@click.option('--tag', type=str, default=None, help='按标签筛选')
@click.option('--dataset', type=str, default=None, help='数据集名称')
@click.option('--date', type=str, default=None, help='日期 (如 20260319)')
@click.option('--all-dates', is_flag=True, help='显示数据集所有日期的模板')
def template_list(enabled_only, tag, dataset, date, all_dates):
    """列出所有模板"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from template_manager import TemplateManager

        if all_dates and dataset:
            m = TemplateManager(dataset=dataset)
            dates = m.get_available_dates(dataset)
            click.echo(f"数据集 {dataset} 的所有日期: {dates}")
            for d in dates:
                tm = m.load_from_date(d)
                templates = tm.list_templates(enabled_only=enabled_only, tag=tag)
                click.echo(f"\n=== 日期 {d} ({len(templates)} 模板) ===")
                for t in templates:
                    status = "[ON]" if t.enabled else "[OFF]"
                    click.echo(f"  {status} {t.name}")
            return

        manager = TemplateManager(dataset=dataset, date=date)
        templates = manager.list_templates(enabled_only=enabled_only, tag=tag)

        if templates:
            click.echo(f"找到 {len(templates)} 个模板:")
            for t in templates:
                status = "[ON]" if t.enabled else "[OFF]"
                combinations = t.calculate_combinations()
                click.echo(f"\n{status} {t.name} (组合数: {combinations})")
                click.echo(f"   数据集: {t.dataset}")
                if t.description:
                    click.echo(f"   描述: {t.description}")
                if t.tags:
                    click.echo(f"   标签: {', '.join(t.tags)}")
                click.echo(f"   表达式: {t.template[:80]}...")
        else:
            click.echo("未找到模板")

        stats = manager.get_stats()
        click.echo(f"\n统计: 总数={stats['total']}, 启用={stats['enabled']}, 禁用={stats['disabled']}")

    except Exception as e:
        logger.exception("列出模板失败")
        click.echo(f"[FAIL] 错误: {e}", err=True)


@template_cli.command(name='add')
@click.option('--name', '-n', required=True, help='模板名称')
@click.option('--template', '-t', required=True, help='模板表达式（使用<component>作为占位符）')
@click.option('--components', '-c', required=True, help='组件JSON字符串')
@click.option('--description', '-d', default='', help='模板描述')
@click.option('--tags', default='', help='标签（逗号分隔）')
@click.option('--dataset', default='analyst10', help='数据集ID')
def template_add(name, template, components, description, tags, dataset):
    """添加新模板"""
    try:
        import json

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from template_manager import AlphaTemplateConfig, TemplateManager

        comp_dict = json.loads(components)
        tag_list = [t.strip() for t in tags.split(',') if t.strip()]

        template_config = AlphaTemplateConfig(
            name=name,
            template=template,
            components=comp_dict,
            description=description,
            tags=tag_list,
            dataset=dataset
        )

        manager = TemplateManager()
        success, msg = manager.add_template(template_config)

        if success:
            click.echo(f"[OK] {msg}")
        else:
            click.echo(f"[FAIL] {msg}", err=True)
            sys.exit(1)

    except json.JSONDecodeError as e:
        click.echo(f"[FAIL] JSON格式错误: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        logger.exception("添加模板失败")
        click.echo(f"[FAIL] 错误: {e}", err=True)
        sys.exit(1)


@template_cli.command(name='show')
@click.argument('name')
def template_show(name):
    """显示模板详情"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from template_manager import TemplateManager

        manager = TemplateManager()
        template_config = manager.get_template(name)

        if template_config:
            click.echo(f"模板名称: {template_config.name}")
            click.echo(f"状态: {'启用' if template_config.enabled else '禁用'}")
            click.echo(f"数据集: {template_config.dataset}")
            click.echo(f"描述: {template_config.description}")
            click.echo(f"标签: {', '.join(template_config.tags) if template_config.tags else '无'}")
            click.echo(f"\n表达式:")
            click.echo(f"  {template_config.template}")
            click.echo(f"\n组件:")
            for key, values in template_config.components.items():
                click.echo(f"  {key}: {values}")
            click.echo(f"\n可能组合数: {template_config.calculate_combinations()}")
        else:
            click.echo(f"[FAIL] 模板 '{name}' 不存在", err=True)
            sys.exit(1)

    except Exception as e:
        logger.exception("显示模板失败")
        click.echo(f"错误: {e}", err=True)


@template_cli.command(name='delete')
@click.argument('name')
@click.confirmation_option(prompt='确定要删除这个模板吗?')
def template_delete(name):
    """删除模板"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from template_manager import TemplateManager

        manager = TemplateManager()
        success, msg = manager.delete_template(name)

        if success:
            click.echo(f"[OK] {msg}")
        else:
            click.echo(f"[FAIL] {msg}", err=True)
            sys.exit(1)

    except Exception as e:
        logger.exception("删除模板失败")
        click.echo(f"[FAIL] 错误: {e}", err=True)


@template_cli.command(name='enable')
@click.argument('name')
def template_enable(name):
    """启用模板"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from template_manager import TemplateManager

        manager = TemplateManager()
        template_config = manager.get_template(name)

        if not template_config:
            click.echo(f"[FAIL] 模板 '{name}' 不存在", err=True)
            sys.exit(1)

        template_config.enabled = True
        success, msg = manager.update_template(name, template_config)

        if success:
            click.echo(f"[OK] 模板 '{name}' 已启用")
        else:
            click.echo(f"[FAIL] {msg}", err=True)
            sys.exit(1)

    except Exception as e:
        logger.exception("启用模板失败")
        click.echo(f"[FAIL] 错误: {e}", err=True)


@template_cli.command(name='disable')
@click.argument('name')
def template_disable(name):
    """禁用模板"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from template_manager import TemplateManager

        manager = TemplateManager()
        template_config = manager.get_template(name)

        if not template_config:
            click.echo(f"[FAIL] 模板 '{name}' 不存在", err=True)
            sys.exit(1)

        template_config.enabled = False
        success, msg = manager.update_template(name, template_config)

        if success:
            click.echo(f"[OK] 模板 '{name}' 已禁用")
        else:
            click.echo(f"[FAIL] {msg}", err=True)
            sys.exit(1)

    except Exception as e:
        logger.exception("禁用模板失败")
        click.echo(f"[FAIL] 错误: {e}", err=True)


@template_cli.command(name='export')
@click.argument('name')
def template_export(name):
    """导出模板为Python代码"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from template_manager import TemplateManager

        manager = TemplateManager()
        code = manager.export_template(name)

        if code:
            click.echo(code)
        else:
            click.echo(f"[FAIL] 模板 '{name}' 不存在", err=True)
            sys.exit(1)

    except Exception as e:
        logger.exception("导出模板失败")
        click.echo(f"[FAIL] 错误: {e}", err=True)


@template_cli.command(name='stats')
def template_stats():
    """显示模板统计信息"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from template_manager import TemplateManager

        manager = TemplateManager()
        stats = manager.get_stats()

        click.echo("模板统计:")
        click.echo(f"  总数: {stats['total']}")
        click.echo(f"  启用: {stats['enabled']}")
        click.echo(f"  禁用: {stats['disabled']}")
        click.echo(f"  总可能组合数: {stats['total_combinations']}")
        click.echo(f"  标签: {', '.join(stats['tags']) if stats['tags'] else '无'}")

    except Exception as e:
        logger.exception("获取统计失败")
        click.echo(f"[FAIL] 错误: {e}", err=True)


pipeline_cli.add_command(template_cli)


def main():
    """CLI入口点"""
    pipeline_cli()


if __name__ == '__main__':
    main()
