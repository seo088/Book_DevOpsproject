import oracledb

# Oracle 연결 설정 (Flask와 동일하게)
conn = oracledb.connect(
    user="system",
    password="Asdf4156",
    dsn="localhost:1521/XEPDB1"
)

with conn.cursor() as cur:
    cur.execute("SELECT user_id, password, nickname, email FROM users")
    rows = cur.fetchall()

    print("=== users 테이블 내용 ===")
    for r in rows:
        print(f"ID: {r[0]}, PASSWORD: {r[1][:40]}..., NICKNAME: {r[2]}, EMAIL: {r[3]}")

conn.close()
