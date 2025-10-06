import oracledb

conn = oracledb.connect(user="system", password="Asdf4156", dsn="localhost:1521/XEPDB1")
cur = conn.cursor()

def create_table(sql, name):
    try:
        cur.execute(sql)
        print(f"{name} 테이블 생성 완료")
    except oracledb.DatabaseError as e:
        error_obj, = e.args
        if error_obj.code == 955:  # ORA-00955: name already used
            print(f"{name} 테이블 이미 존재")
        else:
            raise

# 1. users
create_table("""
    CREATE TABLE users (
        user_id       VARCHAR2(30) PRIMARY KEY,
        password      VARCHAR2(200) NOT NULL,
        nickname      VARCHAR2(50) UNIQUE NOT NULL,
        email         VARCHAR2(100) UNIQUE NOT NULL,
        profile_image VARCHAR2(255),
        created_at    TIMESTAMP DEFAULT SYSTIMESTAMP
    )
""", "users")

# 2. followers
create_table("""
    CREATE TABLE followers (
        follower_id  VARCHAR2(30) REFERENCES users(user_id),
        following_id VARCHAR2(30) REFERENCES users(user_id),
        PRIMARY KEY (follower_id, following_id)
    )
""", "followers")

# 3. user_tags (관심 태그)
create_table("""
    CREATE TABLE user_tags (
        user_id VARCHAR2(30) REFERENCES users(user_id),
        tag     VARCHAR2(50),
        PRIMARY KEY (user_id, tag)
    )
""", "user_tags")

# 4. books (책 정보)
create_table("""
    CREATE TABLE books (
        book_id      VARCHAR2(20) PRIMARY KEY,  -- ISBN13
        isbn10       VARCHAR2(20),
        title        VARCHAR2(200) NOT NULL,
        author       VARCHAR2(200),
        publisher    VARCHAR2(200),
        published_at DATE,
        cover_image  VARCHAR2(255),
        description  CLOB,
        source       VARCHAR2(20),  -- aladin / naver
        created_at   TIMESTAMP DEFAULT SYSTIMESTAMP
    )
""", "books")

# 5. books_read (읽은 책)
create_table("""
    CREATE TABLE books_read (
        user_id  VARCHAR2(30) REFERENCES users(user_id),
        book_id  VARCHAR2(20) REFERENCES books(book_id),
        read_at  TIMESTAMP DEFAULT SYSTIMESTAMP,
        PRIMARY KEY (user_id, book_id)
    )
""", "books_read")

# 6. ratings (별점)
create_table("""
    CREATE TABLE ratings (
        user_id  VARCHAR2(30) REFERENCES users(user_id),
        book_id  VARCHAR2(20) REFERENCES books(book_id),
        rating   NUMBER(2,1) CHECK (rating BETWEEN 0.0 AND 5.0),
        PRIMARY KEY (user_id, book_id)
    )
""", "ratings")

# 7. reviews (짧은 리뷰)
create_table("""
    CREATE TABLE reviews (
        review_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        user_id     VARCHAR2(30) REFERENCES users(user_id),
        book_id     VARCHAR2(20) REFERENCES books(book_id),
        content     VARCHAR2(1000),
        created_at  TIMESTAMP DEFAULT SYSTIMESTAMP
    )
""", "reviews")

# 8. essays (긴 독후감)
create_table("""
    CREATE TABLE essays (
        essay_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        user_id    VARCHAR2(30) REFERENCES users(user_id),
        book_id    VARCHAR2(20) REFERENCES books(book_id),
        content    CLOB,
        created_at TIMESTAMP DEFAULT SYSTIMESTAMP
    )
""", "essays")

conn.commit()
cur.close()
conn.close()
print("모든 테이블 생성 완료")
