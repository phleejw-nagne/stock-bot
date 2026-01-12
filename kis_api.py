# kis_api.py
import requests
import json
import pandas as pd
import config # 설정 파일 불러오기

class KisApi:
    def __init__(self):
        self.base_url = config.URL_BASE
        self.app_key = config.APP_KEY
        self.app_secret = config.APP_SECRET
        self.token = None
    
    # 1. 접근 토큰(Token) 발급받기
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

    # 2. 주식 현재가 정보 조회
    def get_current_price(self, stock_code):
        path = "uapi/domestic-stock/v1/quotations/inquire-price"
        url = f"{self.base_url}/{path}"
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010100" # 주식현재가 시세 조회 ID (모의투자/실전 동일)
        }
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code # 종목코드 (예: 005930)
        }
        res = requests.get(url, headers=headers, params=params)
        return res.json()['output']

    # 3. 주식 일별 시세 조회 (그래프용)
    def get_daily_price(self, stock_code, period="D"):
        path = "uapi/domestic-stock/v1/quotations/inquire-daily-price"
        url = f"{self.base_url}/{path}"
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010400" # 주식 일별 시세 조회 ID
        }
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code,
            "fid_period_div_code": period, # D:일봉, W:주봉, M:월봉
            "fid_org_adj_prc": "1" # 수정주가 반영 여부
        }
        res = requests.get(url, headers=headers, params=params)
        
        # 데이터를 보기 좋게 DataFrame으로 변환
        data = res.json()['output']
        df = pd.DataFrame(data)
        # 날짜, 시가, 고가, 저가, 종가, 거래량 컬럼만 선택 및 숫자형 변환
        df = df[['stck_bsop_date', 'stck_oprc', 'stck_hgpr', 'stck_lwpr', 'stck_clpr', 'acml_vol']]
        df.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
        df['Date'] = pd.to_datetime(df['Date'], format='%Y%m%d')
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col])
        
        return df.sort_values('Date') # 날짜 오름차순 정렬
