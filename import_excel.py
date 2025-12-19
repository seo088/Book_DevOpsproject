import pandas as pd
import oracledb
import os
from dotenv import load_dotenv
import math

# .env 파일 로드 (DB 정보 가져오기)
load_dotenv()

def import_excel_to_db():
    # 1. 엑셀 파일 읽기
    excel_file = 'IndieBookstores_file.xlsx'  # 파일명 확인해주세요
    
    try:
        # 엑셀 파일 읽어오기 (첫 번째 시트)
        df = pd.read_excel(excel_file)
        print(f"✅ 엑셀 파일 로드 성공: {len(df)}개의 데이터 발견")
        
        # NaN(빈 값)을 None(NULL)으로 변환 (DB 저장 시 에러 방지)
        df = df.where(pd.notnull(df), None)
        
    except Exception as e:
        print(f"❌ 엑셀 파일 읽기 실패: {e}")
        return

    # 2. DB 연결
    conn = None
    try:
        conn = oracledb.connect(
            user=os.getenv("DB_USER", "system"),
            password=os.getenv("DB_PASSWORD", "Asdf4156"), 
            dsn=os.getenv("DB_DSN", "localhost:1521/freepdb1") # 안되면 ORCLCDB 등으로 수정
        )
        cur = conn.cursor()
        print("✅ DB 연결 성공")

        # 3. 데이터 한 줄씩 INSERT
        success_count = 0
        
        # INSERT 쿼리 (store_id는 자동생성이므로 제외)
        sql = """
            INSERT INTO IndieBookstores (
                name, address, phone_number, open_hours, 
                sns, lat, lon, description, closed_day
            ) VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9)
        """

        for index, row in df.iterrows():
            try:
                # 엑셀 컬럼명과 매칭 (엑셀 헤더가 영어라고 가정)
                # 만약 엑셀 헤더가 한글이면 row['이름'], row['주소'] 식으로 수정해야 함
                cur.execute(sql, (
                    row.get('name'),         # 책방 이름
                    row.get('address'),      # 주소
                    row.get('phone_number'), # 전화번호
                    row.get('open_hours'),   # 운영시간
                    row.get('sns'),          # SNS 주소
                    row.get('lat'),          # 위도 (숫자)
                    row.get('lon'),          # 경도 (숫자)
                    row.get('description'),  # 설명
                    row.get('closed_day')    # 휴무일
                ))
                success_count += 1
                
            except Exception as e:
                print(f"⚠️ {index+1}행 저장 실패 ({row.get('name')}): {e}")

        conn.commit()
        print(f"\n🎉 총 {success_count}개의 독립서점 데이터가 DB에 저장되었습니다!")

    except Exception as e:
        print(f"❌ DB 작업 중 오류 발생: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    import_excel_to_db()