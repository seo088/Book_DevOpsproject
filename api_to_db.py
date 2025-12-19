import requests
import oracledb
# ... (기존 import 및 TTB_KEY, DB 정보)

# ⭐️ 수정할 부분: query 변수를 사용자 입력으로 대체합니다.
# query = "책먹는 여우"  # 기존 코드 (주석 처리 또는 삭제)
TTB_KEY = "ttbtjdud07601928001" #API 키
query = input("검색할 책 제목을 입력하세요: ") # ⭐️ 새로운 검색어를 입력받습니다.

if not query:
    print("검색어가 입력되지 않아 작업을 종료합니다.")
    exit()

url = f"http://www.aladin.co.kr/ttb/api/ItemSearch.aspx?ttbkey={TTB_KEY}&Query={query}&QueryType=Title&MaxResults=2&start=1&SearchTarget=Book&output=JS&Version=20131101"


# 1. API 요청
response = requests.get(url)
data = response.json()

# 2. DB 연결
conn = oracledb.connect(user="system", password="0000", dsn="localhost:1521/XE")
cur = conn.cursor()

# 3. 도서 데이터 파싱 및 삽입
for item in data["item"]:
    book_id = item.get("isbn13")
    isbn10 = item.get("isbn")
    title = item.get("title")
    author = item.get("author")
    publisher = item.get("publisher")
    pubdate = item.get("pubDate", "")[:10]
    description = item.get("description", "")
    cover = item.get("cover")

    sql = """
        INSERT INTO books (book_id, isbn10, title, author, publisher, published_at, cover_image, description, source)
        VALUES (:1, :2, :3, :4, :5, TO_DATE(:6, 'YYYY-MM-DD'), :7, :8, :9)
    """

    try:
        cur.execute(sql, (book_id, isbn10, title, author, publisher, pubdate, cover, description, "aladin"))
        print(f"✅ '{title}' 추가 완료")
    except oracledb.IntegrityError:
        print(f"⚠️ '{title}' 이미 존재함")

conn.commit()
cur.close()
conn.close()
print("📚 모든 책 데이터 추가 완료!")