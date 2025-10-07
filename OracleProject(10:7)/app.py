from flask import Flask, render_template, request, redirect, url_for, session, flash
import oracledb
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import timedelta
from werkzeug.utils import secure_filename
import random
import string
import uuid

pool = oracledb.create_pool(
    user="system",
    password="Asdf4156",
    dsn="localhost:1521/XEPDB1",
    min=2,
    max=5,
    increment=1
)

def get_connection():
    return pool.acquire()

app = Flask(__name__)
app.secret_key = "my_secret_key"
app.permanent_session_lifetime = timedelta(hours=5)

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
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
                    cur.execute("""
                        SELECT CASE
                                   WHEN user_id = :user_id THEN '아이디'
                                   WHEN nickname = :nickname THEN '닉네임'
                                   WHEN email = :email THEN '이메일'
                               END
                        FROM users
                        WHERE user_id = :user_id
                           OR nickname = :nickname
                           OR email = :email
                    """, {"user_id": user_id, "nickname": nickname, "email": email})

                    row = cur.fetchone()
                    if row:
                        flash(f"이미 사용 중인 {row[0]}입니다.")
                        return render_template("signup.html", form_data=form_data)

                    hashed_pw = generate_password_hash(password, method="pbkdf2:sha256")
                    cur.execute("""
                        INSERT INTO users (user_id, password, nickname, email)
                        VALUES (:1, :2, :3, :4)
                    """, (user_id, hashed_pw, nickname, email))
                    conn.commit()

            flash("회원가입이 완료되었습니다. 로그인해주세요.")
            return redirect(url_for("login"))
        except Exception as e:
            flash(f"오류가 발생했습니다: {e}")
            return redirect(url_for("signup"))

    return render_template("signup.html", form_data={})

@app.route("/login", methods=["GET", "POST"])
def login():
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
            flash(f"로그인 중 오류 발생: {e}")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/profile_edit", methods=["GET", "POST"])
def profile_edit():
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:


                if request.method == "POST":
                    new_nickname = request.form["user_nickname"]
                    new_email = request.form["user_email"]


                    file = request.files.get("profile_image")
                    filename = None
                    if file and file.filename:
                        ext = os.path.splitext(file.filename)[1]
                        filename = f"{uuid.uuid4().hex}{ext}"
                        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                        file.save(file_path)


                    current_pw = request.form.get("current_pw", "")
                    new_pw = request.form.get("new_pw", "")
                    new_pw_confirm = request.form.get("new_pw_confirm", "")

                    cur.execute("SELECT password FROM users WHERE user_id = :1", (session["user_id"],))
                    row = cur.fetchone()
                    if not row:
                        flash("사용자 정보를 찾을 수 없습니다.")
                        return redirect(url_for("mypage"))

                    db_pw = row[0]

                    update_fields = {"nickname": new_nickname, "email": new_email, "user_id": session["user_id"]}
                    update_sql = "UPDATE users SET nickname = :nickname, email = :email"

                    if filename:
                        update_fields["profile_image"] = filename
                        update_sql += ", profile_image = :profile_image"

                    if new_pw or new_pw_confirm:
                        if not check_password_hash(db_pw, current_pw):
                            return render_template("profile_edit.html",
                                user={"nickname": new_nickname, "email": new_email, "profile_image": filename},
                                error_message_pw="현재 비밀번호가 올바르지 않습니다.")
                        if new_pw != new_pw_confirm:
                            return render_template("profile_edit.html",
                                user={"nickname": new_nickname, "email": new_email, "profile_image": filename},
                                error_message_pw="새 비밀번호가 일치하지 않습니다.")

                        hashed_pw = generate_password_hash(new_pw, method="pbkdf2:sha256")
                        update_fields["password"] = hashed_pw
                        update_sql += ", password = :password"

                    update_sql += " WHERE user_id = :user_id"
                    cur.execute(update_sql, update_fields)
                    conn.commit()

                    session["nickname"] = new_nickname
                    flash("프로필이 수정되었습니다.")
                    return redirect(url_for("mypage"))

                cur.execute("SELECT nickname, email, profile_image FROM users WHERE user_id = :1", (session["user_id"],))
                row = cur.fetchone()
                if not row:
                    flash("사용자 정보를 찾을 수 없습니다.")
                    return redirect(url_for("home"))

                user_data = {"nickname": row[0], "email": row[1], "profile_image": row[2]}

    except Exception as e:
        flash(f"프로필 수정 중 오류 발생: {e}")
        return redirect(url_for("mypage"))

    return render_template("profile_edit.html", user=user_data)


def generate_temp_password(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

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
                cur.execute("SELECT 1 FROM users WHERE user_id = :1", (user_id,))
                if not cur.fetchone():
                    flash("존재하지 않는 아이디입니다.")
                    return redirect(url_for("find_password"))

                cur.execute("SELECT 1 FROM users WHERE email = :1", (user_email,))
                if not cur.fetchone():
                    flash("존재하지 않는 이메일입니다.")
                    return redirect(url_for("find_password"))

                cur.execute("""
                    SELECT 1 FROM users
                    WHERE user_id = :1 AND email = :2
                """, (user_id, user_email))
                if not cur.fetchone():
                    flash("아이디와 이메일이 일치하지 않습니다.")
                    return redirect(url_for("find_password"))

                temp_pw = generate_temp_password()
                hashed_pw = generate_password_hash(temp_pw, method="pbkdf2:sha256")

                cur.execute("""
                    UPDATE users
                    SET password = :1
                    WHERE user_id = :2
                """, (hashed_pw, user_id))
                conn.commit()

                flash(f"임시 비밀번호가 발급되었습니다: {temp_pw}")
                return redirect(url_for("login"))

    except Exception as e:
        flash(f"비밀번호 찾기 중 오류 발생: {e}")
        return redirect(url_for("find_password"))

@app.route("/mypage")
def mypage():
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                    SELECT user_id, nickname, email, profile_image
                    FROM users
                    WHERE user_id = :1
                """, (session["user_id"],))
                row = cur.fetchone()
                if not row:
                    flash("사용자 정보를 찾을 수 없습니다.")
                    return redirect(url_for("home"))

                user_data = {
                    "id": row[0],
                    "nickname": row[1],
                    "email": row[2],
                    "profile_image": row[3]
                }

                cur.execute("""
                    SELECT COUNT(*) 
                    FROM books_read
                    WHERE user_id = :1
                """, (session["user_id"],))
                read_count = cur.fetchone()[0]

                user_data["read_count"] = read_count

    except Exception as e:
        flash(f"사용자 정보 조회 중 오류 발생: {e}")
        return redirect(url_for("home"))

    return render_template("mypage.html", user=user_data)


if __name__ == "__main__":
    app.run(host = "0.0.0.0", debug=True, port=5001)
