import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ==========================================
# 1. 页面基本配置与莫兰迪艺术色系 CSS 注入
# ==========================================
st.set_page_config(
    page_title="AlphaLens | 滚动持有穷尽式回测系统",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 注入高质感 UI 样式 (融合柔和灰调与微阴影卡片)
st.markdown("""
<style>
    /* 全局背景与字体平滑 */
    .stApp {
        background-color: #F4F5F6;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    /* 侧边栏调色 */
    [data-testid="stSidebar"] {
        background-color: #EAEBED;
        border-right: 1px solid #D1D5DB;
    }
    /* 自定义卡片样式 */
    .metric-card {
        background-color: #FFFFFF;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.02);
        border: 1px solid #E5E7EB;
        text-align: center;
        margin-bottom: 15px;
    }
    .metric-title {
        color: #6B7280;
        font-size: 14px;
        font-weight: 500;
        margin-bottom: 8px;
    }
    .metric-value {
        color: #374151;
        font-size: 28px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 2. 核心量化回测引擎
# ==========================================
@st.cache_data
def load_and_clean_data(file):
    """读取并清洗数据，确保按日期升序排列，支持 CSV 和 Excel 格式"""
    # 优化点：通过文件名后缀动态判断读取方式
    if file.name.endswith('.xlsx'):
        df = pd.read_excel(file)
    else:
        df = pd.read_csv(file)

    # 统一列名去掉可能存在的空格
    df.columns = df.columns.str.strip()
    df['净值日期'] = pd.to_datetime(df['净值日期'])
    df = df.sort_values('净值日期').reset_index(drop=True)
    return df


def run_backtest(df, start_date, end_date, months_list):
    """穷尽式滚动持有回测核心引擎"""
    # 筛选用户指定的历史采样区间
    mask = (df['净值日期'] >= pd.to_datetime(start_date)) & (df['净值日期'] <= pd.to_datetime(end_date))
    sub_df = df.loc[mask].copy().reset_index(drop=True)

    if len(sub_df) < 10:
        return None, "筛选区间内样本过少，请重新选择时间范围。"

    results = []
    all_details = {}

    # 将日期设为索引便于时间就近查找
    full_df_indexed = df.set_index('净值日期').sort_index()

    # 遍历每一种持有周期
    for m in months_list:
        days_delta = m * 30  # 以30天作为自然月的标准映射跨度
        returns = []

        # 穷尽每一个交易日作为买入点
        for i in range(len(sub_df)):
            buy_date = sub_df.loc[i, '净值日期']
            buy_nav = sub_df.loc[i, '单位净值']

            # 计算理论卖出日期
            target_sell_date = buy_date + pd.Timedelta(days=days_delta)

            # 如果理论卖出日超出了数据集的最后一天，则该买入点无效，结束该周期的穷尽
            if target_sell_date > full_df_indexed.index[-1]:
                break

            # 使用 get_indexer 的 'backfill' 寻找最近的下一个有效交易日
            idx = full_df_indexed.index.get_indexer([target_sell_date], method='backfill')[0]
            if idx == -1:
                continue

            sell_nav = full_df_indexed.iloc[idx]['单位净值']
            pnl_ratio = (sell_nav - buy_nav) / buy_nav
            returns.append(pnl_ratio)

        if len(returns) > 0:
            returns = np.array(returns)
            win_samples = returns[returns > 0]
            loss_samples = returns[returns < 0]

            # 指标计算
            win_ratio = len(win_samples) / len(returns)

            avg_win = np.mean(win_samples) if len(win_samples) > 0 else 0.0
            avg_loss = np.mean(loss_samples) if len(loss_samples) > 0 else 0.0
            odds = avg_win / abs(avg_loss) if avg_loss != 0 else np.nan

            # 新增优化点：根据期望值公式计算单个周期的期望收益率
            expected_value = abs(avg_loss) * (win_ratio * odds - (1 - win_ratio)) if avg_loss != 0 else np.mean(returns)
            buy_suggestion = "✅ 值得买入" if expected_value > 0 else "❌ 谨慎买入"

            # 局部优化：计算赢时最大收益与输时最大亏损
            max_win = np.max(win_samples) if len(win_samples) > 0 else 0.0
            max_loss = np.min(loss_samples) if len(loss_samples) > 0 else 0.0

            results.append({
                "持有周期": f"{m}个月",
                "总采样点数": int(len(returns)),
                "胜率": win_ratio,
                "赔率 (盈亏比)": odds,
                "期望收益率": expected_value,
                "买入建议": buy_suggestion,
                "平均收益率": np.mean(returns),
                "赢时最大收益": max_win,
                "输时最大亏损": max_loss
            })
            all_details[f"{m}个月"] = returns

    return pd.DataFrame(results), all_details


# ==========================================
# 3. Streamlit 页面布局与交互
# ==========================================
st.title("AlphaLens ｜ 滚动持有穷尽式回测")
st.caption("基于第一性原理，穷尽历史序列所有买入组合，测算任意持有周期的极限胜率与赔率分布。")
st.write("---")

# 侧边栏：文件上传与参数控制
with st.sidebar:
    st.subheader("⚙️ 配置文件与参数")
    # 优化点：修改 type 参数以支持同时上传 csv 和 xlsx 格式
    uploaded_file = st.file_uploader("上传历史净值 CSV 或 Excel 文件", type=["csv", "xlsx"])

    st.markdown("---")
    if uploaded_file is not None:
        # 预读取数据以获取日期边界
        init_df = load_and_clean_data(uploaded_file)
        min_d = init_df['净值日期'].min().to_pydatetime()
        max_d = init_df['净值日期'].max().to_pydatetime()

        # 日期区间选择器
        st.markdown("**1. 设定采样历史区间**")
        start_date = st.date_input("采样开始日期", min_d, min_value=min_d, max_value=max_d)
        end_date = st.date_input("采样结束日期", max_d, min_value=min_d, max_value=max_d)

        st.markdown("---")
        st.markdown("**2. 设定持有周期 (N个月)**")
        # 允许用户动态选择或自定义 N
        max_n = st.slider("自定义最大持有月数 (N)", min_value=6, max_value=60, value=12)
        base_months = [1, 2, 3, 4, 5]
        extended_months = list(range(6, max_n + 1))
        months_to_test = base_months + extended_months

        st.markdown("---")
        st.markdown("**3. 设定百分位分析时点**")
        # 允许用户手工选择特定日期进行历史百分位分析
        target_percentile_date = st.date_input("选择历史百分位测算日期", max_d, min_value=min_d, max_value=max_d)
    else:
        st.info("请先在上方上传 数据文件。")

# 主内容显示区
if uploaded_file is not None:
    df = load_and_clean_data(uploaded_file)

    # 执行回测计算
    res_df, details = run_backtest(df, start_date, end_date, months_to_test)

    if isinstance(res_df, pd.DataFrame) and not res_df.empty:

        # 计算全局汇总总指标（对所有穷尽样本统一求均值）
        total_samples = int(res_df['总采样点数'].sum())
        avg_win_ratio = res_df['胜率'].mean()
        avg_odds = res_df['赔率 (盈亏比)'].replace([np.inf, -np.inf], np.nan).dropna().mean()

        # 计算优化点：计算特定日期的历史百分位（以表格第一个数据为起点）
        origin_date = df['净值日期'].iloc[0]
        origin_date_str = origin_date.strftime('%Y-%m-%d')

        # 截取从历史起点到手工输入特定日期之间的数据流
        history_mask = (df['净值日期'] >= origin_date) & (df['净值日期'] <= pd.to_datetime(target_percentile_date))
        history_sub_df = df.loc[history_mask]

        if not history_sub_df.empty:
            target_nav = history_sub_df['单位净值'].iloc[-1]
            # 计算在该时间段内，低于或等于目标净值的样本占比即为历史百分位
            percentile_value = (history_sub_df['单位净值'] <= target_nav).mean() * 100
            percentile_display = f"{percentile_value:.2f}%"
        else:
            percentile_display = "N/A"

        # ==========================================
        # 4. 顶层大盘看板 (莫兰迪色系高管卡片，加入历史百分位布局)
        # ==========================================
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">📊 穷尽式回测总样本数</div>
                <div class="metric-value">{total_samples:,} 次</div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">📈 跨周期综合平均胜率</div>
                <div class="metric-value">{avg_win_ratio * 100:.2f}%</div>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">⚖️ 跨周期综合平均赔率</div>
                <div class="metric-value">{avg_odds:.2f}</div>
            </div>
            """, unsafe_allow_html=True)
        with col4:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">📅 历史百分位 (起点: {origin_date_str})</div>
                <div class="metric-value">{percentile_display}</div>
            </div>
            """, unsafe_allow_html=True)

        st.write("### 🔍 滚动持有期核心测算看板")

        # 数据美化呈现：针对银行及专业金融分析标准，格式化百分比与千分位
        formatted_df = res_df.copy()
        formatted_df['总采样点数'] = formatted_df['总采样点数'].apply(lambda x: f"{int(x):,}")
        formatted_df['胜率'] = formatted_df['胜率'].apply(lambda x: f"{x * 100:.2f}%")
        # 修复点：移除了 '赔率 (盈亏比).' 后面误输入的英文点号
        formatted_df['赔率 (盈亏比)'] = formatted_df['赔率 (盈亏比)'].apply(
            lambda x: f"{x:.2f}" if pd.notnull(x) else "N/A")
        formatted_df['期望收益率'] = formatted_df['期望收益率'].apply(lambda x: f"{x * 100:.2f}%")
        formatted_df['平均收益率'] = formatted_df['平均收益率'].apply(lambda x: f"{x * 100:.2f}%")

        # 局部优化：对新增的两个极限风险/收益指标进行格式化
        formatted_df['赢时最大收益'] = formatted_df['赢时最大收益'].apply(lambda x: f"{x * 100:.2f}%")
        formatted_df['输时最大亏损'] = formatted_df['输时最大亏损'].apply(lambda x: f"{x * 100:.2f}%")

        # 重整列顺序，展示业务关心的核心字段（局部优化：已将新增指标优雅地嵌入在核心风控维度中）
        display_cols = ["持有周期", "总采样点数", "胜率", "赔率 (盈亏比)", "期望收益率", "买入建议", "平均收益率",
                        "赢时最大收益", "输时最大亏损"]
        st.dataframe(formatted_df[display_cols], use_container_width=True, hide_index=True)

        # ==========================================
        # 5. 高级交互式可视化图表 (Plotly 双轴/多状态呈现)
        # ==========================================
        st.write("---")
        st.write("### 📊 胜率与赔率随持有周期的演变趋势")

        fig = go.Figure()

        # 莫兰迪色系：柔和蓝灰 (Win Ratio) 与 优雅冷灰 (Odds)
        fig.add_trace(go.Bar(
            x=res_df['持有周期'],
            y=res_df['胜率'] * 100,
            name='胜率 (%)',
            marker_color='#8E9AAF',
            opacity=0.85,
            yaxis='y1'
        ))

        fig.add_trace(go.Scatter(
            x=res_df['持有周期'],
            y=res_df['赔率 (盈亏比)'],
            name='赔率 (右轴)',
            mode='lines+markers',
            line=dict(color='#CBC0D3', width=3),
            marker=dict(size=8, color='#9A8C98'),
            yaxis='y2'
        ))

        # 样式极简精细化配置
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,0.9)",
            margin=dict(l=40, r=40, t=20, b=40),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(gridcolor="#ECEEF0", tickfont=dict(color="#6B7280")),
            yaxis=dict(
                title=dict(
                    text="胜率 (%)",
                    font=dict(color="#8E9AAF")
                ),
                gridcolor="#ECEEF0",
                tickfont=dict(color="#6B7280"),
                ticksuffix="%"
            ),
            yaxis2=dict(
                title=dict(
                    text="赔率 (盈亏比)",
                    font=dict(color="#9A8C98")
                ),
                anchor="x",
                overlaying="y",
                side="right",
                tickfont=dict(color="#6B7280"),
                showgrid=False
            )
        )

        st.plotly_chart(fig, use_container_width=True)

    else:
        st.error(details if details else "回测未能生成有效样本，请检查日期或输入数据。")
else:
    # 引导提示界面
    st.info("💡 提示：请在左侧侧边栏上传从系统导出的基金历史净值 CSV 或 Excel 文件开始自动演算。")
    st.markdown("""
    **期望的数据格式规范：**
    * 包含 `净值日期` 字段 (如：2026-05-29)
    * 包含 `单位净值` 字段 (如：1.9702)
    """)
