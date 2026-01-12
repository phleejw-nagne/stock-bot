import requests
import json
import streamlit as st

def send_message(text):
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    
    # 토큰 가져오기 (서버 -> 로컬 순서)
    try:
        token = st.secrets["KAKAO_TOKEN"]
    except:
        import config
        token = config.KAKAO_TOKEN

    headers = {
        "Authorization": "Bearer " + token
    }
    
    data = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": text,
            "link": {
                "web_url": "https://www.naver.com",
                "mobile_web_url": "https://www.naver.com"
            },
            "button_title": "확인하러 가기"
        })
    }
    
    response = requests.post(url, headers=headers, data=data)
    if response.status_code == 200:
        return True
    else:
        return False