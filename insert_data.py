import oracledb

def insert_books():
    conn = None
    try:
        # 1. db.py와 동일한 정보로 DB에 연결합니다.
        conn = oracledb.connect(user="system", password="0000", dsn="localhost:1521/XE")
        cur = conn.cursor()
        print("✅ 데이터베이스 연결 성공")

        # 2. 기존 데이터를 깨끗하게 비웁니다.
        cur.execute("TRUNCATE TABLE books")
        print("- books 테이블 초기화 완료")

        # 3. 추가할 책 데이터 목록을 준비합니다.
        books_to_insert = [
            (
                '9788960176542', '8960176542', '혼모노', '하마오 요코', '은행나무',
                oracledb.Date(2022, 5, 10),
                'https://image.aladin.co.kr/product/29512/34/cover500/k842838988_1.jpg',
                '진짜와 가짜 사이에서 흔들리는 사람들의 내면을 그려낸 하마오 요코의 감정 에세이.',
                'aladin'
            ),
            (
                '9788971992258', '8971992258', '모순', '양귀자', '쓰다',
                oracledb.Date(2016, 8, 1),
                'https://image.aladin.co.kr/product/345/70/cover500/8971992258_1.jpg',
                '세상에 순응하지 않으려는 스물세 살 여자와 그녀의 가족, 그리고 모순된 삶 속에서 인간의 성장과 상처를 그려낸 양귀자의 대표작.',
                'aladin'
            )
        ]

        # 4. executemany를 사용해 데이터를 한 번에 추가합니다.
        sql = """
            INSERT INTO books ( book_id, isbn10, title, author, publisher, published_at, cover_image, description, source )
            VALUES ( :1, :2, :3, :4, :5, :6, :7, :8, :9 )
        """
        cur.executemany(sql, books_to_insert)
        print(f"- {cur.rowcount}개의 책 데이터 추가 준비 완료")

        # 5. 변경사항을 영구 저장(COMMIT)합니다.
        conn.commit()
        print("✅ 커밋 완료! 데이터가 영구적으로 저장되었습니다.")

        # 6. 정말 데이터가 들어갔는지 스크립트에서 직접 확인합니다.
        print("\n--- 저장된 데이터 확인 ---")
        cur.execute("SELECT title, author FROM books")
        for row in cur.fetchall():
            print(f"책 제목: {row[0]}, 저자: {row[1]}")
        print("------------------------")

    except oracledb.DatabaseError as e:
        print(f"❌ 데이터베이스 작업 중 오류 발생: {e}")
    finally:
        if conn:
            conn.close()
            print("\n데이터베이스 연결 해제 완료")

# 스크립트 실행
if __name__ == "__main__":
    insert_books()