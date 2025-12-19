# init_tags.py
# -*- coding: utf-8 -*-
import oracledb
import os
from dotenv import load_dotenv
from tag_data import TAG_DICT  # 방금 만든 tag_data.py에서 데이터를 가져옵니다.

# 1. 환경 변수 로드 (.env 파일)
load_dotenv()

# 2. DB 연결 설정
# app.py와 동일한 설정 사용
dsn = os.getenv("DB_DSN", "localhost:1521/freepdb1")
user = os.getenv("DB_USER", "system")
password = os.getenv("DB_PASSWORD", "Asdf4156")

def init_db_tags():
    print("🔄 태그 데이터 초기화를 시작합니다...")
    
    conn = None
    try:
        conn = oracledb.connect(user=user, password=password, dsn=dsn)
        cur = conn.cursor()
        
        count = 0
        
        # TAG_DICT를 순회하며 DB에 저장
        for category, tags_map in TAG_DICT.items():
            for tag_name in tags_map.keys():
                # [수정] :1, :2 대신 명시적인 이름(:tn, :cat) 사용 + 딕셔너리 바인딩
                sql = """
                    MERGE INTO tags t
                    USING dual ON (t.tag_name = :tn)
                    WHEN MATCHED THEN
                        UPDATE SET category = :cat
                    WHEN NOT MATCHED THEN
                        INSERT (tag_name, category) VALUES (:tn, :cat)
                """
                # 값을 딕셔너리로 전달
                cur.execute(sql, {'tn': tag_name, 'cat': category})
                
                count += 1
                
        conn.commit()
        print(f"✅ 총 {count}개의 태그가 처리(저장/갱신)되었습니다.")
        print("🎉 DB 초기화 완료! 이제 앱을 실행하면 사이드바에 태그가 뜹니다.")

    except oracledb.Error as e:
        print(f"❌ DB 오류 발생: {e}")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    init_db_tags()