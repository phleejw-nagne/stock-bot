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

# --- 페이지 설정 ---
st.set_page_config(layout="wide", page_title="스마트 주식 봇 Ver 5.2")

# ==========================================
# [데이터 저장/로드 기능] 
# ==========================================
DATA_FILE = "stock_data.json"

def load_data():
    """파일에서 데이터 로드"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {"watchlist": ["005930"], "stock_names": {}}

def save_data():
    """데이터 파일 저장"""
    data = {
        "watchlist": st.session_state['watchlist'],
        "stock_names": st.session_state['stock_names']
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 세션 초기화 ---
saved_data = load_data()

if 'watchlist' not in st.session_state: 
    st.session_state['watchlist'] = saved_data['watchlist']

if 'stock_names' not in st.session_state: 
    st.session_state['stock_names'] = saved_data['stock_names']

if 'current_stock' not in st.session_state: 
    # 리스트가 비어있지 않으면 첫 번째, 비어있으면 삼성전자 기본값
    st.session_state['current_stock'] = st.session_state['watchlist'][0] if st.session_state['watchlist'] else "005930"

if 'trade_history' not in st.session_state: 
    st.session_state['trade_history'] = {}

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
    if code in st.session_state['stock_names']: 
        return st.session_state['stock_names'][code]
    try:
        name = stock.get_market_ticker_name(code)
        if not name: name = code
        st.session_state['stock_names'][code] = name
        save_data() 
        return name
    except: 
        return code

# ==========================================
# [사이드바] 종목 관리 (삭제 버튼 추가됨)
# ==========================================
st.sidebar.header("📋 종목 리스트")
new_code = st.sidebar.text_input("종목 추가", placeholder="예: 005930")

if st.sidebar.button("➕ 추가"):
    if new_code and new_code not in st.session_state['watchlist']:
        st.session_state['watchlist'].append(new_code)
        get_stock_name(new_code) # 이름 미리 확보
        save_data() # 저장
        st.session_state['trade_history'][new_code] = {'buy_ordered': False, 'sell_ordered': False}
        st.rerun()

st.sidebar.markdown("---")

# 리스트 출력 (삭제 버튼 구현)
# 복사본을 만들어 순회 (삭제 시 인덱스 오류 방지)
for code in st.session_state['watchlist'][:]:
    if code not in st.session_state['trade_history']:
        st.session_state['trade_history'][code] = {'buy_ordered': False, 'sell_ordered': False}
    
    name = get_stock_name(code)
    
    # 레이아웃 분할: [종목선택버튼 (80%)] [삭제버튼 (20%)]
    col_list, col_del = st.sidebar.columns([0.8, 0.2])
    
    with col_list:
        # 선택 버튼
        if st.button(f"{name} ({code})", key=f"sel_{code}"):
            st.session_state['current_stock'] = code
            st.rerun()
            
    with col_del:
        # 삭제 버튼 (빨간색 텍스트 느낌의 이모지 사용)
        if st.button("❌", key=f"del_{code}", help="리스트에서 삭제"):
            st.session_state['watchlist'].remove(code)
            
            # 현재 보고 있는 종목을 삭제했다면? -> 남은 것 중 첫번째로 이동
            if st.session_state['current_stock'] == code:
                if st.session_state['watchlist']:
                    st.session_state['current_stock'] = st.session_state['watchlist'][0]
                else:
                    st.session_state['current_stock'] = "005930" # 다 지워지면 기본값
            
            save_data() # 파일 반영
            st.rerun()

# ==========================================
# [메인 화면]
# ==========================================
# watchlist가 하나도 없을 때를 대비한 예외 처리
if not st.session_state['watchlist']:
    st.warning("👈 사이드바에서 관심 종목을 추가해주세요.")
    st.stop()

target_code = st.session_state['current_stock']
target_name = get_stock_name(target_code)

st.title(f"🤖 {target_name} 스마트 매매")

try:
    curr_data = api.get_current_price(target_code)
    current_price = int(curr_data['stck_prpr']) 
    yesterday_price = int(curr_data['stck_sdpr']) 
    change_rate = float(curr_data['prdy_ctrt']) 
except:
    st.error("데이터 로딩 실패 (장 운영 시간이 아니거나 API 오류)")
    st.stop()

# ------------------------------------------------
# 1. 매매 전략 설정
# ------------------------------------------------
st.markdown("### ⚙️ 전략 설정")
tab1, tab2 = st.tabs(["🔢 % 자동 계산", "✍️ 직접 가격 입력"])

with tab1:
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**🔵 매수 설정**")
        buy_pct = st.number_input("기준가 대비 하락 %", value=-3.0, step=0.5, max_value=0.0)
        calc_buy_price = int(yesterday_price * (1 + buy_pct / 100))
        st.caption(f"목표가: **{calc_buy_price:,}원**")
    with col_b:
        st.markdown("**🔴 매도 설정**")
        sell_pct = st.number_input("기준가 대비 상승 %", value=5.0, step=0.5, min_value=0.0)
        calc_sell_price = int(yesterday_price * (1 + sell_pct / 100))
        st.caption(f"목표가: **{calc_sell_price:,}원**")

with tab2:
    col_c, col_d = st.columns(2)
    with col_c:
        manual_buy_price = st.number_input("매수 희망가 (원)", value=0, step=100)
    with col_d:
        manual_sell_price = st.number_input("매도 희망가 (원)", value=0, step=100)

if manual_buy_price > 0:
    final_buy_price = manual_buy_price
else:
    final_buy_price = calc_buy_price

if manual_sell_price > 0:
    final_sell_price = manual_sell_price
else:
    final_sell_price = calc_sell_price

st.markdown("---")
c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    qty = st.number_input("주문 수량 (주)", min_value=1, value=1)
with c2:
    st.markdown(f"**매수 목표**: {final_buy_price:,}원")
    st.markdown(f"**매도 목표**: {final_sell_price:,}원")
with c3:
    auto_trade_on = st.toggle("🚀 자동매매 시작")
    if auto_trade_on:
        st.success("자동매매 실행 중...")

# ------------------------------------------------
# 2. 매매 실행 로직
# ------------------------------------------------
st.divider()
st.metric(label="실시간 현재가", value=f"{current_price:,}원", delta=f"{change_rate}%")

if st.button("🔄 시세/차트 새로고침"):
    st.rerun()

history = st.session_state['trade_history'][target_code]

if auto_trade_on:
    if current_price <= final_buy_price and not history['buy_ordered']:
        res = api.send_order(target_code, qty, 'buy')
        if res['rt_cd'] == '0':
            msg = f"[매수체결] {target_name}\n목표: {final_buy_price}원\n체결: {current_price}원"
            kakao_msg.send_message(msg)
            st.toast(msg)
            history['buy_ordered'] = True
    
    if current_price >= final_sell_price and not history['sell_ordered']:
        res = api.send_order(target_code, qty, 'sell')
        if res['rt_cd'] == '0':
            msg = f"[매도체결] {target_name}\n목표: {final_sell_price}원\n체결: {current_price}원"
            kakao_msg.send_message(msg)
            st.toast(msg)
            history['sell_ordered'] = True

if history['buy_ordered']: st.info("✅ 매수 주문 완료됨")
if history['sell_ordered']: st.info("✅ 매도 주문 완료됨")

# ------------------------------------------------
# 3. 차트 표시 (거래량 포함)
# ------------------------------------------------
st.markdown("### 📊 차트 (일봉 & 거래량)")

try:
    chart_data = api.get_daily_price(target_code, 60)
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, 
                        row_heights=[0.7, 0.3])

    # 캔들
    fig.add_trace(go.Candlestick(
        x=chart_data['Date'],
        open=chart_data['Open'], high=chart_data['High'],
        low=chart_data['Low'], close=chart_data['Close'],
        name="Price",
        increasing_line_color='#ef404a', decreasing_line_color='#2c56a8'
    ), row=1, col=1)

    # 거래량
    colors = ['#ef404a' if c >= o else '#2c56a8' for c, o in zip(chart_data['Close'], chart_data['Open'])]
    fig.add_trace(go.Bar(
        x=chart_data['Date'],
        y=chart_data['Volume'],
        name="Volume",
        marker_color=colors
    ), row=2, col=1)

    # 목표가 선
    fig.add_hline(y=final_buy_price, line_dash="dot", line_color="red", row=1, col=1, annotation_text="매수")
    fig.add_hline(y=final_sell_price, line_dash="dot", line_color="blue", row=1, col=1, annotation_text="매도")

    fig.update_layout(
        height=600, 
        xaxis_rangeslider_visible=False,
        margin=dict(t=30, b=20, l=10, r=10),
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"차트 데이터 조회 실패: {e}")