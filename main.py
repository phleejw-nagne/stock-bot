import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import plotly.graph_objects as go
from kis_api import KisApi
from pykrx import stock 
import kakao_msg 
import time

# --- 페이지 설정 ---
st.set_page_config(layout="wide", page_title="스마트 주식 봇 Ver 5.0")

# --- 세션 상태 초기화 ---
if 'watchlist' not in st.session_state: st.session_state['watchlist'] = ["005930"]
if 'stock_names' not in st.session_state: st.session_state['stock_names'] = {}
if 'current_stock' not in st.session_state: st.session_state['current_stock'] = "005930"
if 'trade_history' not in st.session_state: st.session_state['trade_history'] = {}

# --- API 연결 ---
api = KisApi()
# 1. 세션에 저장된 토큰이 있는지 확인
if 'kis_token' in st.session_state and st.session_state['kis_token'] is not None:
    # 이미 발급받은 토큰이 있으면? -> 그냥 그거 씀 (API 요청 안 함!)
    api.token = st.session_state['kis_token']
    # print("기존 토큰을 사용합니다.") 

else:
    # 토큰이 없으면? -> 새로 발급받고 저장함
    if api.get_access_token():
        st.session_state['kis_token'] = api.token # 토큰값 자체를 저장
        st.session_state['token_ok'] = True
        # 여기에 카톡 알림이 있다면, 최초 1회만 발송됨
    else:
        st.error("API 토큰 발급 실패! 키 값을 확인하세요.")
        st.stop()

def get_stock_name(code):
    if code in st.session_state['stock_names']: return st.session_state['stock_names'][code]
    try:
        name = stock.get_market_ticker_name(code)
        if not name: name = code
        st.session_state['stock_names'][code] = name
        return name
    except: return code

# ==========================================
# [사이드바] 종목 관리
# ==========================================
st.sidebar.header("📋 종목 리스트")
new_code = st.sidebar.text_input("종목 추가", placeholder="예: 005930")
if st.sidebar.button("➕ 추가"):
    if new_code and new_code not in st.session_state['watchlist']:
        st.session_state['watchlist'].append(new_code)
        st.session_state['trade_history'][new_code] = {'buy_ordered': False, 'sell_ordered': False}
        st.rerun()

st.sidebar.markdown("---")
for code in st.session_state['watchlist']:
    if code not in st.session_state['trade_history']:
        st.session_state['trade_history'][code] = {'buy_ordered': False, 'sell_ordered': False}
    
    name = get_stock_name(code)
    if st.sidebar.button(f"{name} ({code})", key=f"btn_{code}"):
        st.session_state['current_stock'] = code
        st.rerun()

# ==========================================
# [메인 화면]
# ==========================================
target_code = st.session_state['current_stock']
target_name = get_stock_name(target_code)

st.title(f"🤖 {target_name} 스마트 매매")

# 데이터 미리 가져오기 (계산을 위해 필수)
try:
    curr_data = api.get_current_price(target_code)
    current_price = int(curr_data['stck_prpr']) # 현재가
    yesterday_price = int(curr_data['stck_sdpr']) # 전일 종가 (기준가)
    change_rate = float(curr_data['prdy_ctrt']) # 등락률
except:
    st.error("데이터 로딩 실패")
    st.stop()

# ------------------------------------------------
# 1. 매매 전략 설정 (자동 계산 기능 추가)
# ------------------------------------------------
st.markdown("### ⚙️ 전략 설정")

# 설정 방식 선택 (탭 기능)
tab1, tab2 = st.tabs(["🔢 % 자동 계산", "✍️ 직접 가격 입력"])

# [Tab 1] 퍼센트(%)로 자동 계산
with tab1:
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**🔵 매수 설정 (하락 시 구매)**")
        buy_pct = st.number_input("기준가 대비 몇 % 하락 시 매수?", value=-3.0, step=0.5, max_value=0.0)
        # 자동 계산 공식: 전일종가 * (1 + 퍼센트/100)
        calc_buy_price = int(yesterday_price * (1 + buy_pct / 100))
        st.caption(f"📉 계산된 매수 목표가: **{calc_buy_price:,}원**")
        
    with col_b:
        st.markdown("**🔴 매도 설정 (상승 시 판매)**")
        sell_pct = st.number_input("기준가 대비 몇 % 상승 시 매도?", value=5.0, step=0.5, min_value=0.0)
        calc_sell_price = int(yesterday_price * (1 + sell_pct / 100))
        st.caption(f"📈 계산된 매도 목표가: **{calc_sell_price:,}원**")

# [Tab 2] 직접 가격 입력
with tab2:
    col_c, col_d = st.columns(2)
    with col_c:
        manual_buy_price = st.number_input("매수 희망가 (원)", value=0, step=100)
    with col_d:
        manual_sell_price = st.number_input("매도 희망가 (원)", value=0, step=100)

# 최종 목표가 결정 로직 (어떤 탭을 쓰느냐에 따라 결정)
# 사용자가 Tab 2(직접입력)에 0이 아닌 값을 넣으면 그걸 우선순위로 둠.
# 그렇지 않으면 Tab 1(자동계산) 값을 사용.
if manual_buy_price > 0:
    final_buy_price = manual_buy_price
    buy_mode = "직접입력"
else:
    final_buy_price = calc_buy_price
    buy_mode = f"자동계산({buy_pct}%)"

if manual_sell_price > 0:
    final_sell_price = manual_sell_price
    sell_mode = "직접입력"
else:
    final_sell_price = calc_sell_price
    sell_mode = f"자동계산({sell_pct}%)"

# 수량 설정 및 스위치
st.markdown("---")
c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    qty = st.number_input("주문 수량 (주)", min_value=1, value=1)
with c2:
    st.markdown(f"**매수 목표**: {final_buy_price:,}원")
    st.markdown(f"**매도 목표**: {final_sell_price:,}원")
with c3:
    auto_trade_on = st.toggle("🚀 자동매매 시작 (ON/OFF)") # 체크박스보다 예쁜 토글 버튼
    if auto_trade_on:
        st.success("자동매매가 실행 중입니다. (브라우저를 끄지 마세요)")

# ------------------------------------------------
# 2. 매매 실행 로직
# ------------------------------------------------
st.divider()

# 현재가 표시
st.metric(label="실시간 현재가", value=f"{current_price:,}원", delta=f"{change_rate}%")

if st.button("🔄 시세 체크 및 주문 실행"):
    st.rerun()

history = st.session_state['trade_history'][target_code]

if auto_trade_on:
    # (1) 매수 로직
    if current_price <= final_buy_price:
        if not history['buy_ordered']:
            res = api.send_order(target_code, qty, 'buy')
            if res['rt_cd'] == '0':
                msg = f"[매수체결] {target_name}\n목표가: {final_buy_price}원\n체결가: {current_price}원"
                kakao_msg.send_message(msg)
                st.toast(f"✅ 매수 성공! {msg}")
                history['buy_ordered'] = True
            else:
                st.error(f"매수 실패: {res['msg1']}")

    # (2) 매도 로직
    if current_price >= final_sell_price:
        if not history['sell_ordered']:
            res = api.send_order(target_code, qty, 'sell')
            if res['rt_cd'] == '0':
                msg = f"[매도체결] {target_name}\n목표가: {final_sell_price}원\n체결가: {current_price}원"
                kakao_msg.send_message(msg)
                st.toast(f"✅ 매도 성공! {msg}")
                history['sell_ordered'] = True
            else:
                st.error(f"매도 실패: {res['msg1']}")

# 매매 상태 메시지
if history['buy_ordered']: st.info("✅ 매수 주문이 완료되었습니다.")
if history['sell_ordered']: st.info("✅ 매도 주문이 완료되었습니다.")

# ------------------------------------------------
# 3. 차트 표시
# ------------------------------------------------
st.markdown("### 📊 일봉 차트")

try:
    chart_data = api.get_daily_price(target_code, 60)
    
    fig = go.Figure(data=[go.Candlestick(x=chart_data['Date'], open=chart_data['Open'], high=chart_data['High'], low=chart_data['Low'], close=chart_data['Close'], increasing_line_color='#ef404a', decreasing_line_color='#2c56a8')])

    # 목표가 점선 추가
    fig.add_hline(y=final_buy_price, line_dash="dot", line_color="red", annotation_text=f"매수 목표({final_buy_price:,})")
    fig.add_hline(y=final_sell_price, line_dash="dot", line_color="blue", annotation_text=f"매도 목표({final_sell_price:,})")

    fig.update_layout(xaxis_rangeslider_visible=False, height=500, margin=dict(t=20, b=20))
    st.plotly_chart(fig, width='stretch')

except Exception as e:
    st.error(f"데이터 조회 실패: {e}")