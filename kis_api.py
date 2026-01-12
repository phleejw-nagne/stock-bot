import requests
import json
import pandas as pd
import streamlit as st

class KisApi:
    def __init__(self):
        self.base_url = "https://openapivts.koreainvestment.com:29443" # 기본값 설정
        self.token = None
        
        # [핵심 수정] Secrets(서버) 먼저 확인하고, 없으면 config(로컬) 확인
        try:
            # 1. 서버(Streamlit Cloud) 환경인지 시도
            self.app_key = st.secrets["APP_KEY"]
            self.app_secret = st.secrets["APP_SECRET"]
            self.base_url = st.secrets["URL_BASE"]
            # print("서버 환경 감지됨")
        except:
            # 2. 실패하면 로컬(내 컴퓨터) 환경이라고 판단하고 config 불러오기
            import config 
            self.app_key = config.APP_KEY
            self.app_secret = config.APP_SECRET
            self.base_url = config.URL_BASE
            # print("로컬 환경 감지됨")

    # 1. 토큰 발급
    def get_access_token(self):
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
            self.token = res.json()['access_token']
            return True
        else:
            return False

    # 2. 현재가 조회
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
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code
        }
        res = requests.get(url, headers=headers, params=params)
        return res.json()['output']

    # 3. 일별 시세 조회
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

    # 4. 주문 기능 (여기서도 config를 안전하게 불러와야 함)
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
        
        # [핵심] 계좌번호도 Secrets 확인 후 없으면 config에서 가져오기
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