from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.response import FileResponse
import hashlib
import sqlite3

# FastAPIアプリを作る（HTTPサーバー本体）
app = FastAPI()

# === 保存先ディレクトリの設定 ===
# storage/uploads を「自分のクラウドの中身」にする
BASE_DIR = Path("storage/uploads")

# ディレクトリが存在しなければ作る
# parents=True : 親ディレクトリ（storage）も一緒に作る
# exist_ok=True : すでにあってもエラーにしない
BASE_DIR.mkdir(parents=True, exist_ok=True)


@app.on_event("startup")
def startup_event():
    init_db()


async def hashval(upload_file: UploadFile):
    hash = hashlib.sha256()
    await upload_file.seek(0)

    while chunk := await upload_file.read(8192):
        hash.update(chunk)

    await upload_file.seek(0)
    return hash.hexdigest()


def init_db():
    conn = sqlite3.connect("metadata.db")
    conn.execute("""
            CREATE TABLE IF NOT EXISTS file_metadata (
                hash TEXT PRIMARY KEY,
                original_name TEXT,
                file_extension TEXT,
                size INTEGER
            )
        """)
    conn.close()


# === ファイルアップロード用のエンドポイント ===
# POST /files に対する処理
@app.post("/files")
async def upload_file(
    # file は HTTPのBodyに含まれる「ファイル」
    # File(...) を付けることで「これはファイルだ」とFastAPIに伝える
    file: UploadFile = File(...),
):
    # file.filename は、アップロードされたファイル名
    # ただし、そのまま使うと危険な場合があるので…

    hash_val = await hashval(file)
    head1 = hash_val[0:2]
    head2 = hash_val[2:4]
    # Path(file.filename).name
    # → ディレクトリ成分を削除して「純粋なファイル名」だけにする
    safe_name = Path(file.filename).name
    file_extension = Path(file.filename).suffix
    save_filename = f"{hash_val}{file_extension}"
    # same_nameをHash値に置き換える
    # 先頭をディレクトリの名前に変換
    save_dir = BASE_DIR / head1 / head2
    save_dir.mkdir(parents=True, exist_ok=True)
    # 保存先のフルパスを作る
    # 例: storage/uploads/sample.pdf
    file_path = save_dir / save_filename

    if file_path.exists():
        return {"message": "File already exists"}

    content = await file.read()
    file_size = len(content)
    # 実際にファイルを書き込:
    # "wb" = バイナリ書き込みモード
    with open(file_path, "wb") as f:
        # UploadFile.read() でファイルの中身を取得
        # await が必要なのは、非同期で読み込んでいるから
        f.write(content)
    # クライアントに返すレスポンス
    # DB
    with sqlite3.connect("metadata.db") as conn:
        conn.execute(
            "INSERT OR REPLACE INTO file_metadata (hash, original_name, file_extension, size) VALUES (?, ?, ?, ?)",
            (hash_val, file.filename, file_extension, file_size),
        )

    return {"filename": safe_name, "saved_to": str(file_path)}


# ファイル取得
@app.get("/files/{save_filename}")
async def get_file(save_filename: str):
    head1 = save_filename[0:2]
    head2 = save_filename[2:4]
    file_path = BASE_DIR / head1 / head2 / save_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path)


# フィアル一覧
@app.get("/files")
async def list_file(type: str | None = None, limit: int = 20):
    files = []
    with sqlite3.connect("metadata.db") as conn:
        cursor = conn.execute(
            "SELECT original_name, hash, file_extension, size FROM file_metadata LIMIT ?",
            (limit,),
        )
        for row in cursor.fetchall():
            full_save_name = f"{row[1]}{row[2]}"
            files.append(
                {
                    "display_name": row[0],  # 元の名前
                    "save_filename": full_save_name,  # 取得用のID
                    "size": row[3],
                }
            )
    return files
