# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g
import oracledb
import requests
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import timedelta, datetime, date
from werkzeug.utils import secure_filename
import random
import string
import uuid
import re
from dotenv import load_dotenv
# app.py 상단 import 부분에 추가
from tag_data import TAG_DICT

# 1. .env 파일 로드
load_dotenv()

# --- Database Pool (연결 풀 설정) ---
# .env 파일에 DB_USER, DB_PASSWORD, DB_DSN이 설정되어 있어야 합니다.
pool = oracledb.create_pool(
    user=os.getenv("DB_USER", "system"),
    password=os.getenv("DB_PASSWORD", "Asdf4156"), 
    dsn=os.getenv("DB_DSN", "localhost:1521/freepdb1"),
    min=2,
    max=5,
    increment=1
)

# [수정됨] 연결 방식 통일: 하드코딩된 get_db_connection 제거하고 Pool 사용
def get_connection():
    return pool.acquire()

# --- [추가] 활동 로그 저장 헬퍼 함수 ---
def log_activity(conn, user_id, type, target_name, action):
    """
    conn: 현재 연결된 DB connection (또는 커서가 있는 컨텍스트)
    type: REVIEW, ESSAY, BOOKMARK, READ, FOLLOW
    target_name: 책 제목 또는 상대방 닉네임
    action: CREATE, DELETE
    """
    try:
        with conn.cursor() as cur:
            sql = """
                INSERT INTO activity_logs (user_id, type, target_name, action)
                VALUES (:1, :2, :3, :4)
            """
            cur.execute(sql, (user_id, type, target_name, action))
            # commit은 호출한 쪽에서 마지막에 한 번에 함
    except Exception as e:
        print(f"⚠️ 로그 저장 실패: {e}")

# --- [Helper] 문자열 안전하게 자르기 (ORA-12899 방지) ---
def safe_str(val, max_len=100):
    if not val: return ''
    val = str(val)
    if len(val) > max_len:
        return val[:max_len]
    return val

# --- Aladin Image Upscaler ---
def upscale_aladin_cover(url: str, base_size: int = 500) -> str:
    if not url: return url
    if f"/cover{base_size}/" in url or "cover600" in url or "cover800" in url: return url
    url = re.sub(r'/cover(sum|\d{2,3})/', f'/cover{base_size}/', url)
    url = url.replace("/coversum/", f"/cover{base_size}/")
    return url

# --- Flask App Setup ---
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_key_12345")
app.permanent_session_lifetime = timedelta(hours=5)

# TTB 키 설정
TTB_KEY = os.getenv("ALADIN_TTB_KEY", "ttbtjdud07601928001") 
MAX_RESULTS = 50

# 카카오 지도 API 키 (환경변수 권장, 없으면 하드코딩 값 사용)
KAKAO_JS_KEY = os.getenv("KAKAO_JS_KEY", "51138c0a012a0854928b066719ce62d9")

# 파일 업로드 경로
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# 전역 변수로 태그 캐시 저장
TAG_CACHE = None

# app.py 의 inject_tags 함수를 아래 코드로 교체하세요.

@app.context_processor
def inject_tags():
    global TAG_CACHE
    
    # 1. 전체 태그 로드 (기존 로직)
    if TAG_CACHE is None:
        grouped_tags = {}
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # 카테고리, 태그명 조회
                    sql = "SELECT category, tag_name FROM tags ORDER BY category, tag_name"
                    cur.execute(sql)
                    for category, tag_name in cur.fetchall():
                        if category not in grouped_tags:
                            grouped_tags[category] = []
                        grouped_tags[category].append(tag_name)
            TAG_CACHE = grouped_tags
        except Exception as e:
            print(f"Tag injection error: {e}")
            return dict(sidebar_tags={}) # 에러 시 빈 딕셔너리 반환

    # 2. [수정됨] 사이드바에 표시할 '장르' 카테고리만 필터링
    # 보여주고 싶은 카테고리 목록을 여기에 정의합니다.
    # ('감성/무드', '상황/추천', '책의 특징/수상' 제외)
    target_categories = [
        "소설/장르", 
        "인문/철학/심리", 
        "사회/과학", 
        "경제/경영/재테크", 
        "예술/대중문화", 
        "취미/라이프스타일", 
        "국가/지역"
    ]
    
    sidebar_tags = {}
    if TAG_CACHE:
        for cat in target_categories:
            if cat in TAG_CACHE:
                sidebar_tags[cat] = TAG_CACHE[cat]

    # sidebar_tags라는 이름으로 템플릿에 전달
    return dict(sidebar_tags=sidebar_tags)

def get_side_stats_from_db(user_id):
    stats = {'followers': 0, 'following': 0}
    if not user_id: return stats
    
    try:
        # with 문을 사용하면 자동으로 close(release) 됩니다.
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM followers WHERE following_id = :1", (user_id,))
                stats['followers'] = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM followers WHERE follower_id = :1", (user_id,))
                stats['following'] = cur.fetchone()[0]
    except Exception as e:
        print(f"❌ Error getting side stats: {e}")
        # DB 연결 실패 시 기본값(0,0) 반환
    return stats

# --- [Before Request] 전역 변수 g 설정 ---
@app.before_request
def setup_global_user():
    g.user_id = session.get('user_id')
    g.nickname = session.get('nickname')
    
    if g.user_id:
        g.side_stats = get_side_stats_from_db(g.user_id)
    else:
        g.side_stats = None

@app.context_processor
def inject_side_stats():
    return dict(side_stats=g.side_stats)


# --- Routes ---

@app.route("/")
def home():
    recommended_books = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    # 🟢 [수정] 출판사(publisher)와 실제 평점(avg_rating)을 조회하도록 쿼리 보강
                    sql = """
                        SELECT b.book_id, b.title, b.author, b.publisher, b.cover_image,
                               COALESCE(AVG(r.rating), 0) as avg_rating,
                               (COUNT(rv.review_id) * 0.05 * COALESCE(AVG(r.rating), 0)) AS final_weight
                        FROM books b
                        LEFT JOIN reviews rv ON b.book_id = rv.book_id
                        LEFT JOIN ratings r ON b.book_id = r.book_id
                        GROUP BY b.book_id, b.title, b.author, b.publisher, b.cover_image, b.published_at
                        ORDER BY final_weight DESC 
                        FETCH FIRST 4 ROWS ONLY
                    """
                    cur.execute(sql)
                    for row in cur.fetchall():
                        recommended_books.append({
                            "id": row[0], 
                            "title": row[1], 
                            "author": row[2],
                            "publisher": row[3], # 추가됨
                            "cover": upscale_aladin_cover(row[4]) if row[4] else None,
                            "rating": round(row[5], 1) # 평점 추가
                        })
                except oracledb.DatabaseError:
                    print("⚠️ 홈 화면: 아직 데이터가 부족하여 추천 로직을 건너뜁니다.")
    except Exception as e:
        print(f"❌ 추천 도서 조회 중 오류: {e}")
        
    return render_template("index.html", recommended_books=recommended_books)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if g.user_id: return redirect(url_for('home'))
    if request.method == "POST":
        user_id = request.form["user_id"]
        nickname = request.form["nickname"]
        email = request.form["email"]
        password = request.form["password"]
        password_confirm = request.form["password_confirm"]
        form_data = request.form.to_dict()

        if password != password_confirm:
            flash("비밀번호가 일치하지 않습니다.")
            return render_template("signup.html", form_data=form_data)

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM users WHERE user_id = :1 OR nickname = :2 OR email = :3", (user_id, nickname, email))
                    if cur.fetchone():
                        flash("이미 사용 중인 아이디/닉네임/이메일입니다.")
                        return render_template("signup.html", form_data=form_data)

                    hashed_pw = generate_password_hash(password, method="pbkdf2:sha256")
                    cur.execute("INSERT INTO users (user_id, password, nickname, email) VALUES (:1, :2, :3, :4)",
                                (user_id, hashed_pw, nickname, email))
                    conn.commit()
            flash("회원가입 완료! 로그인해주세요.")
            return redirect(url_for("login"))
        except Exception as e:
            flash(f"회원가입 중 오류: {e}")
            return redirect(url_for("signup"))

    return render_template("signup.html", form_data={})

@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user_id: return redirect(url_for('home'))
    if request.method == "POST":
        user_id = request.form["user_id"]
        password = request.form["password"]
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT password, nickname FROM users WHERE user_id = :1", (user_id,))
                    user = cur.fetchone()
                    if user and check_password_hash(user[0], password):
                        session["user_id"] = user_id
                        session["nickname"] = user[1]
                        session.permanent = True
                        return redirect(url_for("home"))
                    else:
                        flash("아이디 또는 비밀번호를 확인해주세요.")
                        return render_template("login.html", user_id=user_id)
        except Exception as e:
            flash(f"로그인 오류: {e}")
            return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("로그아웃 되었습니다.")
    return redirect(url_for("home"))

@app.route("/profile_edit", methods=["GET", "POST"])
def profile_edit():
    if not g.user_id: return redirect(url_for("login"))
    user_data_for_template = {}

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT nickname, email, profile_image, password FROM users WHERE user_id = :1", (g.user_id,))
                current_user_row = cur.fetchone()
                if not current_user_row:
                    flash("사용자 정보를 찾을 수 없습니다."); return redirect(url_for("home"))

                if request.method == "GET":
                    user_data_for_template = {"nickname": current_user_row[0], "email": current_user_row[1], "profile_image": current_user_row[2]}
                    return render_template("profile_edit.html", user=user_data_for_template)

                if request.method == "POST":
                    new_nickname = request.form["user_nickname"]
                    new_email = request.form["user_email"]
                    file = request.files.get("profile_image")
                    filename = None
                    db_pw = current_user_row[3]
                    user_data_for_template = {"nickname": new_nickname, "email": new_email, "profile_image": current_user_row[2]}

                    if file and file.filename:
                        try:
                            ext = os.path.splitext(file.filename)[1].lower()
                            if ext not in {'.png', '.jpg', '.jpeg', '.gif'}:
                                flash("허용되지 않는 파일 형식입니다.")
                                return render_template("profile_edit.html", user=user_data_for_template)

                            filename = f"{uuid.uuid4().hex}{ext}"
                            file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                            file.save(file_path)
                            user_data_for_template["profile_image"] = filename
                        except Exception as e:
                            print(f"❌ FAILED TO SAVE FILE: {e}")
                            flash(f"파일 저장 실패: {e}")
                            return render_template("profile_edit.html", user=user_data_for_template)
                    
                    if filename is None:
                        filename = current_user_row[2]

                    current_pw = request.form.get("current_pw", "")
                    new_pw = request.form.get("new_pw", "")
                    new_pw_confirm = request.form.get("new_pw_confirm", "")
                    password_changed = False
                    if new_pw or current_pw:
                        if not current_pw or not check_password_hash(db_pw, current_pw):
                            flash("현재 비밀번호가 올바르지 않습니다.")
                            return render_template("profile_edit.html", user=user_data_for_template)
                        if not new_pw or not new_pw_confirm:
                            flash("새 비밀번호와 확인 비밀번호를 입력해주세요.")
                            return render_template("profile_edit.html", user=user_data_for_template)
                        if new_pw != new_pw_confirm:
                            flash("새 비밀번호가 일치하지 않습니다.")
                            return render_template("profile_edit.html", user=user_data_for_template)
                        password_changed = True

                    update_fields = {"user_id": g.user_id}
                    update_sql_parts = []
                    
                    if new_nickname != current_user_row[0]:
                        update_fields["nickname"] = new_nickname; update_sql_parts.append("nickname = :nickname")
                    if new_email != current_user_row[1]:
                        update_fields["email"] = new_email; update_sql_parts.append("email = :email")
                    if filename != current_user_row[2]:
                        update_fields["profile_image"] = filename; update_sql_parts.append("profile_image = :profile_image")
                    if password_changed:
                        update_fields["password"] = generate_password_hash(new_pw, method="pbkdf2:sha256")
                        update_sql_parts.append("password = :password")

                    if update_sql_parts:
                        update_sql = f"UPDATE users SET {', '.join(update_sql_parts)} WHERE user_id = :user_id"
                        cur.execute(update_sql, update_fields)
                        conn.commit()
                        session["nickname"] = new_nickname
                        flash("프로필이 수정되었습니다.")
                    else:
                        flash("변경 사항이 없습니다.")
                    return redirect(url_for("mypage"))

    except Exception as e:
        flash(f"프로필 수정 오류: {e}"); print(f"❌ Profile edit error: {e}")
        return redirect(url_for("mypage"))

@app.route("/find_password", methods=["GET"])
def find_password():
    return render_template("find_password.html")

@app.route("/find_password_post", methods=["POST"])
def find_password_post():
    user_id = request.form["user_id"]
    user_email = request.form["user_email"]
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM users WHERE user_id = :1 AND email = :2", (user_id, user_email))
                if not cur.fetchone():
                    flash("일치하는 사용자를 찾을 수 없습니다.")
                    return redirect(url_for("find_password"))
                
                temp_pw = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
                hashed_pw = generate_password_hash(temp_pw, method="pbkdf2:sha256")
                cur.execute("UPDATE users SET password = :1 WHERE user_id = :2", (hashed_pw, user_id))
                conn.commit()
                flash("임시 비밀번호가 발급되었습니다. (로그 확인)")
                print(f"임시 비밀번호 [{user_id}]: {temp_pw}")
                return redirect(url_for("login"))
    except Exception as e:
        flash(f"비밀번호 찾기 오류: {e}"); print(f"❌ Error in find_password_post: {e}")
        return redirect(url_for("find_password"))

@app.route("/mypage")
def mypage():
    if not g.user_id: return redirect(url_for("login"))
    
    user_data = {
        "id": g.user_id, "nickname": g.nickname, "email": "정보 없음", 
        "profile_image": None, "read_count": 0, "tags": [],
        "visibility_review": "PUBLIC", "visibility_essay": "PUBLIC", 
        "visibility_bookmark": "PUBLIC", "visibility_follow": "PUBLIC"
    }
    
    # 🟢 [수정] 변수 초기화 (recent_essays 추가)
    recent_bookmarks = []
    recent_read_books = []
    recent_reviews = []
    recent_essays = [] # 독후감 리스트
    activities = []
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # 1. 유저 정보 조회
                cur.execute("""
                    SELECT user_id, nickname, email, profile_image, 
                           visibility_review, visibility_essay, visibility_bookmark, visibility_follow
                    FROM users WHERE user_id = :1
                """, (g.user_id,))
                row = cur.fetchone()
                if row:
                    user_data["id"] = row[0]; user_data["nickname"] = row[1]
                    user_data["email"] = row[2]; user_data["profile_image"] = row[3]
                    user_data["visibility_review"] = row[4] or "PUBLIC"
                    user_data["visibility_essay"] = row[5] or "PUBLIC"
                    user_data["visibility_bookmark"] = row[6] or "PUBLIC"
                    user_data["visibility_follow"] = row[7] or "PUBLIC"

                # 2. 읽은 책 카운트
                try:
                    cur.execute("SELECT COUNT(*) FROM books_read WHERE user_id = :1", (g.user_id,))
                    user_data["read_count"] = cur.fetchone()[0]
                except: pass

                # 3. 북마크 (최근 4개)
                try:
                    sql_bookmark = """SELECT b.book_id, b.title, b.author, b.publisher, b.cover_image,
                               (SELECT COALESCE(AVG(r.rating), 0) FROM ratings r WHERE r.book_id = b.book_id) as avg_rating
                        FROM books b JOIN bookmarks bm ON b.book_id = bm.book_id 
                        WHERE bm.user_id = :1 ORDER BY bm.added_at DESC FETCH FIRST 4 ROWS ONLY"""
                    cur.execute(sql_bookmark, (g.user_id,))
                    for row in cur.fetchall():
                        recent_bookmarks.append({"id": row[0], "title": row[1], "author": row[2], "publisher": row[3], "cover": upscale_aladin_cover(row[4]), "avg_rating": round(row[5], 1)})
                except: pass

                # 4. [수정] 내가 쓴 리뷰 (최근 3개) - ratings 테이블과 조인하여 평점 가져오기
                try:
                    sql_review = """
                        SELECT r.book_id, b.title, r.content, 
                               COALESCE(rt.rating, 0) as rating, -- ratings 테이블에서 가져옴
                               r.created_at, b.cover_image
                        FROM reviews r
                        JOIN books b ON r.book_id = b.book_id
                        LEFT JOIN ratings rt ON r.book_id = rt.book_id AND r.user_id = rt.user_id
                        WHERE r.user_id = :1
                        ORDER BY r.created_at DESC
                        FETCH FIRST 3 ROWS ONLY
                    """
                    cur.execute(sql_review, (g.user_id,))
                    for row in cur.fetchall():
                        # CLOB 타입 처리 (긴 텍스트 읽기)
                        content_val = row[2].read() if hasattr(row[2], 'read') else str(row[2])
                        
                        recent_reviews.append({
                            "book_id": row[0], 
                            "title": row[1], 
                            "content": content_val, 
                            "rating": row[3],      # 평점
                            "created_at": row[4].strftime('%Y.%m.%d'),
                            "cover": upscale_aladin_cover(row[5])
                        })
                except Exception as e:
                    print(f"❌ Review fetch error: {e}")

                # 5. 🟢 [추가] 내가 쓴 독후감 (최근 3개)
                try:
                    # DBMS_LOB.SUBSTR을 사용하여 CLOB 내용을 문자열로 잘라서 가져옴 (오류 방지)
                    sql_essay = """
                        SELECT e.essay_id, e.book_id, b.title, DBMS_LOB.SUBSTR(e.content, 100, 1), e.created_at, b.cover_image
                        FROM essays e
                        JOIN books b ON e.book_id = b.book_id
                        WHERE e.user_id = :1
                        ORDER BY e.created_at DESC
                        FETCH FIRST 3 ROWS ONLY
                    """
                    cur.execute(sql_essay, (g.user_id,))
                    for row in cur.fetchall():
                        recent_essays.append({
                            "essay_id": row[0], "book_id": row[1], "title": row[2], 
                            "excerpt": row[3], # SQL에서 이미 잘라옴
                            "created_at": row[4].strftime('%Y.%m.%d'),
                            "cover": upscale_aladin_cover(row[5])
                        })
                except Exception as e:
                    print(f"❌ Essay fetch error: {e}")

                # 6. 읽은 책 (기존 로직)
                try:
                    sql_read = """SELECT b.book_id, b.title, b.author, b.publisher, b.cover_image,
                               (SELECT rating FROM ratings r WHERE r.book_id = b.book_id AND r.user_id = :1) as my_rating,
                               (SELECT COUNT(*) FROM essays es WHERE es.book_id = b.book_id AND es.user_id = :2) as has_essay,
                               (SELECT COUNT(*) FROM reviews rv WHERE rv.book_id = b.book_id AND rv.user_id = :3) as has_review
                        FROM books b JOIN books_read br ON b.book_id = br.book_id WHERE br.user_id = :4
                        ORDER BY br.read_at DESC FETCH FIRST 4 ROWS ONLY"""
                    cur.execute(sql_read, (g.user_id, g.user_id, g.user_id, g.user_id))
                    for row in cur.fetchall():
                        recent_read_books.append({
                            "id": row[0], "title": row[1], "author": row[2], "publisher": row[3], "cover": upscale_aladin_cover(row[4]),
                            "rating": round(row[5], 1) if row[5] is not None else None, "has_essay": bool(row[6]), "has_review": bool(row[7])
                        })
                except: pass

                # 7. 활동 로그
                try:
                    sql_activity = """
                        SELECT type, target_name, action, created_at 
                        FROM activity_logs WHERE user_id = :1 
                        ORDER BY created_at DESC FETCH FIRST 30 ROWS ONLY
                    """
                    cur.execute(sql_activity, (g.user_id,))
                    for row in cur.fetchall():
                        act_type = row[0]; target = row[1]; action = row[2]
                        act_date = row[3].strftime('%Y-%m-%d %H:%M')
                        icon = "fas fa-circle"; text = ""
                        
                        if action == 'CREATE':
                            if act_type == 'REVIEW': icon="fas fa-star"; text=f"<strong>{target}</strong> 책에 <u>리뷰</u>를 남겼습니다."
                            elif act_type == 'ESSAY': icon="fas fa-pen-fancy"; text=f"<strong>{target}</strong> 책의 <u>독후감</u>을 작성했습니다."
                            elif act_type == 'BOOKMARK': icon="fas fa-bookmark"; text=f"<strong>{target}</strong> 책을 <u>북마크</u>했습니다."
                            elif act_type == 'READ': icon="fas fa-book-open"; text=f"<strong>{target}</strong> 책을 <u>읽은 책</u>으로 등록했습니다."
                            elif act_type == 'FOLLOW': icon="fas fa-user-plus"; text=f"<strong>{target}</strong> 님을 <u>팔로우</u>했습니다."
                        elif action == 'DELETE':
                            icon="fas fa-trash-alt"
                            if act_type == 'FOLLOW': text=f"<strong>{target}</strong> 님을 <span style='color:#999'>언팔로우</span>했습니다."
                            else: text=f"<strong>{target}</strong> 관련 기록({act_type})을 삭제했습니다."

                        activities.append({"icon": icon, "text": text, "date": act_date, "type": act_type})
                except: pass

    except Exception as e:
        flash(f"정보 조회 오류: {e}"); print(f"❌ Mypage error: {e}")
    
    # 🟢 [수정] essays=recent_essays 추가됨
    return render_template("mypage.html", user=user_data, bookmarks=recent_bookmarks, read_books=recent_read_books, 
                           reviews=recent_reviews, essays=recent_essays, activities=activities)

@app.route("/search")
def search_books():
    # 1. 파라미터 받기 (is_tag_search 삭제, genre 추가)
    query = request.args.get("search_query", "").strip()
    genre_filter = request.args.get("genre", "").strip()

    # 아무것도 입력/선택 안 했으면 홈으로
    if not query and not genre_filter:
        return redirect(url_for("home"))
    
    # 2. 알라딘 API 실시간 수집 (텍스트 검색어가 있을 때만 실행)
    # 장르 클릭만 했을 때는 DB에 있는 데이터만 보여주는 것이 필터의 역할에 충실합니다.
    if query:
        try:
            search_url = "https://www.aladin.co.kr/ttb/api/ItemSearch.aspx"
            params = {
                'ttbkey': TTB_KEY,
                'Query': query,
                'QueryType': 'Keyword',
                'MaxResults': 20,
                'start': 1,
                'SearchTarget': 'Book',
                'output': 'JS',
                'Version': '20131101'
            }
            res = requests.get(search_url, params=params)
            api_data = res.json().get('item', [])

            with get_connection() as conn:
                with conn.cursor() as cur:
                    for item in api_data:
                        isbn = item.get('isbn13')
                        if not isbn: continue
                        cur.execute("SELECT 1 FROM books WHERE book_id = :1", (isbn,))
                        if not cur.fetchone():
                            pub_date = None
                            if item.get('pubDate'):
                                try: pub_date = datetime.strptime(item.get('pubDate'), '%Y-%m-%d').date()
                                except: pass
                            
                            cur.execute("""
                                INSERT INTO books (book_id, title, author, publisher, published_at, cover_image, description, source)
                                VALUES (:1, :2, :3, :4, :5, :6, :7, 'aladin')
                            """, (isbn, safe_str(item.get('title'), 200), safe_str(item.get('author'), 60), 
                                  safe_str(item.get('publisher'), 60), pub_date, item.get('cover'), item.get('description')))
                            
                            analyze_and_save_tags(conn, isbn, item.get('title'), item.get('description'))
                    conn.commit()
        except Exception as e:
            print(f"⚠️ 알라딘 실시간 수집 실패 (DB 검색으로 대체): {e}")

    # 3. DB에서 최종 결과 조회 (필터 + 검색어 조합)
    results = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # 기본 SELECT 문
                sql = """
                    SELECT DISTINCT b.book_id, b.title, b.author, b.publisher, b.cover_image, b.published_at,
                           (SELECT COALESCE(AVG(rating), 0) FROM ratings r WHERE r.book_id = b.book_id) as avg_rating
                    FROM books b
                """
                where_clauses = []
                params = {}

                # [필터] 장르가 선택된 경우 JOIN 추가
                if genre_filter:
                    sql += " JOIN book_tags bt ON b.book_id = bt.book_id JOIN tags t ON bt.tag_id = t.tag_id "
                    where_clauses.append("t.tag_name = :genre")
                    params['genre'] = genre_filter

                # [검색어] 검색어가 입력된 경우 WHERE 조건 추가
                if query:
                    # 제목, 저자, 출판사, 설명에서 검색
                    where_clauses.append("(b.title LIKE :q OR b.author LIKE :q OR b.publisher LIKE :q OR DBMS_LOB.SUBSTR(b.description, 1000, 1) LIKE :q)")
                    params['q'] = f"%{query}%"

                if where_clauses:
                    sql += " WHERE " + " AND ".join(where_clauses)

                sql += " ORDER BY avg_rating DESC"
                
                cur.execute(sql, params)
                
                for row in cur.fetchall():
                    pub_date_str = row[5].strftime('%Y-%m-%d') if row[5] and hasattr(row[5], 'strftime') else str(row[5] or '')[:10]
                    results.append({
                        "id": row[0], "title": row[1], "author": row[2], "publisher": row[3],
                        "cover": upscale_aladin_cover(row[4]), "pubDate": pub_date_str,
                        "rating": round(row[6], 1)
                    })
    except Exception as e:
        print(f"❌ DB 조회 에러: {e}")
        flash("검색 결과를 가져오는 중 오류가 발생했습니다.")

    # 4. 결과 페이지로 데이터 전송
    return render_template("search_results.html", 
                           books=results, 
                           query=query, 
                           current_genre=genre_filter)

@app.route('/bestseller')
def bestseller():
    bestseller_books = []; total_count = 0; conn = None
    my_bookmarks = set(); my_read_books = set()
    
    try:
        conn = get_connection(); cur = conn.cursor()
        try:
            if g.user_id:
                cur.execute("SELECT book_id FROM bookmarks WHERE user_id = :1", (g.user_id,))
                my_bookmarks = {row[0] for row in cur.fetchall()}
                cur.execute("SELECT book_id FROM books_read WHERE user_id = :1", (g.user_id,))
                my_read_books = {row[0] for row in cur.fetchall()}
        except oracledb.DatabaseError:
            pass 

        url = "https://www.aladin.co.kr/ttb/api/ItemList.aspx"
        params = {'ttbkey': TTB_KEY, 'QueryType': 'Bestseller', 'MaxResults': 50, 'start': 1, 'SearchTarget': 'Book', 'output': 'JS', 'Version': '20131101'}
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        api_results = response.json().get("item", [])
        
        for book_data in api_results:
            isbn13 = book_data.get('isbn13')
            if not isbn13: continue
            
            try:
                cur.execute("SELECT COALESCE(AVG(rating), 0.0) FROM ratings WHERE book_id = :1", (isbn13,))
                rating_result = cur.fetchone()
                site_rating = float(round(rating_result[0], 1)) if rating_result else 0.0
            except: site_rating = 0.0
            
            bestseller_books.append({
                "id": isbn13, "title": book_data.get('title'), "author": book_data.get('author', ''),
                "publisher": book_data.get('publisher', ''), "cover": upscale_aladin_cover(book_data.get('cover', '')),
                "description": book_data.get('description', ''), "pub_date_full": book_data.get('pubDate', '')[:10],
                "fox_rating": site_rating, "priceStandard": book_data.get('priceStandard'),
                "is_bookmarked": isbn13 in my_bookmarks, "is_read": isbn13 in my_read_books
            })
        total_count = len(bestseller_books)
    except Exception as e:
        flash(f"베스트셀러 오류: {e}"); print(f"❌ Bestseller error: {e}")
    finally:
        if conn:
            pool.release(conn)
    return render_template('bestseller.html', books=bestseller_books, count=total_count)

@app.route('/new-releases')
def new_releases():
    new_release_books = []; total_count = 0; conn = None
    my_bookmarks = set(); my_read_books = set()

    try:
        conn = get_connection(); cur = conn.cursor()
        try:
            if g.user_id:
                cur.execute("SELECT book_id FROM bookmarks WHERE user_id = :1", (g.user_id,))
                my_bookmarks = {row[0] for row in cur.fetchall()}
                cur.execute("SELECT book_id FROM books_read WHERE user_id = :1", (g.user_id,))
                my_read_books = {row[0] for row in cur.fetchall()}
        except: pass

        url = "https://www.aladin.co.kr/ttb/api/ItemList.aspx"
        params = {'ttbkey': TTB_KEY, 'QueryType': 'ItemNewAll', 'MaxResults': 50, 'start': 1, 'SearchTarget': 'Book', 'output': 'JS', 'Version': '20131101'}
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        api_results = response.json().get("item", [])
        today = date.today()

        for book_data in api_results:
            pub_date_str = book_data.get('pubDate', '')[:10]
            try: publish_date = datetime.strptime(pub_date_str, '%Y-%m-%d').date()
            except: continue
            if publish_date > today: continue 

            isbn13 = book_data.get('isbn13')
            new_release_books.append({
                 "id": isbn13, "title": book_data.get('title'), "author": book_data.get('author', ''),
                 "publisher": book_data.get('publisher', ''), "cover": upscale_aladin_cover(book_data.get('cover', '')),
                 "description": book_data.get('description', ''), "pub_date_full": pub_date_str,
                 "is_bookmarked": isbn13 in my_bookmarks, "is_read": isbn13 in my_read_books
             })
        new_release_books.sort(key=lambda x: x.get('pub_date_full', ''), reverse=True)
        total_count = len(new_release_books)
    except Exception as e:
        flash(f"신작 오류: {e}"); print(f"❌ New release error: {e}")
    finally:
        if conn:
            pool.release(conn)
    return render_template('new_releases.html', books=new_release_books, count=total_count)

@app.route('/book/<string:book_isbn>')
def book_detail(book_isbn):
    book_info = None; reviews_list = []; avg_rating = 0.0; conn = None
    is_bookmarked = False; is_read = False
    user_data = {"nickname": g.nickname, "email": "정보 없음", "profile_image": None} if g.user_id else {}

    try:
        conn = get_connection()
        url = "https://www.aladin.co.kr/ttb/api/ItemLookUp.aspx"
        params = {'ttbkey': TTB_KEY, 'itemIdType': 'ISBN13', 'ItemId': book_isbn, 'output': 'JS', 'Version': '20131101', 'Cover': 'Big', 'OptResult': 'usedList,reviewList'}
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        items = response.json().get("item", [])
        
        if items:
            book_info = items[0]
            book_info["cover"] = upscale_aladin_cover(book_info.get("cover", ""))
            book_info["aladin_rating"] = round(book_info.get('customerReviewRank', 0) / 2.0, 1)
            
            try:
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM books WHERE book_id = :1", (book_isbn,))
                if not cur.fetchone():
                    pub_date = datetime.strptime(book_info.get('pubDate', ''), '%Y-%m-%d').date() if book_info.get('pubDate') else None
                    
                    safe_title = safe_str(book_info.get('title'), 200)
                    safe_author = safe_str(book_info.get('author'), 60)
                    safe_pub = safe_str(book_info.get('publisher'), 60)

                    cur.execute("""INSERT INTO books (book_id, isbn10, title, author, publisher, published_at, cover_image, description, source) 
                                   VALUES (:1, :2, :3, :4, :5, :6, :7, :8, 'aladin')""",
                                (book_isbn, book_info.get('isbn'), safe_title, safe_author,
                                safe_pub, pub_date, book_info.get('cover'), book_info.get('description', '')))
                    analyze_and_save_tags(conn, book_isbn, safe_title, book_info.get('description', ''))
                    conn.commit()
            except Exception as db_e: print(f"❌ Book insert error: {db_e}")

            cur = conn.cursor()
            try:
                cur.execute("SELECT COALESCE(AVG(rating), 0.0) FROM ratings WHERE book_id = :1", (book_isbn,))
                rating_result = cur.fetchone(); avg_rating = float(round(rating_result[0], 1)) if rating_result else 0.0
                
                cur.execute("""
                    SELECT rv.content, rv.created_at, u.nickname, r.rating, u.user_id
                    FROM reviews rv 
                    JOIN users u ON rv.user_id = u.user_id 
                    LEFT JOIN ratings r ON rv.user_id = r.user_id AND rv.book_id = r.book_id
                    WHERE rv.book_id = :1 ORDER BY rv.created_at DESC FETCH FIRST 10 ROWS ONLY
                """, (book_isbn,))
                
                for row in cur.fetchall(): 
                    reviews_list.append({"content": row[0], "created_at": row[1].strftime('%Y.%m.%d'), "nickname": row[2], "rating": row[3] if row[3] else 0.0, "user_id": row[4]})
            except: pass 
            
            if g.user_id:
                try:
                    cur.execute("SELECT 1 FROM bookmarks WHERE user_id = :1 AND book_id = :2", (g.user_id, book_isbn))
                    if cur.fetchone(): is_bookmarked = True
                    cur.execute("SELECT 1 FROM books_read WHERE user_id = :1 AND book_id = :2", (g.user_id, book_isbn))
                    if cur.fetchone(): is_read = True
                except: pass

        else:
             try:
                if not conn: conn = get_connection()
                cur = conn.cursor()
                cur.execute("SELECT * FROM books WHERE book_id = :1", (book_isbn,))
                db_book = cur.fetchone()
                if db_book:
                     book_info = {"isbn13": db_book[0], "title": db_book[2], "author": db_book[3], "publisher": db_book[4],
                                  "pubDate": db_book[5].strftime('%Y-%m-%d') if db_book[5] else '',
                                  "cover": upscale_aladin_cover(db_book[6]), "description": db_book[7], "aladin_rating": 0 }
                     if g.user_id:
                         try:
                             cur.execute("SELECT 1 FROM bookmarks WHERE user_id = :1 AND book_id = :2", (g.user_id, book_isbn))
                             if cur.fetchone(): is_bookmarked = True
                             cur.execute("SELECT 1 FROM books_read WHERE user_id = :1 AND book_id = :2", (g.user_id, book_isbn))
                             if cur.fetchone(): is_read = True
                         except: pass
                else: flash("책 정보를 찾을 수 없습니다.")
             except: pass

    except Exception as e:
        flash(f"책 상세 오류: {e}"); print(f"❌ Book detail error: {e}")
        book_info = {}
    finally:
         if conn:
             pool.release(conn)
    book_tags_list = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                sql_tags = """
                    SELECT t.tag_name 
                    FROM tags t 
                    JOIN book_tags bt ON t.tag_id = bt.tag_id 
                    WHERE bt.book_id = :1
                """
                cur.execute(sql_tags, (book_isbn,))
                book_tags_list = [row[0] for row in cur.fetchall()]
    except Exception as e:
        print(f"Error fetching book tags: {e}")

    # [수정] render_template에 book_tags=book_tags_list 추가
    return render_template('book_detail.html', 
                           book=book_info or {}, 
                           reviews=reviews_list, 
                           avg_rating=avg_rating, 
                           user=user_data, 
                           is_bookmarked=is_bookmarked, 
                           is_read=is_read,
                           book_tags=book_tags_list) # 이 부분 추가!

@app.route('/read-books')
def books_read_list():
    if not g.user_id: return redirect(url_for('login'))
    read_books_data = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT b.book_id, b.title, b.author, b.cover_image, r.rating, br.read_at,
                           (SELECT COUNT(*) FROM essays es WHERE es.book_id = b.book_id AND es.user_id = br.user_id) as has_essay,
                           (SELECT COUNT(*) FROM reviews rv WHERE rv.book_id = b.book_id AND rv.user_id = br.user_id) as has_review
                    FROM books b JOIN books_read br ON b.book_id = br.book_id
                    LEFT JOIN ratings r ON b.book_id = r.book_id AND br.user_id = r.user_id
                    WHERE br.user_id = :1 ORDER BY br.read_at DESC
                """, (g.user_id,))
                for row in cur.fetchall():
                    read_books_data.append({
                        "id": row[0], "title": row[1], "author": row[2],
                        "cover": upscale_aladin_cover(row[3]) if row[3] else None,
                        "rating": round(row[4], 1) if row[4] is not None else None,
                        "read_at": row[5].strftime('%Y.%m.%d') if row[5] else "날짜 미상",
                        "has_essay": bool(row[6]), "has_review": bool(row[7])
                    })
    except Exception as e: flash("읽은 책 목록 오류"); print(f"❌ Error in books_read_list: {e}")
    return render_template('books_read.html', books=read_books_data)

@app.route('/essay/<string:book_id>', methods=['GET', 'POST'])
def essay_detail(book_id):
    if not g.user_id: return redirect(url_for('login'))
    book_info = {}; essay_data = {}; conn = None
    user_data = {"nickname": g.nickname}

    if request.method == 'POST':
        essay_title = request.form.get('essay_title')
        essay_content = request.form.get('essay_content')
        is_public = 'Y' if request.form.get('is_public') else 'N'

        if essay_content:
            try:
                conn = get_connection(); cur = conn.cursor()
                cur.execute("SELECT essay_id FROM essays WHERE user_id = :1 AND book_id = :2", (g.user_id, book_id))
                exists = cur.fetchone()
                if exists:
                      cur.execute("UPDATE essays SET title = :1, content = :2, is_public = :3, created_at = SYSTIMESTAMP WHERE essay_id = :4", (essay_title, essay_content, is_public, exists[0]))
                else:
                      cur.execute("INSERT INTO essays (user_id, book_id, title, content, is_public) VALUES (:1, :2, :3, :4, :5)", (g.user_id, book_id, essay_title, essay_content, is_public))
                log_activity(conn, g.user_id, 'ESSAY', book_info['title'], 'CREATE')
                conn.commit()
                flash("독후감이 저장되었습니다.")
                return redirect(url_for('essays_list'))
            except Exception as e: 
                flash(f"저장 오류: {e}"); print(f"❌ Essay save error: {e}")
            finally: 
                if conn:
                    pool.release(conn)
    
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SELECT title, author, cover_image FROM books WHERE book_id = :1", (book_id,))
        row = cur.fetchone()
        if row: book_info = {'title': row[0], 'author': row[1], 'cover': upscale_aladin_cover(row[2]) if row[2] else None}
        cur.execute("SELECT essay_id, title, content, is_public FROM essays WHERE user_id = :1 AND book_id = :2", (g.user_id, book_id))
        row = cur.fetchone()
        if row: 
            essay_data = {'id': row[0], 'title': row[1], 'content': row[2], 'is_public': (row[3] == 'Y')}
    except Exception as e: 
        flash(f"조회 오류: {e}"); print(f"❌ Essay get error: {e}")
    finally: 
        if conn:
            pool.release(conn)
    return render_template('essay_detail.html', book_info=book_info, essay=essay_data, book_id=book_id, user=user_data)

@app.route('/my-essays')
def essays_list():
    if not g.user_id: return redirect(url_for('login'))
    sort_by = request.args.get('sort', 'latest')
    order = "e.created_at DESC" if sort_by == 'latest' else "b.title ASC"
    my_essays = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                sql = f"""
                    SELECT e.essay_id, b.title AS book_title, b.book_id, e.created_at, DBMS_LOB.SUBSTR(e.content, 100, 1) as content_preview
                    FROM essays e JOIN books b ON e.book_id = b.book_id 
                    WHERE e.user_id = :1 ORDER BY {order}
                """
                cur.execute(sql, (g.user_id,))
                for row in cur.fetchall():
                    raw_content = row[4] if row[4] else ""
                    excerpt = (raw_content[:15] + "...") if len(raw_content) > 15 else (raw_content if raw_content else "내용 없음")
                    my_essays.append({"essay_id": row[0], "book_title": row[1], "book_id": row[2], "created_at": row[3].strftime('%Y.%m.%d'), "excerpt": excerpt})
    except Exception as e: flash("목록 오류"); print(f"❌ Essay list error: {e}")
    return render_template('essays_list.html', essays=my_essays, sort_option=sort_by)

@app.route('/my-reviews')
def reviews_list():
    if not g.user_id: return redirect(url_for('login'))
    sort_by = request.args.get('sort', 'latest')
    order_clause = "r.rating DESC NULLS LAST, display_date DESC" if sort_by == 'rating' else "display_date DESC"
    my_reviews = []; count = 0
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                sql = f"""
                    SELECT rv.review_id, b.title, b.author, b.cover_image, r.rating, rv.content, COALESCE(rv.created_at, br.read_at) as display_date
                    FROM books_read br JOIN books b ON br.book_id = b.book_id
                    JOIN ratings r ON br.book_id = r.book_id AND br.user_id = r.user_id
                    LEFT JOIN reviews rv ON br.book_id = rv.book_id AND br.user_id = rv.user_id
                    WHERE br.user_id = :1 ORDER BY {order_clause}
                """
                cur.execute(sql, (g.user_id,))
                for row in cur.fetchall():
                    my_reviews.append({
                        "review_id": row[0], "book_title": row[1], "book_author": row[2] or '',
                        "book_cover": upscale_aladin_cover(row[3]) if row[3] else None, 
                        "rating": round(row[4], 1) if row[4] is not None else 0.0, 
                        "content": row[5] if row[5] else "", "created_at": row[6].strftime('%Y.%m.%d') if row[6] else "날짜 미상"
                    })
                count = len(my_reviews)
    except Exception as e: flash("목록 오류"); print(f"❌ Review list error: {e}")
    return render_template('reviews_list.html', reviews=my_reviews, count=count, sort_option=sort_by)

@app.route('/bookmarks')
def bookmarks_list():
    if not g.user_id: return redirect(url_for('login'))
    bookmarks_data = []; count = 0; sort_by = request.args.get('sort', 'latest_added')
    order = "bm.added_at DESC" if sort_by == 'latest_added' else "b.title ASC"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                sql = f"""SELECT b.book_id, b.title, b.author, b.publisher, b.cover_image, bm.added_at
                          FROM books b JOIN bookmarks bm ON b.book_id = bm.book_id
                          WHERE bm.user_id = :1 ORDER BY {order}"""
                cur.execute(sql, (g.user_id,))
                for row in cur.fetchall():
                    bookmarks_data.append({
                        "id": row[0], "title": row[1], "author": row[2], "publisher": row[3],
                        "cover": upscale_aladin_cover(row[4]), "added_at": row[5].strftime('%Y.%m.%d')
                    })
                count = len(bookmarks_data)
    except Exception as e: flash("북마크 오류"); print(f"❌ Bookmark list error: {e}")
    return render_template('bookmarks_list.html', bookmarks=bookmarks_data, count=count, sort_option=sort_by)

@app.route('/bookmark/add/<string:book_isbn>', methods=['POST'])
def add_bookmark(book_isbn):
    if not g.user_id: return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401
    conn = None
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SELECT 1 FROM books WHERE book_id = :1", (book_isbn,))
        if not cur.fetchone():
            try:
                url = "https://www.aladin.co.kr/ttb/api/ItemLookUp.aspx"
                params = {'ttbkey': TTB_KEY, 'itemIdType': 'ISBN13', 'ItemId': book_isbn, 'output': 'JS', 'Version': '20131101', 'Cover': 'Big'}
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(url, params=params, headers=headers); response.raise_for_status()
                items = response.json().get("item", [])
                if items:
                    book_info = items[0]
                    pub_date = datetime.strptime(book_info.get('pubDate'), '%Y-%m-%d').date() if book_info.get('pubDate') else None
                    
                    safe_title = safe_str(book_info.get('title'), 200)
                    safe_author = safe_str(book_info.get('author'), 60)
                    safe_pub = safe_str(book_info.get('publisher'), 60)

                    cur.execute("""INSERT INTO books (book_id, isbn10, title, author, publisher, published_at, cover_image, description, source) 
                                   VALUES (:1, :2, :3, :4, :5, :6, :7, :8, 'aladin')""",
                                (book_isbn, book_info.get('isbn'), safe_title, safe_author,
                                safe_pub, pub_date, upscale_aladin_cover(book_info.get('cover')), book_info.get('description', '')))
                else: return jsonify({'success': False, 'message': '책 정보를 찾을 수 없습니다.'}), 404
            except Exception as e: print(f"❌ API Error: {e}"); return jsonify({'success': False, 'message': 'API 오류'}), 500

        cur.execute("INSERT INTO bookmarks (user_id, book_id) VALUES (:1, :2)", (g.user_id, book_isbn))
        cur.execute("SELECT title FROM books WHERE book_id = :1", (book_isbn,))
        t_row = cur.fetchone()
        title = t_row[0] if t_row else "책"

        log_activity(conn, g.user_id, 'BOOKMARK', title, 'CREATE') # 🟢 추가
        conn.commit()
        return jsonify({'success': True, 'message': '북마크에 추가되었습니다.'})
    except oracledb.DatabaseError as e:
        if e.args[0].code == 1: return jsonify({'success': False, 'message': '이미 추가된 책입니다.'}), 409
        return jsonify({'success': False, 'message': 'DB 오류'}), 500
    except Exception as e: return jsonify({'success': False, 'message': '서버 오류'}), 500
    finally: 
        if conn:
            pool.release(conn)

@app.route("/bookmark/delete/<string:book_isbn>", methods=["POST"])
def delete_bookmark(book_isbn):
    if not g.user_id:
        return jsonify({"success": False, "message": "로그인 필요"}), 401
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # 1. 책 제목 먼저 조회 (로그 저장용) - 🟢 순서 중요!
                cur.execute("SELECT title FROM books WHERE book_id = :1", (book_isbn,))
                row = cur.fetchone()
                book_title = row[0] if row else "알 수 없는 책"

                # 2. 북마크 삭제 수행
                cur.execute("DELETE FROM bookmarks WHERE user_id = :1 AND book_id = :2", (g.user_id, book_isbn))
                
                # 3. 로그 저장
                log_activity(conn, g.user_id, 'BOOKMARK', book_title, 'DELETE')
                
                conn.commit()
                return jsonify({"success": True})
                
    except Exception as e:
        print(f"❌ Delete bookmark error: {e}")
        return jsonify({"success": False, "message": "삭제 실패"}), 500

@app.route("/mark-read/<string:book_isbn>", methods=["POST"])
def mark_as_read(book_isbn):
    if not g.user_id:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401
        
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # 1. 책 제목 먼저 조회 (로그 저장용 + 존재 여부 확인)
                # ORA-02291 에러 방지를 위해 책이 있는지 먼저 확인합니다.
                cur.execute("SELECT title FROM books WHERE book_id = :1", (book_isbn,))
                row = cur.fetchone()
                
                if not row:
                    # 책이 DB에 없는 경우 (드문 경우이나, 추천 목록 등에서 발생 가능)
                    return jsonify({"success": False, "message": "도서 정보를 찾을 수 없습니다."}), 404
                
                book_title = row[0]

                # 2. 이미 읽은 책인지 확인
                cur.execute("SELECT 1 FROM books_read WHERE user_id = :1 AND book_id = :2", (g.user_id, book_isbn))
                exists = cur.fetchone()

                if exists:
                    # 삭제 (읽은 책 취소)
                    cur.execute("DELETE FROM books_read WHERE user_id = :1 AND book_id = :2", (g.user_id, book_isbn))
                    # 🟢 [수정] 위에서 구한 book_title 사용
                    log_activity(conn, g.user_id, 'READ', book_title, 'DELETE')
                    action = "deleted"
                else:
                    # 추가 (읽은 책 등록)
                    cur.execute("INSERT INTO books_read (user_id, book_id) VALUES (:1, :2)", (g.user_id, book_isbn))
                    # 🟢 [수정] 위에서 구한 book_title 사용
                    log_activity(conn, g.user_id, 'READ', book_title, 'CREATE')
                    action = "added"

                conn.commit()
                return jsonify({"success": True, "action": action})

    except Exception as e:
        print(f"❌ Mark read error: {e}")
        return jsonify({"success": False, "message": "서버 오류 발생"}), 500

# 전북 행사 (DB 조회 우선, 데이터 없으면 샘플 데이터 5종 전체 표시)
@app.route('/jeonbuk_events')
def jeonbuk_events():
    events_list = []
    conn = None
    try:
        conn = get_connection() 
        cur = conn.cursor()
        
        sql = """
            SELECT EVENT_ID, TITLE, LOCATION, 
                   TO_CHAR(START_DATE, 'YYYY-MM-DD') as S_DATE, 
                   TO_CHAR(END_DATE, 'YYYY-MM-DD') as E_DATE,
                   DESCRIPTION 
            FROM events
            ORDER BY START_DATE ASC
        """
        cur.execute(sql)
        rows = cur.fetchall()
        
        print(f"✅ [DEBUG] events 테이블에서 {len(rows)}개의 데이터를 가져왔습니다.")

        for row in rows:
            desc_text = ""
            if row[5]:
                try:
                    desc_text = row[5].read() if hasattr(row[5], 'read') else str(row[5])
                except:
                    desc_text = str(row[5])
            
            events_list.append({
                "id": row[0],
                "title": row[1],
                "location": row[2] or "장소 미정",
                "date": f"{row[3]} ~ {row[4]}" if row[4] and row[3] != row[4] else row[3],
                "time": "상세내용 참조", 
                "description": desc_text or "상세 설명이 없습니다."
            })
            
    except Exception as e:
        print(f"❌ [ERROR] events 테이블 조회 중 오류: {e}")
    finally:
        if conn:
            pool.release(conn)

    if not events_list:
        print("⚠️ [INFO] DB 데이터가 없어 샘플 데이터를 표시합니다.")
        events_list = [
            {"id": 1, "title": "2025 전주 독서대전", "location": "전주한옥마을 및 완판본문화관", "date": "2025-10-09", "time": "10:00 ~ 18:00", "description": "전주의 책과 문화를 즐길 수 있는 대표 독서 축제."},
            {"id": 2, "title": "군산 북페어 2025", "location": "군산회관 및 원도심 일원", "date": "2025-08-29", "time": "11:00 ~ 20:00", "description": "군산의 로컬 문화를 담은 독립출판 마켓."},
            {"id": 3, "title": "익산 북페스티벌", "location": "익산시립도서관 일원", "date": "2025-10-16", "time": "13:00 ~ 17:00", "description": "책 읽는 문화도시 익산에서 열리는 가을 책 축제."},
            {"id": 4, "title": "남원 춘향골 도서관 문화가 있는 날", "location": "남원시립도서관", "date": "2025-05-25", "time": "14:00 ~ 16:00", "description": "가족과 함께하는 도서관 문화 체험 프로그램."},
            {"id": 5, "title": "완주 힐링 독서 캠프", "location": "완주 삼례문화예술촌", "date": "2025-06-12", "time": "1박 2일", "description": "자연 속에서 즐기는 힐링 독서 여행."}
        ]

    return render_template('jeonbuk_events.html', events=events_list)

@app.route('/event/<int:event_id>')
def event_detail(event_id):
    return "행사 상세 정보 페이지입니다."

# [수정됨] bookspot 경로 (지도 + 목록)
@app.route('/bookspot')
def bookspot():
    return render_template('bookspot.html', kakao_key=KAKAO_JS_KEY)

# [수정됨] 지도 데이터 API (IndieBookstores + libraries 테이블 조회)
# ★ 중요: 여기서 get_connection() (Pool)을 사용하도록 수정함
@app.route('/api/locations')
def get_locations():
    locations = []
    conn = None
    try:
        conn = get_connection() # Pool 사용
        cursor = conn.cursor()

        # 1. 독립서점 데이터 조회 (IndieBookstores)
        try:
            sql_bookstore = """
                SELECT name, lat, lon, address, phone_number, open_hours, sns, closed_day 
                FROM IndieBookstores
            """
            cursor.execute(sql_bookstore)
            for row in cursor.fetchall():
                if row[1] and row[2]: 
                    locations.append({
                        'title': row[0], 'lat': row[1], 'lng': row[2],
                        'address': row[3], 'phone': row[4], 'hours': row[5],
                        'sns': row[6], 'closed_day': row[7],
                        'type': 'bookstore' 
                    })
        except oracledb.DatabaseError:
            print("⚠️ IndieBookstores 테이블이 없거나 조회 실패")

        # 2. 도서관 데이터 조회 (libraries)
        try:
            sql_library = """
                SELECT NAME, LAT, LON, LOCATION, PHONE, SNS 
                FROM libraries
            """
            cursor.execute(sql_library)
            for row in cursor.fetchall():
                if row[1] and row[2]:
                    locations.append({
                        'title': row[0], 'lat': row[1], 'lng': row[2],
                        'address': row[3], 'phone': row[4], 
                        'sns': row[5],
                        'type': 'library', 
                        'hours': '운영시간은 홈페이지 참조', 
                        'closed_day': '홈페이지 참조'
                    })
        except oracledb.DatabaseError:
            print("⚠️ libraries 테이블이 없거나 조회 실패")

    except Exception as e:
        print(f"❌ DB 통합 조회 오류: {e}")
    finally:
        if conn:
            pool.release(conn)

    return jsonify(locations)   

@app.route('/read-book/delete/<string:book_isbn>', methods=['POST'])
def delete_read_book(book_isbn):
    if not g.user_id: return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM books_read WHERE user_id = :1 AND book_id = :2", (g.user_id, book_isbn))
                conn.commit()
                if cur.rowcount > 0: return jsonify({'success': True, 'message': '삭제되었습니다.'})
                else: return jsonify({'success': False, 'message': '삭제할 항목이 없습니다.'}), 404
    except Exception as e: print(f"❌ 읽은 책 삭제 오류: {e}"); return jsonify({'success': False, 'message': '서버 오류 발생'}), 500

@app.route('/essay/delete/<int:essay_id>', methods=['POST'])
def delete_essay(essay_id):
    if not g.user_id: return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM essays WHERE essay_id = :1 AND user_id = :2", (essay_id, g.user_id))
                log_activity(conn, g.user_id, 'ESSAY', book_title, 'DELETE')
                conn.commit()
                if cur.rowcount > 0: return jsonify({'success': True, 'message': '독후감이 삭제되었습니다.'})
                else: return jsonify({'success': False, 'message': '삭제 실패'}), 404
    except Exception as e: print(f"❌ 독후감 삭제 오류: {e}"); return jsonify({'success': False, 'message': '서버 오류 발생'}), 500

@app.route('/add_review/<string:book_id>', methods=['POST'])
def add_review_post(book_id):
    if not g.user_id: return jsonify({'success': False, 'message': '로그인이 필요합니다.'})
    rating = request.form.get('rating')
    content = request.form.get('content', '').strip() 
    if not rating or rating == '0' or rating == '': return jsonify({'success': False, 'message': '별점을 반드시 선택해주세요.'})
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                if content: cur.execute("INSERT INTO reviews (user_id, book_id, content) VALUES (:1, :2, :3)", (g.user_id, book_id, content))
                sql_merge = """MERGE INTO ratings r USING dual ON (r.user_id = :1 AND r.book_id = :2) 
                               WHEN MATCHED THEN UPDATE SET rating = :3 
                               WHEN NOT MATCHED THEN INSERT (user_id, book_id, rating) VALUES (:4, :5, :6)"""
                cur.execute(sql_merge, [g.user_id, book_id, rating, g.user_id, book_id, rating])
                cur.execute("SELECT title FROM books WHERE book_id = :1", (book_id,))
                book_title = cur.fetchone()[0]
                log_activity(conn, g.user_id, 'REVIEW', book_title, 'CREATE')
                conn.commit()
        return jsonify({'success': True, 'message': '평가가 등록되었습니다.'})
    except Exception as e: print(f"❌ Review add error: {e}"); return jsonify({'success': False, 'message': f'서버 오류: {e}'})

@app.route('/get_review/<string:book_id>')
def get_review(book_id):
    if not g.user_id: return jsonify({'success': False})
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT r.rating, rv.content FROM ratings r LEFT JOIN reviews rv ON r.book_id = rv.book_id AND r.user_id = rv.user_id WHERE r.user_id = :1 AND r.book_id = :2", (g.user_id, book_id))
                row = cur.fetchone()
                if row: return jsonify({'success': True, 'rating': row[0], 'content': row[1] if row[1] else ""})
                else: return jsonify({'success': False})
    except Exception as e: print(f"❌ Get review error: {e}"); return jsonify({'success': False})

@app.route('/search/user', methods=['POST'])
def search_user():
    nickname = request.json.get('nickname', '').strip()
    if not nickname: return jsonify({'success': False, 'message': '닉네임을 입력해주세요.'})
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM users WHERE nickname = :1", (nickname,))
                row = cur.fetchone()
                if row: return jsonify({'success': True, 'user_id': row[0]})
                else: return jsonify({'success': False, 'message': '해당 닉네임을 가진 사용자가 없습니다.'})
    except Exception as e: print(f"❌ User search error: {e}"); return jsonify({'success': False, 'message': '검색 중 오류 발생'})

# app.py의 기존 user_profile 함수를 이걸로 덮어쓰세요.

# [수정됨] user_profile 함수 (커서 닫힘 오류 해결)
@app.route('/profile/<string:target_user_id>')
def user_profile(target_user_id):
    # 만약 내 아이디를 눌렀다면 내 마이페이지로 이동
    if g.user_id == target_user_id:
        return redirect(url_for('mypage'))

    user_data = {}
    visibility = {}
    read_books = []
    bookmarks = []
    reviews = []
    essays = []
    is_following = False # 기본값
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # 1. 대상 유저 정보 + 공개 설정 조회
                sql_user = """
                    SELECT nickname, profile_image, 
                           visibility_review, visibility_essay, visibility_bookmark 
                           visibility_follow  -- 🟢 [추가됨]
                    FROM users WHERE user_id = :1
                """
                cur.execute(sql_user, (target_user_id,))
                row = cur.fetchone()
                
                if not row:
                    flash("존재하지 않는 사용자입니다.")
                    return redirect(url_for('home'))
                
                user_data = {
                    "id": target_user_id,
                    "nickname": row[0],
                    "profile_image": row[1]
                }
                
                # 공개 설정 (DB값 없으면 PUBLIC)
                visibility = {
                    'review': row[2] if row[2] else 'PUBLIC',
                    'essay': row[3] if row[3] else 'PUBLIC',
                    'bookmark': row[4] if row[4] else 'PUBLIC',
                    'read': 'PUBLIC',
                    'tag': 'PUBLIC'
                }
                
                # 2. 통계 (팔로워/팔로잉) - 별도 함수 호출 (내부에서 별도 연결 사용하므로 안전)
                user_data["stats"] = get_side_stats_from_db(target_user_id)
                
                # 🟢 [수정] 팔로우 여부 확인 (새 연결 안 만들고 기존 cur 사용!)
                if g.user_id:
                    sql_check = "SELECT 1 FROM followers WHERE follower_id = :1 AND following_id = :2"
                    cur.execute(sql_check, (g.user_id, target_user_id))
                    if cur.fetchone():
                        is_following = True
                
                # 3. 읽은 책 (PUBLIC일 때만 조회)
                if visibility['read'] != 'PRIVATE':
                    sql_read = """
                        SELECT b.book_id, b.title, b.cover_image, r.rating
                        FROM books b 
                        JOIN books_read br ON b.book_id = br.book_id
                        LEFT JOIN ratings r ON b.book_id = r.book_id AND r.user_id = br.user_id
                        WHERE br.user_id = :1
                        ORDER BY br.read_at DESC FETCH FIRST 8 ROWS ONLY
                    """
                    cur.execute(sql_read, (target_user_id,))
                    for row in cur.fetchall():
                        read_books.append({
                            "id": row[0], "title": row[1], 
                            "cover": upscale_aladin_cover(row[2]),
                            "rating": round(row[3], 1) if row[3] else 0.0
                        })

                # 4. 북마크
                if visibility['bookmark'] != 'PRIVATE':
                    sql_bm = """
                        SELECT b.book_id, b.title, b.cover_image
                        FROM books b JOIN bookmarks bm ON b.book_id = bm.book_id
                        WHERE bm.user_id = :1
                        ORDER BY bm.added_at DESC FETCH FIRST 8 ROWS ONLY
                    """
                    cur.execute(sql_bm, (target_user_id,))
                    for row in cur.fetchall():
                        bookmarks.append({"id": row[0], "title": row[1], "cover": upscale_aladin_cover(row[2])})

                # 5. 리뷰
                if visibility['review'] != 'PRIVATE':
                    sql_rv = """
                        SELECT rv.content, r.rating, b.title
                        FROM reviews rv
                        JOIN books b ON rv.book_id = b.book_id
                        LEFT JOIN ratings r ON rv.book_id = r.book_id AND rv.user_id = r.user_id
                        WHERE rv.user_id = :1
                        ORDER BY rv.created_at DESC FETCH FIRST 5 ROWS ONLY
                    """
                    cur.execute(sql_rv, (target_user_id,))
                    for row in cur.fetchall():
                        reviews.append({
                            "content": row[0],
                            "rating": row[1] if row[1] else 0.0,
                            "book_title": row[2]
                        })

                # 6. 독후감
                if visibility['essay'] != 'PRIVATE':
                    sql_es = """
                        SELECT e.essay_id, e.book_id, b.title, DBMS_LOB.SUBSTR(e.content, 100, 1)
                        FROM essays e JOIN books b ON e.book_id = b.book_id
                        WHERE e.user_id = :1 AND e.is_public = 'Y'
                        ORDER BY e.created_at DESC FETCH FIRST 5 ROWS ONLY
                    """
                    cur.execute(sql_es, (target_user_id,))
                    for row in cur.fetchall():
                        essays.append({
                            "essay_id": row[0], "book_id": row[1],
                            "book_title": row[2], "excerpt": row[3]
                        })

    except Exception as e:
        print(f"❌ Profile view error: {e}")
        flash("프로필을 불러오는 중 오류가 발생했습니다.")
        return redirect(url_for('home'))

    return render_template('user_profile.html', 
                           target_user=user_data, 
                           read_books=read_books, 
                           bookmarks=bookmarks,
                           reviews=reviews,
                           essays=essays,
                           visibility=visibility,
                           is_following=is_following)
# --- [추가] 공개 설정 변경 API ---
@app.route('/api/update_privacy', methods=['POST'])
def update_privacy():
    if not g.user_id: 
        return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401
    
    data = request.json
    target = data.get('target')   # review, essay, bookmark
    status = data.get('status')   # PUBLIC, PRIVATE
    
    # 컬럼 매핑
    column_map = {
        'review': 'visibility_review',
        'essay': 'visibility_essay',
        'bookmark': 'visibility_bookmark',
        'follow': 'visibility_follow'  # 👈 추가됨
    }
    
    if target not in column_map or status not in ['PUBLIC', 'PRIVATE']:
        return jsonify({'success': False, 'message': '잘못된 요청입니다.'}), 400

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # 해당 컬럼 업데이트
                sql = f"UPDATE users SET {column_map[target]} = :1 WHERE user_id = :2"
                cur.execute(sql, (status, g.user_id))
                conn.commit()
                return jsonify({'success': True})
    except Exception as e:
        print(f"❌ Privacy update error: {e}")
        return jsonify({'success': False, 'message': 'DB 업데이트 실패'}), 500

# --- [추가] 팔로우 토글 API ---
@app.route('/toggle_follow/<string:target_id>', methods=['POST'])
def toggle_follow(target_id):
    if not g.user_id:
        return jsonify({'success': False, 'message': '로그인이 필요합니다.', 'need_login': True})
    
    if g.user_id == target_id:
        return jsonify({'success': False, 'message': '자기 자신은 팔로우할 수 없습니다.'})

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:

                # [수정] 로그 기록을 위해 상대방 닉네임을 먼저 가져와야 함
                cur.execute("SELECT nickname FROM users WHERE user_id = :1", (target_id,))
                row = cur.fetchone()
                target_name = row[0] if row else target_id  # 닉네임 없으면 ID라도 사용
                # 1. 이미 팔로우 중인지 확인
                cur.execute("SELECT 1 FROM followers WHERE follower_id = :1 AND following_id = :2", (g.user_id, target_id))
                exists = cur.fetchone()
                
                if exists:
                    # 이미 팔로우 중 -> 언팔로우 (삭제)
                    cur.execute("DELETE FROM followers WHERE follower_id = :1 AND following_id = :2", (g.user_id, target_id))
                    log_activity(conn, g.user_id, 'FOLLOW', target_name, 'DELETE')
                    action = 'unfollowed'
                else:
                    # 안 함 -> 팔로우 (추가)
                    cur.execute("INSERT INTO followers (follower_id, following_id) VALUES (:1, :2)", (g.user_id, target_id))
                    log_activity(conn, g.user_id, 'FOLLOW', target_name, 'CREATE')
                    action = 'followed'
                
                # 2. 변경된 팔로워 수 계산 (프론트 갱신용)
                cur.execute("SELECT COUNT(*) FROM followers WHERE following_id = :1", (target_id,))
                new_follower_count = cur.fetchone()[0]
                
                conn.commit()
                
                return jsonify({
                    'success': True, 
                    'action': action, 
                    'new_count': new_follower_count
                })

    except Exception as e:
        print(f"❌ Follow toggle error: {e}")
        return jsonify({'success': False, 'message': '서버 오류 발생'})

# app.py의 get_follow_list 함수를 이걸로 교체하세요 (보안 로직 추가됨)
@app.route('/api/follow_list/<string:target_user_id>/<string:type>')
def get_follow_list(target_user_id, type):
    user_list = []
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # 1. 공개 설정 확인
                cur.execute("SELECT visibility_follow FROM users WHERE user_id = :1", (target_user_id,))
                row = cur.fetchone()
                if not row:
                    return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'})
                
                visibility = row[0] if row[0] else 'PUBLIC'

                # 2. 권한 체크: '비공개'이고 '내'가 아니면 거부
                if visibility == 'PRIVATE' and g.user_id != target_user_id:
                    return jsonify({'success': False, 'message': '비공개된 목록입니다.'})

                # 3. 목록 조회 (기존 로직)
                if type == 'following':
                    sql = """SELECT u.user_id, u.nickname, u.profile_image FROM followers f 
                             JOIN users u ON f.following_id = u.user_id WHERE f.follower_id = :1"""
                else:
                    sql = """SELECT u.user_id, u.nickname, u.profile_image FROM followers f 
                             JOIN users u ON f.follower_id = u.user_id WHERE f.following_id = :1"""
                
                cur.execute(sql, (target_user_id,))
                for r in cur.fetchall():
                    user_list.append({'user_id': r[0], 'nickname': r[1], 'profile_image': r[2]})
                    
        return jsonify({'success': True, 'list': user_list})

    except Exception as e:
        print(f"❌ Follow list error: {e}")
        return jsonify({'success': False, 'message': '서버 오류'})
    
# ---------------------------------------------------------
# [핵심 로직] 책 태그 분석 및 저장 함수
# ---------------------------------------------------------
def analyze_and_save_tags(conn, book_id, title, description):
    """
    책 제목(가중치 3)과 설명(가중치 1)을 분석하여 상위 5개 태그를 DB에 저장합니다.
    """
    if not title: title = ""
    if not description: description = ""
    
    # 1. 점수 계산
    tag_scores = {} # { "태그명": 점수 }
    
    # 모든 카테고리와 태그를 순회하며 매칭 검사
    for category, tags in TAG_DICT.items():
        for tag_name, keywords in tags.items():
            score = 0
            for keyword in keywords:
                # 제목 매칭 (3점)
                if keyword in title:
                    score += 3
                # 설명 매칭 (1점)
                if keyword in description:
                    score += 1
            
            if score > 0:
                # 태그별 총점 합산
                tag_scores[tag_name] = tag_scores.get(tag_name, 0) + score
                # 태그 메타데이터 저장을 위해 카테고리 정보도 임시 저장해두면 좋음 (생략 가능)

    # 2. 점수 내림차순 정렬 후 상위 5개 추출
    sorted_tags = sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)[:5]
    
    if not sorted_tags:
        return # 매칭된 태그가 없으면 종료

    try:
        with conn.cursor() as cur:
            for tag_name, score in sorted_tags:
                # A. 태그가 TAGS 테이블에 있는지 확인하고 없으면 생성 (카테고리는 TAG_DICT에서 찾아서 넣음)
                # (주의: 실제로는 TAGS 테이블을 미리 초기화해두는 것이 성능상 좋으나, 여기선 자동 생성 로직 포함)
                found_category = "기타"
                for cat, t_dict in TAG_DICT.items():
                    if tag_name in t_dict:
                        found_category = cat
                        break
                
                # MERGE 문을 사용하여 태그가 없으면 INSERT (Oracle 문법)
                cur.execute("""
                    MERGE INTO tags t
                    USING dual ON (t.tag_name = :1)
                    WHEN NOT MATCHED THEN
                        INSERT (tag_name, category) VALUES (:2, :3)
                """, (tag_name, tag_name, found_category))
                
                # B. 태그 ID 조회
                cur.execute("SELECT tag_id FROM tags WHERE tag_name = :1", (tag_name,))
                tag_id_row = cur.fetchone()
                
                if tag_id_row:
                    tag_id = tag_id_row[0]
                    # C. BOOK_TAGS 테이블에 연결 정보 저장 (중복 무시)
                    # 여기서는 간단히 INSERT 하고 에러나면 무시하거나 MERGE 사용
                    cur.execute("""
                        MERGE INTO book_tags bt
                        USING dual ON (bt.book_id = :1 AND bt.tag_id = :2)
                        WHEN NOT MATCHED THEN
                            INSERT (book_id, tag_id) VALUES (:3, :4)
                    """, (book_id, tag_id, book_id, tag_id))
                    
            # print(f"✅ [Auto Tagging] {title} -> {[t[0] for t in sorted_tags]}")

    except Exception as e:
        print(f"❌ 태그 저장 중 오류: {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)