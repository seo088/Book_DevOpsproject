# update_existing_tags.py
# -*- coding: utf-8 -*-
import oracledb
import os
from dotenv import load_dotenv
from tag_data import TAG_DICT

# 1. 환경 변수 로드
load_dotenv()

# 2. DB 연결 설정
dsn = os.getenv("DB_DSN", "localhost:1521/freepdb1")
user = os.getenv("DB_USER", "system")
password = os.getenv("DB_PASSWORD", "Asdf4156")

def update_tags_for_all_books():
    print("🔄 기존 도서 태그 업데이트를 시작합니다...")
    
    conn = None
    try:
        conn = oracledb.connect(user=user, password=password, dsn=dsn)
        cur = conn.cursor()
        
        # 1. 모든 책 정보 가져오기
        print("📚 저장된 책 정보를 불러오는 중...")
        cur.execute("SELECT book_id, title, description FROM books")
        books = cur.fetchall()
        
        print(f"총 {len(books)}권의 책을 분석합니다.")
        
        success_count = 0
        
        for book in books:
            book_id = book[0]
            title = book[1] or ""
            # CLOB 타입 처리: description이 CLOB 객체일 수 있음
            description_obj = book[2]
            description = ""
            
            if description_obj:
                try:
                    description = description_obj.read() if hasattr(description_obj, 'read') else str(description_obj)
                except:
                    description = str(description_obj)

            # --- 태그 점수 계산 로직 (app.py와 동일) ---
            tag_scores = {}
            
            for category, tags_map in TAG_DICT.items():
                for tag_name, keywords in tags_map.items():
                    score = 0
                    for keyword in keywords:
                        if keyword in title: score += 3
                        if keyword in description: score += 1
                    
                    if score > 0:
                        tag_scores[tag_name] = tag_scores.get(tag_name, 0) + score
            
            # 상위 5개 태그 선정
            sorted_tags = sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)[:5]
            
            if not sorted_tags:
                continue

            # --- DB 저장 ---
            for tag_name, score in sorted_tags:
                # 1. 태그 ID 조회
                cur.execute("SELECT tag_id FROM tags WHERE tag_name = :1", (tag_name,))
                tag_row = cur.fetchone()
                
                if tag_row:
                    tag_id = tag_row[0]
                    # 2. BOOK_TAGS에 연결 (중복 무시 MERGE)
                    sql = """
                        MERGE INTO book_tags bt
                        USING dual ON (bt.book_id = :bid AND bt.tag_id = :tid)
                        WHEN NOT MATCHED THEN
                            INSERT (book_id, tag_id) VALUES (:bid, :tid)
                    """
                    cur.execute(sql, {'bid': book_id, 'tid': tag_id})
            
            success_count += 1
            if success_count % 10 == 0:
                print(f"⏳ {success_count}권 처리 완료...", end='\r')

        conn.commit()
        print(f"\n✅ 완료! 총 {success_count}권의 책에 태그가 부여되었습니다.")

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    update_tags_for_all_books()