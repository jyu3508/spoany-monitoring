import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import re

# 1. 웹페이지 기본 설정
st.set_page_config(page_title="스포애니 모니터링 시스템", page_icon="🏋️‍♂️", layout="wide")

# 2. 네이버 API 키 설정
CLIENT_ID = "sVbbWfqJHXF433WsGcHo"
CLIENT_SECRET = "3ZD55wZRI3"

MY_BRAND = "스포애니"
COMPETITORS = ["버핏그라운드", "짐박스", "F45 TRAINING", "좋은습관 PT STUDIO", "헬스보이짐", "휘트니스피플우먼"]

# 📌 스팸 노이즈 키워드
EXCLUDE_KEYWORDS = ["호텔", "숙박", "패키지", "객실", "투숙", "갤럭시", "애플워치", "스마트워치", "웨어러블"]

# 📌 비만치료제 핵심 키워드
OBESITY_DRUGS = ["위고비", "마운자로", "삭센다", "다이어트 주사", "비만 치료제", "비만치료제", "다이어트약"]

# 📌 본사 차원의 핵심 비즈니스 동향 키워드
MY_BRAND_CORE_KEYWORDS = [
    "출시", "수상", "대표", "마케팅", "캠페인", "FRANCHISE", "창업", 
    "박람회", "페스타", "체인", "가맹", "업무협약", "MOU", "인수", "확장", "전략"
]

# 📌 지점 단위에서 주로 쓰는 프로모션 키워드 (뉴스 채널이 아닐 땐 일반 분류로 넘기기 위함)
BRANCH_PROMOTION_KEYWORDS = ["오픈", "할인", "프로모션", "이벤트", "리모델링", "단독", "회원권", "가격"]

# 📌 채용 관련 키워드
RECRUIT_KEYWORDS = ["모집", "채용", "구인", "구직", "트레이너구함", "강사구함", "인재채용"]

def clean_text(text):
    if not text: return ""
    tags = ["<b>", "</b>", "&quot;", "&gt;", "&lt;", "&amp;"]
    for tag in tags:
        text = text.replace(tag, "")
    return text

def classify_brand(title, description, channel_name):
    """텍스트와 채널 특성을 결합하여 완벽하게 의도대로 분류"""
    combined_text = (title + " " + description).replace(" ", "").upper()
    
    # 1. 최우선 분류: 비만치료제 이슈 검사
    if any(drug.replace(" ", "").upper() in combined_text for drug in OBESITY_DRUGS):
        return "비만치료제 트렌드"
        
    # 2. 자사 브랜드(스포애니) 분류 로직
    if MY_BRAND in combined_text:
        # 채용 공고는 무조건 일반/기타로 제외
        if any(recruit_word in combined_text for recruit_word in RECRUIT_KEYWORDS):
            return "스포애니 (일반 언급/기타)"
            
        # [교정 핵심 1] 뉴스 채널에 나온 스포애니 소식은 무조건 '핵심 비즈니스'로 분류
        if channel_name == "뉴스":
            return "스포애니 (핵심 비즈니스)"
            
        # [교정 핵심 2] 블로그/카페 글 중 'OO점', 'OO역점' 형태의 지점 홍보글 필터링
        # 제목에 '강남점', '범계역점' 등이 들어가면 지점형 일상/홍보로 판단
        is_branch_name = re.search(r"\d+호점|[가-힣]+점|[가-힣]+역점", title)
        
        # 본사 핵심 키워드가 포함되어 있다면 블로그라도 핵심 비즈니스
        if any(core_word.upper() in combined_text for core_word in MY_BRAND_CORE_KEYWORDS):
            return "스포애니 (핵심 비즈니스)"
            
        # 지점명이 명시되어 있거나, 단순 지점 프로모션 단어만 있는 경우 -> 일반 언급/기타로 분류
        if is_branch_name or any(promo_word.upper() in combined_text for promo_word in BRANCH_PROMOTION_KEYWORDS):
            return "스포애니 (일반 언급/기타)"
            
        return "스포애니 (일반 언급/기타)"
        
    # 3. 경쟁사 브랜드 검사
    matched_competitors = []
    for comp in COMPETITORS:
        target_comp = comp.replace(" ", "").upper()
        if "좋은습관" in comp:
            if "좋은습관PT" in combined_text or "좋은습관스튜디오" in combined_text:
                if comp not in matched_competitors: matched_competitors.append(comp)
        elif "F45" in comp:
            if "F45TRAINING" in combined_text or "F45트레이닝" in combined_text or "F45운동" in combined_text:
                if comp not in matched_competitors: matched_competitors.append(comp)
            elif "F45" in combined_text and ("헬스" in combined_text or "PT" in combined_text or "다이어트" in combined_text):
                if comp not in matched_competitors: matched_competitors.append(comp)
        elif target_comp in combined_text:
            matched_competitors.append(comp)
            
    if matched_competitors:
        return ", ".join(matched_competitors)
        
    return "업계 트렌드/동향"

def is_noise(title, description):
    combined_text = title + " " + description
    for word in EXCLUDE_KEYWORDS:
        if word in combined_text:
            return True
    return False

def fetch_naver_data(api_type, keyword, display_count=50):
    url = f"https://openapi.naver.com/v1/search/{api_type}.json?query={keyword}&display={display_count}&sort=date"
    headers = {"X-Naver-Client-Id": CLIENT_ID, "X-Naver-Client-Secret": CLIENT_SECRET}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get("items", [])
    except Exception as e:
        st.warning(f"네이버 {api_type} 통신 중 일시적 오류 발생: {e}")
    return []

@st.cache_data(ttl=600)
def load_smart_data():
    all_data = []
    channels = ["news", "blog", "cafearticle"]
    channel_names = {"news": "뉴스", "blog": "블로그", "cafearticle": "네이버카페"}
    
    search_competitors = []
    for c in COMPETITORS:
        if c == "좋은습관 PT STUDIO": search_competitors.append("좋은습관 PT")
        elif c == "F45 TRAINING": search_competitors.append("F45 트레이닝")
        else: search_competitors.append(c)
            
    brand_query = f"{MY_BRAND} | " + " | ".join(search_competitors)
    trend_query = "헬스장 PT"
    drug_query = "위고비 헬스장 | 마운자로 다이어트 | 비만치료제 운동"
    
    order_idx = 0
    for channel in channels:
        brand_items = fetch_naver_data(channel, brand_query, display_count=50)
        trend_items = fetch_naver_data(channel, trend_query, display_count=30)
        drug_items = fetch_naver_data(channel, drug_query, display_count=30)
        
        existing_links = set([raw["링크"] for raw in all_data] if all_data else [])
        
        for item in (brand_items + trend_items + drug_items):
            link = item.get("link")
            if not link or link in existing_links: 
                continue
            
            title = clean_text(item.get("title"))
            desc = clean_text(item.get("description"))
            
            if is_noise(title, desc): 
                continue
            
            # 💡 채널 한글명을 함께 넘겨 분류 신뢰도를 높임
            brand_category = classify_brand(title, desc, channel_names[channel])
            
            all_data.append({
                "채널": channel_names[channel],
                "분류": brand_category,
                "제목": title,
                "요약": desc,
                "링크": link,
                "api_order": order_idx
            })
            existing_links.add(link)
            order_idx += 1
            
    df = pd.DataFrame(all_data)
    if not df.empty:
        df = df.sort_values(by="api_order").drop(columns=["api_order"])
        
    return df

# 데이터 로드
try:
    df = load_smart_data()
except Exception as e:
    st.error(f"데이터 로드 중 치명적인 오류가 발생했습니다: {e}")
    df = pd.DataFrame()

# --- UI 레이아웃 화면 그리기 ---
st.title("🏋️‍♂️ 스포애니(SpoAny) 올인원 마케팅 모니터링 시스템")

# 💡 세계 표준시(UTC)에 9시간을 더해 정확한 한국 표준시(KST)를 계산합니다.
kor_now = datetime.utcnow() + timedelta(hours=9)

st.markdown(f"**현재 모니터링 시각 (한국):** {kor_now.strftime('%Y-%m-%d %H:%M:%S')} (접속 및 새로고침 시 실시간 동기화)")
st.divider()

if not df.empty:
    # 1. 상단 스코어보드 현황
    st.subheader("📊 금일 실시간 수집 현황")
    c1, c2, c3, c4, c5 = st.columns(5)
    
    core_cnt = len(df[df['분류'] == "스포애니 (핵심 비즈니스)"])
    etc_cnt = len(df[df['분류'] == "스포애니 (일반 언급/기타)"])
    drug_cnt = len(df[df['분류'] == "비만치료제 트렌드"])
    trend_cnt = len(df[df['분류'] == "업계 트렌드/동향"])
    comp_cnt = len(df) - (core_cnt + etc_cnt + drug_cnt + trend_cnt)

    c1.metric("🔵 자사 (핵심 마케팅)", f"{core_cnt}건")
    c2.metric("🔷 자사 (일반/지점 홍보)", f"{etc_cnt}건") # 마케터님 피드백 반영 명칭 변경
    c3.metric("🚨 비만치료제 트렌드", f"{drug_cnt}건")
    c4.metric("🔴 경쟁사 동향", f"{comp_cnt}건")
    c5.metric("⚪ 일반 업계 동향", f"{trend_cnt}건")
    st.divider()

    # 2. 사이드바 필터링
    st.sidebar.header("🔍 카테고리 필터")
    filter_options = ["전체보기", "스포애니 (핵심 비즈니스)", "스포애니 (일반 언급/기타)", "🚨 비만치료제 트렌드", "경쟁사 전체"] + COMPETITORS + ["업계 트렌드/동향"]
    selected = st.sidebar.selectbox("모니터링 대상 선택", options=filter_options)
    selected_channel = st.sidebar.radio("채널 선택", options=["전체 채널", "뉴스", "블로그", "네이버카페"])

    # 필터 적용 로직
    filtered_df = df.copy()
    if selected == "스포애니 (핵심 비즈니스)":
        filtered_df = filtered_df[filtered_df["분류"] == "스포애니 (핵심 비즈니스)"]
    elif selected == "스포애니 (일반 언급/기타)":
        filtered_df = filtered_df[filtered_df["분류"] == "스포애니 (일반 언급/기타)"]
    elif selected == "🚨 비만치료제 트렌드":
        filtered_df = filtered_df[filtered_df["분류"] == "비만치료제 트렌드"]
    elif selected == "경쟁사 전체":
        filtered_df = filtered_df[~filtered_df["분류"].isin(["스포애니 (핵심 비즈니스)", "스포애니 (일반 언급/기타)", "업계 트렌드/동향", "비만치료제 트렌드"])]
    elif selected != "전체보기":
        filtered_df = filtered_df[filtered_df["분류"] == selected]
        
    if selected_channel != "전체 채널":
        filtered_df = filtered_df[filtered_df["채널"] == selected_channel]

    # 3. 피드 피드백 화면 출력
    st.subheader(f"📋 모니터링 피드 ({selected} / {selected_channel})")
    if filtered_df.empty:
        st.info("선택한 조건의 데이터가 현재 존재하지 않습니다.")
    else:
        for idx, row in filtered_df.iterrows():
            if row["분류"] == "스포애니 (핵심 비즈니스)":
                badge = "🔵 [자사-마케팅핵심]"
            elif row["분류"] == "비만치료제 트렌드":
                badge = "💊 [비만치료제 이슈]"
            elif row["분류"] == "스포애니 (일반 언급/기타)":
                badge = "🔷 [자사-지점홍보/기타]"
            elif row["분류"] == "업계 트렌드/동향":
                badge = "⚪ [일반트렌드]"
            else:
                badge = f"🔴 [경쟁사: {row['분류']}]"
                
            with st.container():
                st.markdown(f"### 📄 {badge} {row['제목']}")
                st.caption(f"채널: {row['채널']} | 분류: {row['분류']}")
                st.write(row["요약"])
                st.markdown(f"[🔗 원본 글 본문 바로가기]({row['링크']})")
                st.divider()
else:
    st.info("수집 조건에 부합하는 클린 데이터가 없습니다. 검색어 설정이나 API 키를 확인해 주세요.")
