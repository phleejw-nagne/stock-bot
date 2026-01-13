import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots 
from kis_api import KisApi
from pykrx import stock 
import kakao_msg 
import time
import json
import os
import pandas as pd

# --- 페이지 설정 ---
st.set_page_config(layout="wide", page_title="스마트 주식 봇 Ver 6.2")

# ==========================================
# [데이터 저장/로드 기능] 
# ==========================================
DATA_FILE = "stock_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {"watchlist": ["005930"], "stock_names": {}}

def save_data():
    data = {
        "watchlist": st.session_state['watchlist'],
        "stock_names": st.session_state['stock_names']
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 세션 초기화 ---
saved_data = load_data()
if 'watchlist' not in st.session_state: st.session_state['watchlist'] = saved_data['watchlist']
if 'stock_names' not in st.session_state: st.session_state['stock_names'] = saved_data['stock_names']
if 'current_stock' not in st.session_state: 
    st.session_state['current_stock'] = st.session_state['watchlist'][0] if st.session_state['watchlist'] else "005930"
if 'trade_history' not in st.session_state: st.session_state['trade_history'] = {}

# --- API 연결 ---
api = KisApi()
if 'kis_token' in st.session_state and st.session_state['kis_token'] is not None:
    api.token = st.session_state['kis_token']
else:
    if api.get_access_token():
        st.session_state['kis_token'] = api.token 
        st.session_state['token_ok'] = True
    else:
        st.error("API 토큰 발급 실패! 키 값을 확인하세요.")
        st.stop()

def get_stock_name(code):
    if code in st.session_state['stock_names']: return st.session_state['stock_names'][code]
    try:
        name = stock.get_market_ticker_name(code)
        if not name: name = code
        st.session_state['stock_names'][code] = name
        save_data() 
        return name
    except: return code

# ==========================================
# [분석 로직] 기술적 분석 및 신호 생성
# ==========================================
def analyze_market_signal(df, current_price):
    if len(df) < 20: return "데이터 부족", "gray", 0, 0

    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()

    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    rsi = latest['RSI']
    vol_ratio = (latest['Volume'] / latest['Vol_MA5']) * 100 
    
    signal = "관망 (Hold)"
    color = "gray"
    score = 0

    if current_price > latest['MA20']: score += 1 
    if latest['MA5'] > latest['MA20']: score += 1 

    if vol_ratio > 100: score += 1 
    if vol_ratio > 200: score += 1 

    if rsi < 30: 
        score += 2 
    elif rsi > 70: 
        score -= 2 

    if score >= 4:
        signal = "강력 매수 (Strong Buy)"
        color = "red"
    elif score >= 2:
        signal = "매수 우위 (Buy)"
        color = "orange"
    elif score <= -1:
        signal = "매도 우위 (Sell)"
        color = "blue"
    
    if current_price > prev['Close'] and vol_ratio < 60:
        signal = "매도 검토 (거래량 부족 상승)"
        color = "blue"
    
    return signal, color, rsi, vol_ratio

# ==========================================
# [사이드바] 종목 관리
# ==========================================
st.sidebar.header("📋 종목 리스트")
new_code = st.sidebar.text_input("종목 추가", placeholder="예: 005930")

if st.sidebar.button("➕ 추가"):
    if new_code and new_code not in st.session_state['watchlist']:
        st.session_state['watchlist'].append(new_code)
        get_stock_name(new_code)
        save_data()
        st.session_state['trade_history'][new_code] = {'buy_ordered': False, 'sell_ordered': False}
        st.rerun()

st.sidebar.markdown("---")
for code in st.session_state['watchlist'][:]:
    if code not in st.session_state['trade_history']:
        st.session_state['trade_history'][code] = {'buy_ordered': False, 'sell_ordered': False}
    
    name = get_stock_name(code)
    col_list, col_del = st.sidebar.columns([0.8, 0.2])
    with col_list:
        if st.button(f"{name} ({code})", key=f"sel_{code}"):
            st.session_state['current_stock'] = code
            st.rerun()
    with col_del:
        if st.button("❌", key=f"del_{code}"):
            st.session_state['watchlist'].remove(code)
            if st.session_state['current_stock'] == code:
                st.session_state['current_stock'] = st.session_state['watchlist'][0] if st.session_state['watchlist'] else "005930"
            save_data()
            st.rerun()

if not st.session_state['watchlist']:
    st.warning("👈 종목을 추가해주세요.")
    st.stop()

# ==========================================
# [메인 화면]
# ==========================================
target_code = st.session_state['current_stock']
target_name = get_stock_name(target_code)
st.title(f"🤖 {target_name} AI 트레이딩")

try:
    curr_data = api.get_current_price(target_code)
    current_price = int(curr_data['stck_prpr']) 
    yesterday_price = int(curr_data['stck_sdpr']) 
    change_rate = float(curr_data['prdy_ctrt']) 
    
    # -------------------------------------------------------
    # [수정됨] 차트 데이터 150일로 증가 (약 7개월치 확보)
    # 5개월 이상의 데이터를 확실하게 보여주기 위함
    # -------------------------------------------------------
    chart_dict = api.get_daily_price(target_code, 150)
    
    df = pd.DataFrame(chart_dict) 
    df = df.sort_values('Date').reset_index(drop=True)
    
except Exception as e:
    st.error(f"데이터 로딩 실패: {e}")
    st.stop()

# ------------------------------------------------
# 1. AI 매매 신호 분석
# ------------------------------------------------
ai_signal, signal_color, rsi_val, vol_strength = analyze_market_signal(df, current_price)

st.markdown("### 💡 AI 기술적 분석")
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("현재 주가", f"{current_price:,}원", f"{change_rate}%")
with c2:
    st.metric("거래량 강도 (평균대비)", f"{vol_strength:.1f}%", delta_color="off")
with c3:
    st.markdown(f"""
    <div style="background-color:{'#ffebee' if signal_color=='red' else '#e3f2fd' if signal_color=='blue' else '#f5f5f5'}; 
                padding:10px; border-radius:10px; text-align:center; border: 1px solid {signal_color}">
        <h4 style="color:{signal_color}; margin:0;">{ai_signal}</h4>
        <small>RSI: {rsi_val:.1f}</small>
    </div>
    """, unsafe_allow_html=True)

if vol_strength > 150:
    st.info("🔥 **거래량 폭발!** 평소보다 거래가 매우 활발합니다. 추세 전환의 신호일 수 있습니다.")
elif vol_strength < 50:
    st.caption("☁️ 거래량이 적어 신뢰도가 낮습니다. 관망하는 것이 좋습니다.")

# ------------------------------------------------
# 2. 매매 전략 설정
# ------------------------------------------------
st.divider()
st.markdown("### ⚙️ 전략 설정")
tab1, tab2 = st.tabs(["🔢 % 자동 계산", "✍️ 직접 가격 입력"])

with tab1:
    col_a, col_b = st.columns(2)
    with col_a:
        buy_pct = st.number_input("기준가 대비 하락 %", value=-3.0, step=0.5, max_value=0.0)
        calc_buy_price = int(yesterday_price * (1 + buy_pct / 100))
        st.caption(f"목표가: **{calc_buy_price:,}원**")
    with col_b:
        sell_pct = st.number_input("기준가 대비 상승 %", value=5.0, step=0.5, min_value=0.0)
        calc_sell_price = int(yesterday_price * (1 + sell_pct / 100))
        st.caption(f"목표가: **{calc_sell_price:,}원**")

with tab2:
    col_c, col_d = st.columns(2)
    with col_c: manual_buy_price = st.number_input("매수 희망가", value=0, step=100)
    with col_d: manual_sell_price = st.number_input("매도 희망가", value=0, step=100)

final_buy_price = manual_buy_price if manual_buy_price > 0 else calc_buy_price
final_sell_price = manual_sell_price if manual_sell_price > 0 else calc_sell_price

c1, c2, c3 = st.columns([1, 1, 2])
with c1: qty = st.number_input("주문 수량", min_value=1, value=1)
with c2:
    st.write(f"📉 매수: **{final_buy_price:,}원**")
    st.write(f"📈 매도: **{final_sell_price:,}원**")
with c3:
    auto_trade_on = st.toggle("🚀 자동매매 시작")
    if auto_trade_on: st.success("자동매매 실행 중...")

# ------------------------------------------------
# 3. 매매 실행 및 차트
# ------------------------------------------------
if st.button("🔄 새로고침"): st.rerun()

history = st.session_state['trade_history'][target_code]

if auto_trade_on:
    if current_price <= final_buy_price and not history['buy_ordered']:
        res = api.send_order(target_code, qty, 'buy')
        if res['rt_cd'] == '0':
            msg = f"[매수] {target_name} 체결\n가격: {current_price}원"
            kakao_msg.send_message(msg)
            st.toast(msg)
            history['buy_ordered'] = True
    
    if current_price >= final_sell_price and not history['sell_ordered']:
        res = api.send_order(target_code, qty, 'sell')
        if res['rt_cd'] == '0':
            msg = f"[매도] {target_name} 체결\n가격: {current_price}원"
            kakao_msg.send_message(msg)
            st.toast(msg)
            history['sell_ordered'] = True

if history['buy_ordered']: st.info("✅ 매수 주문 완료")
if history['sell_ordered']: st.info("✅ 매도 주문 완료")

# 차트 그리기
fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])

fig.add_trace(go.Candlestick(
    x=df['Date'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
    name="Price", increasing_line_color='#ef404a', decreasing_line_color='#2c56a8'
), row=1, col=1)

fig.add_trace(go.Scatter(x=df['Date'], y=df['MA20'], line=dict(color='orange', width=1), name="MA20"), row=1, col=1)

colors = ['#ef404a' if c >= o else '#2c56a8' for c, o in zip(df['Close'], df['Open'])]
fig.add_trace(go.Bar(x=df['Date'], y=df['Volume'], name="Volume", marker_color=colors), row=2, col=1)

fig.add_hline(y=final_buy_price, line_dash="dot", line_color="red", row=1, col=1)
fig.add_hline(y=final_sell_price, line_dash="dot", line_color="blue", row=1, col=1)

fig.update_layout(height=600, xaxis_rangeslider_visible=False, margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
st.plotly_chart(fig, use_container_width=True)