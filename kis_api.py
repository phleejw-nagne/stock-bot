import requests
import json
import pandas as pd
import streamlit as st
import datetime # 날짜 계산을 위해 필수
import os

class KisApi:
    def __init__(self):
        self.base_url = "https://openapivts.koreainvestment.com:29443"
        self.token = None
        self.token_file = "token_cache.json" # 토큰 저장 파일명
        
        # 1. 시크릿/Config 로딩
        try:
            self.app_key = st.secrets["APP_KEY"]
            self.app_secret = st.secrets["APP_SECRET"]
            self.base_url = st.secrets["URL_BASE"]
        except:
            import config 
            self.app_key = config.APP_KEY
            self.app_secret = config.APP_SECRET
            self.base_url = config.URL_BASE

    # -----------------------------------------------------------
    # [토큰 관리] 파일 저장/로드 (카톡 알림 방지)
    # -----------------------------------------------------------
    def save_token_to_file(self, token):
        data = {
            "token": token,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(self.token_file, "w") as f:
            json.dump(data, f)

    def load_token_from_file(self):
        if not os.path.exists(self.token_file):
            return None 
        
        try:
            with open(self.token_file, "r") as f:
                data = json.load(f)
            
            # 6시간(21600초) 유효성 체크
            saved_time = datetime.datetime.strptime(data['timestamp'], "%Y-%m-%d %H:%M:%S")
            time_diff = datetime.datetime.now() - saved_time
            
            if time_diff.total_seconds() > 21600: 
                return None # 만료됨
            
            return data['token']
        except:
            return None

    # -----------------------------------------------------------
    # [토큰 발급] 캐시 확인 후 없을 때만 요청
    # -----------------------------------------------------------
    def get_access_token(self):
        # 1. 저장된 토큰 확인
        saved_token = self.load_token_from_file()
        if saved_token:
            self.token = saved_token
            return True

        # 2. 없으면 새로 요청 (이때만 알림 발생)
        path = "oauth2/tokenP"
        url = f"{self.base_url}/{path}"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        
        res = requests.post(url, headers=headers, data=json.dumps(body))
        
        if res.status_code == 200:
            new_token = res.json()['access_token']
            self.token = new_token
            self.save_token_to_file(new_token) # 파일에 저장
            return True
        else:
            return False

    # -----------------------------------------------------------
    # [현재가 조회]
    # -----------------------------------------------------------
    def get_current_price(self, stock_code):
        path = "uapi/domestic-stock/v1/quotations/inquire-price"
        url = f"{self.base_url}/{path}"
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010100"
        }
        params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": stock_code}
        res = requests.get(url, headers=headers, params=params)
        return res.json()['output']

    # -----------------------------------------------------------
    # [차트 데이터 조회] 기간별 시세 (150일 문제 해결 버전)
    # -----------------------------------------------------------
    def get_daily_price(self, stock_code, n_days=100):
        # 1. 날짜 계산 (오늘 ~ n일 전)
        end_dt = datetime.datetime.now()
        start_dt = end_dt - datetime.timedelta(days=n_days)
        
        str_start = start_dt.strftime("%Y%m%d")
        str_end = end_dt.strftime("%Y%m%d")

        # 2. 기간별 시세 API 호출 (TR_ID 변경됨: FHKST03010100)
        path = "uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        url = f"{self.base_url}/{path}"
        
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST03010100"
        }
        
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code,
            "fid_input_date_1": str_start,
            "fid_input_date_2": str_end,
            "fid_period_div_code": "D",
            "fid_org_adj_prc": "1"
        }
        
        res = requests.get(url, headers=headers, params=params)
        
        # 3. 데이터 파싱 (output2 사용)
        if res.status_code == 200 and 'output2' in res.json():
            data = res.json()['output2']
            df = pd.DataFrame(data)
            
            if df.empty: return pd.DataFrame()

            df = df[['stck_bsop_date', 'stck_oprc', 'stck_hgpr', 'stck_lwpr', 'stck_clpr', 'acml_vol']]
            df.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            
            df['Date'] = pd.to_datetime(df['Date'], format='%Y%m%d')
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col])
            
            return df.sort_values('Date')
        else:
            return pd.DataFrame()

    # -----------------------------------------------------------
    # [주문 전송]
    # -----------------------------------------------------------
    def send_order(self, stock_code, qty, buy_sell_type):
        path = "uapi/domestic-stock/v1/trading/order-cash"
        url = f"{self.base_url}/{path}"
        tr_id = "VTTC0802U" if buy_sell_type == 'buy' else "VTTC0801U"
        
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id
        }
        
        try:
            cano = st.secrets["CANO"]
            acnt_prdt_cd = st.secrets["ACNT_PRDT_CD"]
        except:
            import config
            cano = config.CANO
            acnt_prdt_cd = config.ACNT_PRDT_CD

        body = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "PDNO": stock_code,
            "ORD_DVSN": "01",
            "ORD_QTY": str(qty),
            "ORD_UNPR": "0"
        }
        res = requests.post(url, headers=headers, data=json.dumps(body))
        return res.json()