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
def run(config, from_stage, to_stage, force, state_file):
    """运行Pipeline"""
    try:
        logger.info("启动Pipeline...")

        engine = PipelineEngine(
            config_path=config,
            state_file=state_file
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


def main():
    """CLI入口点"""
    pipeline_cli()


if __name__ == '__main__':
    main()
