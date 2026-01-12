import requests
import json
import pandas as pd
import streamlit as st
import datetime
import os

class KisApi:
    def __init__(self):
        self.base_url = "https://openapivts.koreainvestment.com:29443"
        self.token = None
        self.token_file = "token_cache.json" # 토큰을 저장할 파일 이름
        
        # 1. 시크릿/Config 로딩 (기존과 동일)
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
    # [핵심 수정] 토큰을 파일에 저장하고 불러오는 로직 추가
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
            return None # 파일이 없으면 실패
        
        try:
            with open(self.token_file, "r") as f:
                data = json.load(f)
            
            # 토큰 유효시간 체크 (안전을 위해 6시간이 지났으면 폐기)
            saved_time = datetime.datetime.strptime(data['timestamp'], "%Y-%m-%d %H:%M:%S")
            time_diff = datetime.datetime.now() - saved_time
            
            if time_diff.total_seconds() > 21600: # 6시간(21600초) 지남?
                return None # 너무 오래됨 -> 새로 발급 받아야 함
            
            return data['token'] # 유효한 토큰 반환
        except:
            return None

    # -----------------------------------------------------------
    # [수정된 토큰 발급 함수]
    # -----------------------------------------------------------
    def get_access_token(self):
        # 1. 먼저 파일에 저장된 유효한 토큰이 있는지 확인
        saved_token = self.load_token_from_file()
        if saved_token:
            self.token = saved_token
            # st.success("기존 토큰을 재사용합니다. (알림 안 옴)")
            return True

        # 2. 저장된 게 없거나 만료됐으면 -> 한국투자증권에 새로 요청 (이때만 알림 옴)
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
            self.save_token_to_file(new_token) # [중요] 파일에 저장해두기!
            return True
        else:
            return False

    # (나머지 조회 함수들은 그대로 유지)
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

    def get_daily_price(self, stock_code, period="D"):
        path = "uapi/domestic-stock/v1/quotations/inquire-daily-price"
        url = f"{self.base_url}/{path}"
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010400"
        }
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code,
            "fid_period_div_code": period,
            "fid_org_adj_prc": "1"
        }
        res = requests.get(url, headers=headers, params=params)
        data = res.json()['output']
        df = pd.DataFrame(data)
        df = df[['stck_bsop_date', 'stck_oprc', 'stck_hgpr', 'stck_lwpr', 'stck_clpr', 'acml_vol']]
        df.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
        df['Date'] = pd.to_datetime(df['Date'], format='%Y%m%d')
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col])
        return df.sort_values('Date')

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