#도서관 정보 공공데이터에서 수집해 정제한 후 DB에 저장하는 스크립트

import oracledb
import requests
import os
import re
import time
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    try:
        user = os.getenv("DB_USER", "system")
        pw = os.getenv("DB_PASSWORD", "Asdf4156")
        dsn = os.getenv("DB_DSN", "localhost:1521/freepdb1")
        return oracledb.connect(user=user, password=pw, dsn=dsn)
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")
        return None

def update_libraries():
    # 이미지에서 확인한 본인의 인증키를 여기에 넣으세요
    AUTH_KEY = "3fce750221fee8a6d67f789ea3bf59282677236a33d39fdafb40cda8cb8471b9"
    
    conn = get_connection()
    if not conn: return
    cur = conn.cursor()

    page_no = 1
    total_found = 0
    
    print("🚀 [전북 정밀 선별] 수집을 시작합니다. (경기도/경북 제외 로직 가동)")

    while True:
        url = f"http://data4library.kr/api/libSrch?authKey={AUTH_KEY}&format=json&pageSize=200&pageNo={page_no}"
        
        try:
            response = requests.get(url, timeout=20)
            data = response.json()
            libs_list = data.get('response', {}).get('libs', [])
            
            if not libs_list:
                break

            found_in_page = 0
            for item in libs_list:
                lib = item['lib']
                name = lib.get('libName', 'Unknown')
                location = lib.get('address') or lib.get('addr') or ''
                
                # ⭐ [핵심 수정] 주소가 '전북' 또는 '전라북도'로 시작하거나 포함되어야 함
                # '경'으로 시작하는 경기도, 경북을 확실히 제외하기 위해 더 엄격하게 체크
                is_jeonbuk = False
                if location.startswith('전북') or location.startswith('전라북도'):
                    is_jeonbuk = True
                elif '전라북도' in location or '전북 ' in location: # '전북' 뒤에 공백이 있는 경우 등
                    is_jeonbuk = True
                
                # 추가 검증: '경기도', '경상북도', '경북'이 포함되어 있으면 무조건 제외
                if any(bad_kw in location for bad_kw in ['경기도', '경상북도', '경북']):
                    is_jeonbuk = False

                if is_jeonbuk:
                    # 전화번호 추출
                    phone_raw = lib.get('tel', '')
                    phone_match = re.search(r'(\d{2,3}-\d{3,4}-\d{4})', phone_raw)
                    phone = phone_match.group(1) if phone_match else phone_raw[:50]
                    
                    sns = lib.get('homepage', '')[:200]
                    
                    try:
                        lat = float(lib['latitude']) if lib.get('latitude') else None
                        lon = float(lib['longitude']) if lib.get('longitude') else None
                    except:
                        lat, lon = None, None

                    sql = """
                        MERGE INTO libraries T
                        USING dual ON (T.NAME = :1)
                        WHEN MATCHED THEN
                            UPDATE SET LOCATION = :2, PHONE = :3, SNS = :4, LAT = :5, LON = :6, TYPE = '도서관'
                        WHEN NOT MATCHED THEN
                            INSERT (NAME, LOCATION, PHONE, SNS, LAT, LON, TYPE) 
                            VALUES (:7, :8, :9, :10, :11, :12, '도서관')
                    """
                    cur.execute(sql, [name, location, phone, sns, lat, lon, name, location, phone, sns, lat, lon])
                    found_in_page += 1
                    total_found += 1

            conn.commit()
            if found_in_page > 0:
                print(f"✅ {page_no}페이지 완료 (순수 전북 데이터 {found_in_page}개 추가 / 누적 {total_found}개)")
            
            page_no += 1
            time.sleep(0.1)

        except Exception as e:
            print(f"❌ 오류 발생: {e}")
            break

    print(f"\n🎉 [최종 결과] 경기도/경북을 제외한 순수 전북 도서관 {total_found}개 저장 완료!")
    cur.close()
    conn.close()

if __name__ == "__main__":
    update_libraries()