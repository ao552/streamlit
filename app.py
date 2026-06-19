import streamlit as st
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker
import bcrypt
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from io import BytesIO
import os

# ==========================================
# ページ設定
# ==========================================
st.set_page_config(page_title="現場写真管理", layout="wide")

# ==========================================
# PostgreSQL (Supabase)
# ==========================================
DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# Models
# ==========================================
class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, index=True)
    userid        = Column(String(50),  unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

class Project(Base):
    __tablename__ = "projects"
    id         = Column(Integer, primary_key=True, index=True)
    title      = Column(String(200), nullable=False)
    address    = Column(String(500))
    owner      = Column(String(200))
    memo       = Column(Text)
    created_at = Column(String(20))

class Photo(Base):
    __tablename__ = "photos"
    id         = Column(Integer, primary_key=True)
    project_id = Column(Integer)
    filename   = Column(String(255))
    direction  = Column(String(20))
    created_at = Column(String(20))

Base.metadata.create_all(bind=engine)

# ==========================================
# パスワード関数
# ==========================================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

# ==========================================
# 管理者ユーザー初期作成
# ==========================================
def create_admin_user():
    db = SessionLocal()
    try:
        if db.query(User).filter(User.userid == "admin").first() is None:
            db.add(User(userid="admin", password_hash=hash_password("password123")))
            db.commit()
    finally:
        db.close()

create_admin_user()

# ==========================================
# EXIF / GPS ユーティリティ
# ==========================================
def direction_name(deg: float) -> str:
    dirs = ["北", "北東", "東", "南東", "南", "南西", "西", "北西"]
    return dirs[round(deg / 45) % 8]

def exif_value_to_float(value):
    if value is None:
        return None
    if isinstance(value, tuple) and len(value) == 2:
        return value[0] / value[1]
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        return value.numerator / value.denominator
    return float(value)

def dms_to_deg(dms, ref: str) -> float:
    d = dms[0][0] / dms[0][1]
    m = dms[1][0] / dms[1][1]
    s = dms[2][0] / dms[2][1]
    deg = d + m / 60 + s / 3600
    if ref in ["S", "W"]:
        deg *= -1
    return deg

def get_declination(lat: float) -> float:
    return 6 + (lat - 26) * (4 / (45 - 26))

def get_gps_from_bytes(file_content: bytes) -> str:
    try:
        img  = Image.open(BytesIO(file_content))
        exif = img._getexif()
        if exif is None:
            return ""

        gps_info = {}
        for tag, value in exif.items():
            tag_name = TAGS.get(tag, tag)
            if tag_name == "GPSInfo":
                for t in value:
                    gps_info[GPSTAGS.get(t, t)] = value[t]

        if "GPSImgDirection" not in gps_info:
            return ""

        lat = None
        if "GPSLatitude" in gps_info and "GPSLatitudeRef" in gps_info:
            lat = dms_to_deg(gps_info["GPSLatitude"], gps_info["GPSLatitudeRef"])

        direction = float(gps_info["GPSImgDirection"])

        if lat is not None:
            direction += get_declination(lat)

        direction = direction % 360
        return f"{direction:.1f}° ({direction_name(direction)})"

    except Exception as ex:
        print("get_gps_from_bytes error =", ex)
        return ""

def compress_image(file_content: bytes) -> bytes:
    img = Image.open(BytesIO(file_content))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    exif_bytes = img.info.get("exif", b"")
    buf = BytesIO()
    img.save(buf, "JPEG", quality=30, optimize=True, exif=exif_bytes)
    return buf.getvalue()

# ==========================================
# session_state 初期化
# ==========================================
if "user"    not in st.session_state:
    st.session_state.user    = None
if "page"    not in st.session_state:
    st.session_state.page    = "login"
if "project" not in st.session_state:
    st.session_state.project = None   # 選択中の project_id

def go(page: str, project_id: int = None):
    st.session_state.page    = page
    st.session_state.project = project_id
    st.rerun()

# ==========================================
# ログイン画面
# ==========================================
def page_login():
    st.title("ログイン")
    
    col1, col2 = st.columns([1, 3])  # 左を細くする
        
    with col1:
        userid = st.text_input("ユーザーID")
        password = st.text_input("パスワード", type="password")

        if st.button("ログイン"):
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.userid == userid).first()
                if user is None:
                    st.error("ユーザーが存在しません")
                elif not verify_password(password, user.password_hash):
                    st.error("パスワードが違います")
                else:
                    st.session_state.user = userid
                    go("menu")
            finally:
                db.close()
                
# ==========================================
# メニュー画面
# ==========================================
def page_menu():
    st.title("メインメニュー")
    st.write(f"ようこそ **{st.session_state.user}** さん")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📋 案件一覧", use_container_width=True):
            go("projects")
    with col2:
        if st.button("➕ 案件登録", use_container_width=True):
            go("project_new")
    with col3:
        if st.button("🚪 ログアウト", use_container_width=True):
            st.session_state.user = None
            go("login")

# ==========================================
# 案件一覧
# ==========================================
def page_projects():
    st.title("案件一覧")

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("➕ 新規登録"):
            go("project_new")
    with col2:
        if st.button("← メニューへ"):
            go("menu")

    db = SessionLocal()
    try:
        projects = db.query(Project).order_by(Project.id.desc()).all()
    finally:
        db.close()

    if not projects:
        st.info("案件はまだありません")
        return

    for p in projects:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([1, 3, 3, 2])
            c1.write(f"**{p.id}**")
            if c2.button(p.title, key=f"proj_{p.id}"):
                go("project_detail", p.id)
            c3.write(p.address or "")
            c4.write(p.created_at or "")

# ==========================================
# 案件登録
# ==========================================
def page_project_new():
    st.title("案件登録")

    with st.form("new_project"):
        title   = st.text_input("案件名 *")
        address = st.text_input("所在地")
        owner   = st.text_input("依頼者")
        memo    = st.text_area("メモ", height=120)
        submitted = st.form_submit_button("登録")

    if submitted:
        if not title.strip():
            st.error("案件名は必須です")
        else:
            db = SessionLocal()
            try:
                db.add(Project(
                    title=title, address=address, owner=owner, memo=memo,
                    created_at=datetime.now().strftime("%Y-%m-%d")
                ))
                db.commit()
                st.success("登録しました")
                go("projects")
            finally:
                db.close()

    if st.button("← 案件一覧へ戻る"):
        go("projects")

# ==========================================
# 案件詳細 ＋ 写真アップロード
# ==========================================
def page_project_detail():
    project_id = st.session_state.project
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        photos  = db.query(Photo).filter(Photo.project_id == project_id).all()
    finally:
        db.close()

    if project is None:
        st.error("案件が見つかりません")
        go("projects")
        return

    st.title(f"案件詳細：{project.title}")
    st.write(f"**所在地：** {project.address or '―'}")
    st.write(f"**依頼者：** {project.owner or '―'}")
    st.write(f"**登録日：** {project.created_at or '―'}")
    if project.memo:
        st.write(f"**メモ：** {project.memo}")

    if st.button("← 案件一覧へ"):
        go("projects")

    st.divider()

    # ── 写真アップロード ──────────────────────────────
    st.subheader("写真アップロード")
    uploaded = st.file_uploader(
        "画像を選択（JPG / PNG）",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=False
    )

    if uploaded is not None:
        file_content = uploaded.read()
        st.image(file_content, caption="プレビュー", width=300)
        st.write(f"元サイズ: {len(file_content) / 1024:.1f} KB")

        if st.button("📤 このまま送信"):
            # EXIF 方位取得
            direction = get_gps_from_bytes(file_content)

            # 画像圧縮
            compressed = compress_image(file_content)
            st.write(f"圧縮後: {len(compressed) / 1024:.1f} KB")

            # 保存
            folder   = f"uploads/{project_id}"
            os.makedirs(folder, exist_ok=True)
            filename = uploaded.name or datetime.now().strftime("%Y%m%d_%H%M%S.jpg")
            filepath = os.path.join(folder, filename)
            with open(filepath, "wb") as f:
                f.write(compressed)

            # DB 登録
            db = SessionLocal()
            try:
                db.add(Photo(
                    project_id=project_id,
                    filename=filename,
                    direction=direction,
                    created_at=datetime.now().strftime("%Y-%m-%d")
                ))
                db.commit()
            finally:
                db.close()

            st.success(f"アップロード完了（方位: {direction or 'なし'}）")
            st.rerun()

    st.divider()

    # ── 写真一覧 ──────────────────────────────────────
    st.subheader("写真一覧")

    if not photos:
        st.info("写真はまだありません")
        return

    cols_per_row = 3
    for i in range(0, len(photos), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, photo in enumerate(photos[i:i + cols_per_row]):
            img_path = f"uploads/{project_id}/{photo.filename}"
            with cols[j]:
                if os.path.exists(img_path):
                    st.image(img_path, use_container_width=True)
                else:
                    st.write("（画像なし）")
                st.caption(f"ID:{photo.id}　{photo.filename}")
                st.caption(f"方位: {photo.direction or 'なし'}")

# ==========================================
# ルーティング
# ==========================================
def main():
    # 未ログインは常にログイン画面へ
    if st.session_state.user is None:
        page_login()
        return

    page = st.session_state.page

    if page == "menu":
        page_menu()
    elif page == "projects":
        page_projects()
    elif page == "project_new":
        page_project_new()
    elif page == "project_detail":
        page_project_detail()
    else:
        page_menu()

main()
