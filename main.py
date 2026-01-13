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
st.set_page_config(layout="wide", page_title="스마트 주식 봇 Ver 7.0 (개별설정)")

# --- 스타일 설정 ---
st.markdown("""
<style>
    [data-testid="stSidebar"] .stButton button {
        padding: 0px 5px; font-size: 14px; height: 38px; width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# [데이터 저장/로드] 종목별 설정 기능 추가
# ==========================================
DATA_FILE = "stock_data.json"

# 기본 설정값 (신규 종목 추가 시 사용)
DEFAULT_SETTINGS = {
    "buy_pct": -3.0,       # 매수 기준 (%)
    "sell_pct": 5.0,       # 매도 기준 (%)
    "manual_buy": 0,       # 직접 입력 매수거
    "manual_sell": 0,      # 직접 입력 매도가
    "qty": 1,              # 주문 수량
    "auto_on": False       # 자동매매 켜짐 여부
}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 예전 버전 파일 호환성 처리 (stock_settings가 없으면 생성)
            if "stock_settings" not in data:
                data["stock_settings"] = {}
                for code in data.get("watchlist", []):
                    data["stock_settings"][code] = DEFAULT_SETTINGS.copy()
            return data
    else:
        return {"watchlist": ["005930"], "stock_names": {}, "stock_settings": {}}

def save_data():
    data = {
        "watchlist": st.session_state['watchlist'],
        "stock_names": st.session_state['stock_names'],
        "stock_settings": st.session_state['stock_settings'] # 설정값도 저장
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 세션 초기화 ---
saved_data = load_data()
if 'watchlist' not in st.session_state: st.session_state['watchlist'] = saved_data['watchlist']
if 'stock_names' not in st.session_state: st.session_state['stock_names'] = saved_data['stock_names']
if 'stock_settings' not in st.session_state: st.session_state['stock_settings'] = saved_data.get('stock_settings', {})

# 현재 종목 설정 (리스트가 비어있지 않으면 첫 번째 종목 선택)
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

# 순서 변경 함수
def move_stock(index, direction):
    watchlist = st.session_state['watchlist']
    if direction == 'up' and index > 0:
        watchlist[index], watchlist[index-1] = watchlist[index-1], watchlist[index]
    elif direction == 'down' and index < len(watchlist) - 1:
        watchlist[index], watchlist[index+1] = watchlist[index+1], watchlist[index]
    save_data()
    st.rerun()

# ==========================================
# [분석 로직]
# ==========================================
def analyze_market_signal(df, current_price):
    if len(df) < 20: return "데이터 부족", "gray", 0, 0
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    # RSI 계산
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    rsi = latest['RSI']
    vol_ratio = (latest['Volume'] / latest['Vol_MA5']) * 100 if latest['Vol_MA5'] > 0 else 0
    
    signal = "관망 (Hold)"
    color = "gray"
    score = 0

    if current_price > latest['MA20']: score += 1 
    if latest['MA5'] > latest['MA20']: score += 1 
    if vol_ratio > 100: score += 1 
    if vol_ratio > 200: score += 1 
    if rsi < 30: score += 2 
    elif rsi > 70: score -= 2 

    if score >= 4: signal = "강력 매수"; color = "red"
    elif score >= 2: signal = "매수 우위"; color = "orange"
    elif score <= -1: signal = "매도 우위"; color = "blue"
    
    return signal, color, rsi, vol_ratio

# ==========================================
# [사이드바] 종목 관리
# ==========================================
st.sidebar.header("📋 종목 리스트")
new_code = st.sidebar.text_input("종목 추가", placeholder="예: 005930")

if st.sidebar.button("➕ 추가"):
    if new_code and new_code not in st.session_state['watchlist']:
        st.session_state['watchlist'].append(new_code)
        # 신규 종목 추가 시 기본 설정값 생성
        st.session_state['stock_settings'][new_code] = DEFAULT_SETTINGS.copy()
        
        get_stock_name(new_code)
        save_data()
        st.session_state['trade_history'][new_code] = {'buy_ordered': False, 'sell_ordered': False}
        st.rerun()

st.sidebar.markdown("---")

for idx, code in enumerate(st.session_state['watchlist']):
    if code not in st.session_state['trade_history']:
        st.session_state['trade_history'][code] = {'buy_ordered': False, 'sell_ordered': False}
    # 설정값이 없으면 생성 (구버전 호환)
    if code not in st.session_state['stock_settings']:
        st.session_state['stock_settings'][code] = DEFAULT_SETTINGS.copy()

    name = get_stock_name(code)
    
    # 현재 선택된 종목인지 확인 (선택됨 표시)
    is_selected = "👈" if st.session_state['current_stock'] == code else ""
    
    c_name, c_up, c_down, c_del = st.sidebar.columns([3, 1, 1, 1])
    with c_name:
        if st.button(f"{name} {is_selected}", key=f"sel_{code}"):
            st.session_state['current_stock'] = code
            st.rerun()
    with c_up:
        if idx > 0 and st.button("⬆️", key=f"up_{code}"): move_stock(idx, 'up')
    with c_down:
        if idx < len(st.session_state['watchlist']) - 1 and st.button("⬇️", key=f"down_{code}"): move_stock(idx, 'down')
    with c_del:
        if st.button("❌", key=f"del_{code}"):
            st.session_state['watchlist'].remove(code)
            del st.session_state['stock_settings'][code] # 설정도 삭제
            if st.session_state['current_stock'] == code:
                st.session_state['current_stock'] = st.session_state['watchlist'][0] if st.session_state['watchlist'] else "005930"
            save_data()
            st.rerun()

if not st.session_state['watchlist']:
    st.warning("👈 종목을 추가해주세요."); st.stop()

# ==========================================
# [메인 화면]
# ==========================================
target_code = st.session_state['current_stock']
target_name = get_stock_name(target_code)
my_setting = st.session_state['stock_settings'][target_code] # 현재 종목의 설정 불러오기

st.title(f"🤖 {target_name} 개별 설정")

try:
    curr_data = api.get_current_price(target_code)
    current_price = int(curr_data['stck_prpr']) 
    yesterday_price = int(curr_data['stck_sdpr']) 
    change_rate = float(curr_data['prdy_ctrt']) 
    
    chart_df = api.get_daily_price(target_code, 150)
    
except Exception as e:
    st.error(f"데이터 로딩 실패: {e}")
    st.stop()

# 1. AI 분석
ai_signal, signal_color, rsi_val, vol_strength = analyze_market_signal(chart_df, current_price)
st.markdown("### 💡 AI 분석")
c1, c2, c3 = st.columns(3)
with c1: st.metric("현재 주가", f"{current_price:,}원", f"{change_rate}%")
with c2: st.metric("거래량 강도", f"{vol_strength:.1f}%")
with c3:
    st.markdown(f"<div style='color:{signal_color}; font-weight:bold; font-size:18px; border:1px solid {signal_color}; padding:5px; text-align:center; border-radius:5px;'>{ai_signal}</div>", unsafe_allow_html=True)

# ------------------------------------------------
# 2. [개별 설정] 종목별로 값이 다르게 저장됨
# ------------------------------------------------
st.divider()
st.markdown(f"### ⚙️ **{target_name}** 전용 전략 설정")

# Key에 target_code를 붙여서 종목별로 위젯을 분리함
tab1, tab2 = st.tabs(["🔢 % 자동 계산", "✍️ 직접 가격 입력"])

with tab1:
    col_a, col_b = st.columns(2)
    with col_a:
        # 값을 변경하면 session_state['stock_settings']에 바로 반영되게 구현
        new_buy_pct = st.number_input("기준가 대비 하락 %", value=my_setting['buy_pct'], step=0.5, max_value=0.0, key=f"bp_{target_code}")
        calc_buy_price = int(yesterday_price * (1 + new_buy_pct / 100))
        st.caption(f"목표가: **{calc_buy_price:,}원**")
    with col_b:
        new_sell_pct = st.number_input("기준가 대비 상승 %", value=my_setting['sell_pct'], step=0.5, min_value=0.0, key=f"sp_{target_code}")
        calc_sell_price = int(yesterday_price * (1 + new_sell_pct / 100))
        st.caption(f"목표가: **{calc_sell_price:,}원**")

with tab2:
    col_c, col_d = st.columns(2)
    with col_c: 
        new_manual_buy = st.number_input("매수 희망가", value=my_setting['manual_buy'], step=100, key=f"mb_{target_code}")
    with col_d: 
        new_manual_sell = st.number_input("매도 희망가", value=my_setting['manual_sell'], step=100, key=f"ms_{target_code}")

# 최종 목표가 결정
final_buy_price = new_manual_buy if new_manual_buy > 0 else calc_buy_price
final_sell_price = new_manual_sell if new_manual_sell > 0 else calc_sell_price

c1, c2, c3 = st.columns([1, 1, 2])
with c1: 
    new_qty = st.number_input("주문 수량", min_value=1, value=my_setting['qty'], key=f"qty_{target_code}")
with c2:
    st.write(f"📉 매수: **{final_buy_price:,}원**")
    st.write(f"📈 매도: **{final_sell_price:,}원**")
with c3:
    # 자동매매 스위치도 종목별로 저장
    new_auto_on = st.toggle("🚀 자동매매 시작", value=my_setting['auto_on'], key=f"auto_{target_code}")
    if new_auto_on: st.success("자동매매 실행 중...")

# [중요] 변경된 설정값을 저장소에 업데이트하고 파일 저장
# 위젯의 값(new_...)들이 바뀌면 바로 반영됨
if (my_setting['buy_pct'] != new_buy_pct or my_setting['sell_pct'] != new_sell_pct or
    my_setting['qty'] != new_qty or my_setting['auto_on'] != new_auto_on or
    my_setting['manual_buy'] != new_manual_buy or my_setting['manual_sell'] != new_manual_sell):
    
    st.session_state['stock_settings'][target_code] = {
        "buy_pct": new_buy_pct,
        "sell_pct": new_sell_pct,
        "manual_buy": new_manual_buy,
        "manual_sell": new_manual_sell,
        "qty": new_qty,
        "auto_on": new_auto_on
    }
    save_data() # 파일에 영구 저장

# ------------------------------------------------
# 3. 매매 실행
# ------------------------------------------------
if st.button("🔄 새로고침"): st.rerun()

history = st.session_state['trade_history'][target_code]

# [중요] 개별 설정된 'new_auto_on'이 켜져 있을 때만 동작
if new_auto_on:
    # 매수 로직
    if current_price <= final_buy_price and not history['buy_ordered']:
        res = api.send_order(target_code, new_qty, 'buy')
        if res['rt_cd'] == '0':
            msg = f"[매수] {target_name} 체결\n가격: {current_price}원\n수량: {new_qty}주"
            kakao_msg.send_message(msg); st.toast(msg)
            history['buy_ordered'] = True
    
    # 매도 로직
    if current_price >= final_sell_price and not history['sell_ordered']:
        res = api.send_order(target_code, new_qty, 'sell')
        if res['rt_cd'] == '0':
            msg = f"[매도] {target_name} 체결\n가격: {current_price}원\n수량: {new_qty}주"
            kakao_msg.send_message(msg); st.toast(msg)
            history['sell_ordered'] = True

if history['buy_ordered']: st.info("✅ 오늘 매수 완료")
if history['sell_ordered']: st.info("✅ 오늘 매도 완료")

# 차트 그리기
fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
fig.add_trace(go.Candlestick(x=chart_df['Date'], open=chart_df['Open'], high=chart_df['High'], low=chart_df['Low'], close=chart_df['Close'], name="Price", increasing_line_color='#ef404a', decreasing_line_color='#2c56a8'), row=1, col=1)
fig.add_trace(go.Scatter(x=chart_df['Date'], y=chart_df['MA20'], line=dict(color='orange', width=1), name="MA20"), row=1, col=1)
colors = ['#ef404a' if c >= o else '#2c56a8' for c, o in zip(chart_df['Close'], chart_df['Open'])]
fig.add_trace(go.Bar(x=chart_df['Date'], y=chart_df['Volume'], name="Volume", marker_color=colors), row=2, col=1)
fig.add_hline(y=final_buy_price, line_dash="dot", line_color="red", row=1, col=1)
fig.add_hline(y=final_sell_price, line_dash="dot", line_color="blue", row=1, col=1)
fig.update_layout(height=600, xaxis_rangeslider_visible=False, margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
st.plotly_chart(fig, use_container_width=True)