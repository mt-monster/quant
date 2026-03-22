#!/usr/bin/env python3
"""
Alpha Self and PPAC Correlation Calculator Skill
Calculates self-correlation and PPAC correlation for WorldQuant BRAIN alphas.
"""

import subprocess
import pkg_resources
import sys
import requests
import pandas as pd
import logging
import time
import pickle
from collections import defaultdict
import numpy as np
from tqdm import tqdm
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import argparse
from datetime import datetime
from typing import Optional, Tuple, Dict, List, Union
from requests import Response

# Default parameters
DEFAULT_START_DATE = "01-10"
DEFAULT_END_DATE = "01-11"
DEFAULT_SHARPE_THRESHOLD = -1.0
DEFAULT_FITNESS_THRESHOLD = -1.0
DEFAULT_REGION = "IND"
DEFAULT_ALPHA_NUM = 100
DEFAULT_MAX_WORKERS = 5

# Required packages
REQUIRED_PACKAGES = [
    "requests>=2.32.0",
    "pandas>=2.0.0",
    "numpy>=1.24.0",
    "tqdm>=4.65.0"
]

def check_and_install_requirements():
    """检查并安装必要的Python包"""
    missing_packages = []

    for package in REQUIRED_PACKAGES:
        # 解析包名和版本要求
        if '>=' in package:
            pkg_name, min_version = package.split('>=')
        else:
            pkg_name = package
            min_version = None

        try:
            # 检查包是否已安装
            installed_version = pkg_resources.get_distribution(pkg_name).version
            if min_version:
                # 检查版本是否满足要求
                if pkg_resources.parse_version(installed_version) < pkg_resources.parse_version(min_version):
                    missing_packages.append(package)
        except pkg_resources.DistributionNotFound:
            missing_packages.append(package)
        except Exception:
            missing_packages.append(package)

    if missing_packages:
        print(f"发现 {len(missing_packages)} 个缺失或版本过低的包:")
        for pkg in missing_packages:
            print(f"  - {pkg}")

        # 询问用户是否安装
        response = input("\n是否自动安装缺失的包? (y/n): ").strip().lower()
        if response == 'y':
            print("正在安装缺失的包...")
            for pkg in missing_packages:
                try:
                    print(f"安装 {pkg}...")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
                except subprocess.CalledProcessError as e:
                    print(f"安装 {pkg} 失败: {e}")
                    return False
            print("所有包安装完成!")
            return True
        else:
            print("请手动安装缺失的包:")
            print(f"pip install {' '.join(missing_packages)}")
            return False
    else:
        # 所有包都已安装，不显示任何消息以减少token使用
        return True

# ===== 登录函数 =====
def sign_in(username, password):
    s = requests.Session()
    s.auth = (username, password)
    try:
        response = s.post('https://api.worldquantbrain.com/authentication')
        response.raise_for_status()
        logging.info("Successfully signed in")
        return s
    except requests.exceptions.RequestException as e:
        logging.error(f"Login failed: {e}")
        return None

# ===== 第一个算法的函数 =====
def get_submit_alphas(session, start_date, end_date, sharpe_th, fitness_th, region, alpha_num, tag=None):
    """获取可以提交的Alpha信息"""
    output = []  # 用于存储符合条件的Alpha记录
    count = 0  # 用于统计处理的Alpha数量

    # Get current year for date filtering
    current_year = datetime.now().year

    # 分页获取数据，每次获取100条
    for i in range(0, alpha_num, 100):
        print(f"处理偏移量: {i}")
        # 构造API请求URL
        base_url = f"https://api.worldquantbrain.com/users/self/alphas?limit=100&offset={i}&status=UNSUBMITTED%1FIS_FAIL&dateCreated%3E={current_year}-{start_date}T00:00:00-05:00&dateCreated%3C={current_year}-{end_date}T00:00:00-05:00&is.fitness%3E={fitness_th}&is.sharpe%3E={sharpe_th}&settings.region={region}&order=-is.sharpe&hidden=false&type!=SUPER"
        # 添加标签筛选条件
        if tag:
            base_url += f"&tags={tag}"
        url = base_url

        try:
            response = session.get(url)  # 发送GET请求
            if response.status_code == 200:  # 如果请求成功
                alpha_list = response.json().get("results", [])  # 获取返回的Alpha列表
                for alpha in alpha_list:
                    # 提取Alpha的各项信息
                    alpha_id = alpha.get("id")
                    name = alpha.get("name")
                    dateCreated = alpha.get("dateCreated")
                    sharpe = alpha.get("is", {}).get("sharpe")
                    fitness = alpha.get("is", {}).get("fitness")
                    turnover = alpha.get("is", {}).get("turnover")
                    margin = alpha.get("is", {}).get("margin")
                    longCount = alpha.get("is", {}).get("longCount")
                    shortCount = alpha.get("is", {}).get("shortCount")
                    decay = alpha.get("settings", {}).get("decay")
                    exp = alpha.get("regular", {}).get("code")

                    # 新增：提取中性化设置
                    neutralization = alpha.get("settings", {}).get("neutralization", "NONE")
                    # 将中性化代码转换为可读名称
                    neutralization_map = {
                        "SUBINDUSTRY": "Subindustry",
                        "STATISTICAL": "Statistical",
                        "SLOW": "Slow Factors",
                        "SLOW_AND_FAST": "Slow + Fast Factors",
                        "SECTOR": "Sector",
                        "NONE": "None",
                        "MARKET": "Market",
                        "INDUSTRY": "Industry",
                        "FAST": "Fast Factors",
                        "CROWDING": "Crowding Factors",
                        "COUNTRY": "Country/Region"
                    }
                    neutralization_name = neutralization_map.get(neutralization, neutralization)

                    count += 1  # 增加处理计数

                    # 检查是否可以通过检查
                    checks = alpha.get("is", {}).get("checks", [])
                    checks_df = pd.DataFrame(checks)
                    check_status = "Check FAIL"  # 默认检查状态为失败

                    # 如果存在检查项
                    if not checks_df.empty:
                        if "result" in checks_df.columns:
                            # 如果所有检查项都通过且longCount + shortCount > 100，则标记为Check OK
                            if not any(checks_df["result"].eq("FAIL")) and ((longCount or 0) + (shortCount or 0) > 100):
                                check_status = "Check OK"

                    # 构造记录字典
                    rec = {
                        "alpha_id": alpha_id,
                        "check_status": check_status,
                        "sharpe": sharpe,
                        "turnover": f"{turnover:.2%}" if turnover is not None else None,
                        "fitness": fitness,
                        "margin": f"{margin * 10000:.2f}‱" if margin is not None else None,  # 转换为万分比显示
                        "longCount": longCount,
                        "shortCount": shortCount,
                        "dateCreated": dateCreated,
                        "decay": decay,
                        "exp": exp,
                        "neutralization": neutralization,  # 添加中性化代码
                        "neutralization_name": neutralization_name  # 添加中性化可读名称
                    }

                    # 只有标记为 "Check OK" 的记录才会被保存到输出列表中
                    if check_status == "Check OK":
                        output.append(rec)
            else:
                # 如果请求失败，打印错误信息并尝试重新登录
                print(f"请求失败，状态码: {response.status_code}")
                print(f"响应内容: {response.text}")
        except Exception as e:
            # 捕获异常并打印错误信息
            print(f"处理偏移量 {i} 时出错: {e}")

    print(f"总计处理 Alpha 数量: {count}")  # 打印处理总数
    print(f"符合条件的 Alpha 数量: {len(output)}")
    return output

# ===== 基于夏普比率的排名函数 =====
def rank_alphas_by_sharpe(alpha_data):
    """根据夏普比率对Alpha进行排名"""
    if not alpha_data:
        print("没有符合条件的Alpha数据，无法进行排名")
        return pd.DataFrame()

    df = pd.DataFrame(alpha_data)
    # 按照夏普比率降序排序
    df = df.sort_values(by='sharpe', ascending=False)
    # 添加排名列
    df['Rank'] = range(1, len(df) + 1)

    # 重新排列列顺序
    columns_order = ["exp", "check_status", "alpha_id", "Rank", "sharpe", "turnover",
                     "fitness", "margin", "dateCreated", "longCount", "shortCount", "decay",
                     "neutralization", "neutralization_name"]
    df = df[columns_order]
    return df

# ===== 第二个算法的函数 =====
def save_obj(obj: object, name: str) -> None:
    with open(name + '.pickle', 'wb') as f:
        pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)

def load_obj(name: str) -> object:
    with open(name + '.pickle', 'rb') as f:
        return pickle.load(f)

def wait_get(session, url: str, max_retries: int = 10) -> "Response":
    retries = 0
    while retries < max_retries:
        while True:
            simulation_progress = session.get(url)
            if simulation_progress.headers.get("Retry-After", 0) == 0:
                break
            time.sleep(float(simulation_progress.headers["Retry-After"]))
        if simulation_progress.status_code < 400:
            break
        else:
            time.sleep(2 ** retries)
            retries += 1
    return simulation_progress

def _get_alpha_pnl(session, alpha_id: str) -> pd.DataFrame:
    pnl = wait_get(session, "https://api.worldquantbrain.com/alphas/" + alpha_id + "/recordsets/pnl").json()
    df = pd.DataFrame(pnl['records'], columns=[item['name'] for item in pnl['schema']['properties']])
    df = df.rename(columns={'date': 'Date', 'pnl': alpha_id})
    df = df[['Date', alpha_id]]
    return df

def get_alpha_pnls(session,
                   alphas: list[dict],
                   alpha_pnls: Optional[pd.DataFrame] = None,
                   alpha_ids: Optional[dict[str, list]] = None) -> Tuple[dict[str, list], pd.DataFrame]:
    if alpha_ids is None:
        alpha_ids = defaultdict(list)
    if alpha_pnls is None:
        alpha_pnls = pd.DataFrame()

    new_alphas = [item for item in alphas if item['id'] not in alpha_pnls.columns]
    if not new_alphas:
        return alpha_ids, alpha_pnls

    for item_alpha in new_alphas:
        alpha_ids[item_alpha['settings']['region']].append(item_alpha['id'])

    fetch_pnl_func = lambda alpha_id: _get_alpha_pnl(session, alpha_id).set_index('Date')
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_pnl_func, [item['id'] for item in new_alphas])
        alpha_pnls = pd.concat([alpha_pnls] + list(results), axis=1)
    alpha_pnls.sort_index(inplace=True)
    return alpha_ids, alpha_pnls

def get_os_alphas(session, limit: int = 100, get_first: bool = False) -> List[Dict]:
    fetched_alphas = []
    offset = 0
    retries = 0
    total_alphas = 100
    while len(fetched_alphas) < total_alphas:
        print(f"Fetching alphas from offset {offset} to {offset + limit}")
        url = f"https://api.worldquantbrain.com/users/self/alphas?stage=OS&limit={limit}&offset={offset}&order=-dateSubmitted"
        res = wait_get(session, url).json()
        if offset == 0:
            total_alphas = res['count']
        alphas = res["results"]
        fetched_alphas.extend(alphas)
        if len(alphas) < limit:
            break
        offset += limit
        if get_first:
            break
    return fetched_alphas[:total_alphas]

def calc_self_corr(session,
                   alpha_id: str,
                   os_alpha_rets: pd.DataFrame | None = None,
                   os_alpha_ids: dict[str, str] | None = None,
                   alpha_result: dict | None = None,
                   return_alpha_pnls: bool = False,
                   alpha_pnls: pd.DataFrame | None = None) -> float | tuple[float, pd.DataFrame]:
    if alpha_result is None:
        alpha_result = wait_get(session, f"https://api.worldquantbrain.com/alphas/{alpha_id}").json()
    if alpha_pnls is not None:
        if len(alpha_pnls) == 0:
            alpha_pnls = None
    if alpha_pnls is None:
        _, alpha_pnls = get_alpha_pnls(session, [alpha_result])
    alpha_pnls = alpha_pnls[alpha_id]
    alpha_rets = alpha_pnls - alpha_pnls.ffill().shift(1)
    alpha_rets = alpha_rets[pd.to_datetime(alpha_rets.index) > pd.to_datetime(alpha_rets.index).max() - pd.DateOffset(years=4)]
    self_corr = os_alpha_rets[os_alpha_ids[alpha_result['settings']['region']]].corrwith(alpha_rets).max()
    if np.isnan(self_corr):
        self_corr = 0
    return self_corr

def download_data(session, data_path: Path, flag_increment=True):
    if flag_increment:
        try:
            os_alpha_ids = load_obj(str(data_path / 'os_alpha_ids'))
            os_alpha_pnls = load_obj(str(data_path / 'os_alpha_pnls'))
            ppac_alpha_ids = load_obj(str(data_path / 'ppac_alpha_ids'))
            exist_alpha = [alpha for ids in os_alpha_ids.values() for alpha in ids]
            print("已加载缓存的Alpha数据")
        except (FileNotFoundError, EOFError, pickle.UnpicklingError) as e:
            # 首次运行或缓存文件损坏时的正常情况
            os_alpha_ids = None
            os_alpha_pnls = None
            exist_alpha = []
            ppac_alpha_ids = []
            if isinstance(e, FileNotFoundError):
                print("首次运行，正在下载基础数据...")
            else:
                print("缓存文件可能已损坏，重新下载数据...")
        except Exception as e:
            # 其他异常情况
            print(f"加载缓存数据时遇到问题，重新下载: {str(e)[:50]}...")
            os_alpha_ids = None
            os_alpha_pnls = None
            exist_alpha = []
            ppac_alpha_ids = []
    else:
        os_alpha_ids = None
        os_alpha_pnls = None
        exist_alpha = []
        ppac_alpha_ids = []

    if os_alpha_ids is None:
        print("正在下载OS Alpha数据（首次运行需要下载历史数据）...")
        alphas = get_os_alphas(session, limit=100, get_first=False)
    else:
        alphas = get_os_alphas(session, limit=30, get_first=True)

    alphas = [item for item in alphas if item['id'] not in exist_alpha]
    ppac_alpha_ids += [item['id'] for item in alphas for item_match in item['classifications'] if
                       item_match['name'] == 'Power Pool Alpha']

    os_alpha_ids, os_alpha_pnls = get_alpha_pnls(session, alphas, alpha_pnls=os_alpha_pnls, alpha_ids=os_alpha_ids)

    try:
        save_obj(os_alpha_ids, str(data_path / 'os_alpha_ids'))
        save_obj(os_alpha_pnls, str(data_path / 'os_alpha_pnls'))
        save_obj(ppac_alpha_ids, str(data_path / 'ppac_alpha_ids'))
        print(f'数据已保存到缓存文件')
    except Exception as e:
        print(f"保存缓存文件时遇到问题，但不影响本次运行: {str(e)[:50]}...")

    if alphas:
        print(f'新下载的alpha数量: {len(alphas)}, 目前总共alpha数量: {os_alpha_pnls.shape[1]}')
    else:
        print(f'没有新Alpha需要下载，使用现有缓存数据: {os_alpha_pnls.shape[1]}个Alpha')
    return os_alpha_ids, os_alpha_pnls

def load_data(data_path: Path, tag='PPAC'):
    try:
        os_alpha_ids = load_obj(str(data_path / 'os_alpha_ids'))
        os_alpha_pnls = load_obj(str(data_path / 'os_alpha_pnls'))
        ppac_alpha_ids = load_obj(str(data_path / 'ppac_alpha_ids'))

        # 检查数据是否有效
        if not os_alpha_ids or (hasattr(os_alpha_pnls, 'empty') and os_alpha_pnls.empty):
            raise ValueError("缓存文件为空或无效")

    except (FileNotFoundError, EOFError, pickle.UnpicklingError, ValueError) as e:
        print(f"无法加载缓存数据: {str(e)[:50]}...")
        # 返回空数据，调用者需要处理这种情况
        return {}, pd.DataFrame()
    except Exception as e:
        print(f"加载数据时遇到意外错误: {str(e)[:50]}...")
        return {}, pd.DataFrame()

    if tag == 'PPAC':
        for item in os_alpha_ids:
            os_alpha_ids[item] = [alpha for alpha in os_alpha_ids[item] if alpha in ppac_alpha_ids]
    elif tag == 'SelfCorr':
        for item in os_alpha_ids:
            os_alpha_ids[item] = [alpha for alpha in os_alpha_ids[item] if alpha not in ppac_alpha_ids]
    else:
        os_alpha_ids = os_alpha_ids

    exist_alpha = [alpha for ids in os_alpha_ids.values() for alpha in ids]
    if not exist_alpha:
        print("警告: 没有找到符合条件的Alpha数据")
        return os_alpha_ids, pd.DataFrame()

    os_alpha_pnls = os_alpha_pnls[exist_alpha]
    os_alpha_rets = os_alpha_pnls - os_alpha_pnls.ffill().shift(1)
    os_alpha_rets = os_alpha_rets[pd.to_datetime(os_alpha_rets.index) > pd.to_datetime(os_alpha_rets.index).max() - pd.DateOffset(years=4)]
    return os_alpha_ids, os_alpha_rets

# ===== 新增函数：计算PPAC自相关性 =====
def calculate_ppac_correlation_for_alphas(session, data_path, alpha_df, tag='PPAC',
                                          max_workers=5):
    """为Alpha列表计算PPAC自相关性"""
    # 下载并加载PPAC自相关性计算所需的基础数据
    print("\n下载PPAC自相关性计算所需的基础数据...")
    download_data(session, data_path, flag_increment=True)
    print("\n加载PPAC自相关性计算数据...")
    os_alpha_ids, os_alpha_rets = load_data(data_path, tag=tag)

    # 检查是否成功加载数据
    if os_alpha_rets.empty:
        print("警告: 无法加载足够的PPAC Alpha数据来计算相关性")
        print("首次运行可能需要等待数据下载完成，或当前区域可能没有足够的PPAC Alpha")
        # 返回原始DataFrame，没有PPAC相关性数据
        return alpha_df.copy()

    # 检查目标区域是否有数据
    target_region = alpha_df['alpha_id'].apply(
        lambda x: wait_get(session, f"https://api.worldquantbrain.com/alphas/{x}").json()['settings']['region']
    ).iloc[0] if not alpha_df.empty else None

    if target_region and target_region not in os_alpha_ids:
        print(f"警告: 没有找到区域 '{target_region}' 的PPAC Alpha数据")
        print("尝试下载完整数据以获取该区域的信息...")
        # 尝试强制下载完整数据
        download_data(session, data_path, flag_increment=False)
        # 重新加载数据
        os_alpha_ids, os_alpha_rets = load_data(data_path, tag=tag)

        # 检查重新加载的数据是否有效
        if os_alpha_rets.empty:
            print("警告: 重新加载数据后仍然无法获取足够的PPAC Alpha数据")
            return alpha_df.copy()

        # 再次检查
        if target_region not in os_alpha_ids:
            print(f"警告: 即使下载完整数据后，仍然没有找到区域 '{target_region}' 的PPAC Alpha数据")
            print("可能您在该区域没有PPAC Alpha，或者数据尚未同步")
            # 返回原始DataFrame，没有PPAC相关性数据
            return alpha_df.copy()

    # 为每个Alpha计算PPAC自相关性
    print(f"\n为 {len(alpha_df)} 个Alpha计算PPAC自相关性...")
    alpha_ids = alpha_df['alpha_id'].tolist()
    ppac_corr_results = []

    def process_alpha(alpha_id):
        try:
            ppac_corr = calc_self_corr(session=session,
                                       alpha_id=alpha_id,
                                       os_alpha_rets=os_alpha_rets,
                                       os_alpha_ids=os_alpha_ids)
            return alpha_id, ppac_corr
        except Exception as e:
            print(f"计算Alpha {alpha_id} PPAC自相关性失败: {e}")
            return alpha_id, None

    # 使用线程池并行处理
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_alpha, alpha_id) for alpha_id in alpha_ids]
        for future in tqdm(as_completed(futures), total=len(futures), desc="计算PPAC自相关性"):
            alpha_id, ppac_corr = future.result()
            if ppac_corr is not None:
                ppac_corr_results.append({"alpha_id": alpha_id, "ppac_correlation": ppac_corr})

    # 创建结果DataFrame
    if ppac_corr_results:
        ppac_corr_df = pd.DataFrame(ppac_corr_results)
        # 合并到原始DataFrame
        result_df = alpha_df.merge(ppac_corr_df, on='alpha_id', how='left')
    else:
        print("警告: 未能计算任何Alpha的PPAC相关性")
        result_df = alpha_df.copy()

    return result_df

# ===== 整合函数 =====
def calculate_self_correlation_for_alphas(session, data_path, alpha_df, tag='SelfCorr',
                                          max_workers=5):
    """为Alpha列表计算自相关性"""
    # 下载并加载自相关性计算所需的基础数据
    print("\n下载自相关性计算所需的基础数据...")
    download_data(session, data_path, flag_increment=True)
    print("\n加载自相关性计算数据...")
    os_alpha_ids, os_alpha_rets = load_data(data_path, tag=tag)

    # 检查是否成功加载数据
    if os_alpha_rets.empty:
        print("警告: 无法加载足够的OS Alpha数据来计算自相关性")
        print("首次运行可能需要等待数据下载完成，请稍后重试")
        # 返回原始DataFrame，没有相关性数据
        return alpha_df.copy()

    # 检查目标区域是否有数据
    target_region = alpha_df['alpha_id'].apply(
        lambda x: wait_get(session, f"https://api.worldquantbrain.com/alphas/{x}").json()['settings']['region']
    ).iloc[0] if not alpha_df.empty else None

    if target_region and target_region not in os_alpha_ids:
        print(f"警告: 没有找到区域 '{target_region}' 的OS Alpha数据")
        print("尝试下载完整数据以获取该区域的信息...")
        # 尝试强制下载完整数据
        download_data(session, data_path, flag_increment=False)
        # 重新加载数据
        os_alpha_ids, os_alpha_rets = load_data(data_path, tag=tag)

        # 检查重新加载的数据是否有效
        if os_alpha_rets.empty:
            print("警告: 重新加载数据后仍然无法获取足够的OS Alpha数据")
            return alpha_df.copy()

        # 再次检查
        if target_region not in os_alpha_ids:
            print(f"警告: 即使下载完整数据后，仍然没有找到区域 '{target_region}' 的OS Alpha数据")
            print("可能您在该区域没有OS Alpha，或者数据尚未同步")
            # 返回原始DataFrame，没有相关性数据
            return alpha_df.copy()

    # 为每个Alpha计算自相关性
    print(f"\n为 {len(alpha_df)} 个Alpha计算自相关性...")
    alpha_ids = alpha_df['alpha_id'].tolist()
    self_corr_results = []

    def process_alpha(alpha_id):
        try:
            self_corr = calc_self_corr(session=session,
                                       alpha_id=alpha_id,
                                       os_alpha_rets=os_alpha_rets,
                                       os_alpha_ids=os_alpha_ids)
            return alpha_id, self_corr
        except Exception as e:
            print(f"计算Alpha {alpha_id} 自相关性失败: {e}")
            return alpha_id, None

    # 使用线程池并行处理
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_alpha, alpha_id) for alpha_id in alpha_ids]
        for future in tqdm(as_completed(futures), total=len(futures), desc="计算自相关性"):
            alpha_id, self_corr = future.result()
            if self_corr is not None:
                self_corr_results.append({"alpha_id": alpha_id, "self_correlation": self_corr})

    # 创建结果DataFrame
    if self_corr_results:
        self_corr_df = pd.DataFrame(self_corr_results)
        # 合并到原始DataFrame
        result_df = alpha_df.merge(self_corr_df, on='alpha_id', how='left')
    else:
        print("警告: 未能计算任何Alpha的自相关性")
        result_df = alpha_df.copy()

    return result_df

# ===== 主函数 =====
def main():
    parser = argparse.ArgumentParser(description='Calculate alpha self-correlation and PPAC correlation')
    parser.add_argument('--start-date', default=DEFAULT_START_DATE, help='Start date in MM-DD format')
    parser.add_argument('--end-date', default=DEFAULT_END_DATE, help='End date in MM-DD format')
    parser.add_argument('--region', default=DEFAULT_REGION, help='Market region (e.g., IND, USA, EUR)')
    parser.add_argument('--sharpe-threshold', type=float, default=DEFAULT_SHARPE_THRESHOLD, help='Sharpe ratio threshold')
    parser.add_argument('--fitness-threshold', type=float, default=DEFAULT_FITNESS_THRESHOLD, help='Fitness threshold')
    parser.add_argument('--alpha-num', type=int, default=DEFAULT_ALPHA_NUM, help='Number of alphas to retrieve')
    parser.add_argument('--username', help='BRAIN platform email')
    parser.add_argument('--password', help='BRAIN platform password')
    parser.add_argument('--output', help='Output Excel file name (default: auto-generated)')
    parser.add_argument('--max-workers', type=int, default=DEFAULT_MAX_WORKERS, help='Maximum workers for correlation calculation')

    args = parser.parse_args()

    # 检查并安装必要的包
    if not check_and_install_requirements():
        print("缺少必要的依赖包，程序退出。")
        return 1

    # 配置参数
    class cfg:
        username = args.username or ""
        password = args.password or ""
        data_path = Path('.')

    # If no credentials provided, try to get from environment or config
    if not cfg.username or not cfg.password:
        # Try to get from environment variables
        cfg.username = os.environ.get('BRAIN_USERNAME', '')
        cfg.password = os.environ.get('BRAIN_PASSWORD', '')

    if not cfg.username or not cfg.password:
        print("错误: 需要提供用户名和密码")
        print("请通过 --username 和 --password 参数提供，或设置 BRAIN_USERNAME 和 BRAIN_PASSWORD 环境变量")
        return 1

    # 动态生成输出文件名
    if args.output:
        output_file = args.output
    else:
        output_file = f"alpha_results_{args.start_date}_{args.region}.xlsx"

    # 登录
    print("登录WorldQuant Brain...")
    session = sign_in(cfg.username, cfg.password)
    if not session:
        print("登录失败，请检查用户名和密码")
        return 1

    # 第一步：获取符合条件的Alpha
    print("\n获取符合条件的Alpha...")
    alpha_data = get_submit_alphas(session=session,
                                   start_date=args.start_date,
                                   end_date=args.end_date,
                                   sharpe_th=args.sharpe_threshold,
                                   fitness_th=args.fitness_threshold,
                                   region=args.region,
                                   alpha_num=args.alpha_num,
                                   )
    if not alpha_data:
        print("没有找到符合条件的Alpha")
        return 0

    # 第二步：基于夏普比率进行排名
    print("\n基于夏普比率进行排名...")
    alpha_df = rank_alphas_by_sharpe(alpha_data)
    if alpha_df.empty:
        print("没有找到符合条件的Alpha")
        return 0

    # 第三步：为这些Alpha计算普通自相关性
    result_df = calculate_self_correlation_for_alphas(session=session,
                                                      data_path=cfg.data_path,
                                                      alpha_df=alpha_df,
                                                      tag='SelfCorr',
                                                      max_workers=args.max_workers)

    # 第四步：为这些Alpha计算PPAC自相关性
    result_df = calculate_ppac_correlation_for_alphas(session=session,
                                                      data_path=cfg.data_path,
                                                      alpha_df=result_df,  # 使用上一步的结果
                                                      tag='PPAC',
                                                      max_workers=args.max_workers)

    # 第五步：保存结果到Excel
    # 选择需要输出的列
    output_columns = ["alpha_id", "exp", "check_status", "Rank", "sharpe",
                      "self_correlation", "ppac_correlation", "turnover", "fitness", "margin",
                      "dateCreated", "longCount", "shortCount", "decay",
                      "neutralization", "neutralization_name"]
    # 确保所有列都存在
    available_columns = [col for col in output_columns if col in result_df.columns]
    result_df = result_df[available_columns]

    # 保存到Excel
    with pd.ExcelWriter(output_file) as writer:
        result_df.to_excel(writer, sheet_name='Alpha Results', index=False)
    print(f"\n结果已保存到: {output_file}")

    # 打印前10个结果
    print("\n前10个Alpha的结果:")
    try:
        # 尝试正常打印
        print(result_df.head(10).to_string(index=False))
    except UnicodeEncodeError:
        # 编码问题，尝试使用替代方法
        print("注意: 由于编码问题，使用简化格式显示")
        # 创建一个简化的视图，避免特殊字符
        simple_df = result_df.head(10).copy()
        # 移除可能包含特殊字符的列
        if 'exp' in simple_df.columns:
            simple_df['exp'] = simple_df['exp'].apply(lambda x: str(x)[:50] + '...' if len(str(x)) > 50 else str(x))
        # 只打印部分列
        safe_columns = ['alpha_id', 'check_status', 'Rank', 'sharpe', 'self_correlation', 'ppac_correlation']
        available_columns = [col for col in safe_columns if col in simple_df.columns]
        if available_columns:
            print(simple_df[available_columns].to_string(index=False))
        else:
            print("无法显示结果，请查看生成的Excel文件")

    # 打印统计信息
    print("\n统计信息:")
    print(f"Alpha总数: {len(result_df)}")
    if 'self_correlation' in result_df.columns:
        print(f"平均自相关性: {result_df['self_correlation'].mean():.4f}")
        print(f"最大自相关性: {result_df['self_correlation'].max():.4f}")
        print(f"最小自相关性: {result_df['self_correlation'].min():.4f}")
    if 'ppac_correlation' in result_df.columns:
        print(f"平均PPAC自相关性: {result_df['ppac_correlation'].mean():.4f}")
        print(f"最大PPAC自相关性: {result_df['ppac_correlation'].max():.4f}")
        print(f"最小PPAC自相关性: {result_df['ppac_correlation'].min():.4f}")

    # 中性化设置分布统计
    if 'neutralization_name' in result_df.columns:
        print("\n中性化设置分布:")
        print(result_df['neutralization_name'].value_counts())

    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n操作被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n[错误] 程序运行出错: {str(e)}")
        print("\n可能的原因:")
        print("1. 网络连接问题")
        print("2. BRAIN API服务暂时不可用")
        print("3. 输入参数错误")
        print("4. 系统资源不足")
        print("\n建议:")
        print("1. 检查网络连接")
        print("2. 确认用户名和密码正确")
        print("3. 尝试减少 --alpha-num 参数的值")
        print("4. 稍后重试")
        print("\n详细错误信息:")
        import traceback
        traceback.print_exc()
        sys.exit(1)