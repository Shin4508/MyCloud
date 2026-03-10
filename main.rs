use axum::handler::HandlerWithoutStateExt;
use axum::http::{StatusCode, header, status};
use axum::{
    Router,
    body::Body,
    extract::{DefaultBodyLimit, Multipart, Path as AxumPath},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use std::path::{Path as StdPath, PathBuf};
use tokio::fs::{File, read_dir};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader, BufWriter};
use tokio::net::{TcpListener, TcpStream};
use tokio_util::io::ReaderStream;

const BASE_DIR: &str = "storage/uploads";

// get file
async fn get_file(AxumPath(filename): AxumPath<String>) -> impl IntoResponse {
    // 1. ファイルパスを組み立てる
    let path = PathBuf::from(BASE_DIR).join(&filename);

    // 2. ファイルを「扉」だけ開く（中身は読み込まない）
    let file = match File::open(path).await {
        //
        Ok(f) => f,
        Err(_) => return (StatusCode::NOT_FOUND, "File not found").into_response(), //
    };

    let reader = BufReader::new(file);

    // 4. ファイルを「細切れの流れ（Stream）」に変換
    let stream = ReaderStream::new(reader);

    // 5. レスポンスとして返す
    //    Body::from_stream を使うことで、Axum が自動的に少しずつ送ってくれます。
    Response::builder()
        .header(header::CONTENT_TYPE, "application/octet-stream")
        .header(
            header::CONTENT_DISPOSITION,
            format!("attachment; filename=\"{}\"", filename),
        )
        .body(Body::from_stream(stream)) //
        .unwrap()
}

async fn post_file(mut multipart: Multipart) -> impl IntoResponse {
    while let Ok(Some(field)) = multipart.next_field().await {
        // filename
        let file_name = field.file_name().unwrap_or("uploaded_file").to_string();

        //Path
        let path = StdPath::new("storage/uploads").join(&file_name);

        //SSD にファイルを作成
        let mut f = match File::create(path).await {
            Ok(f) => f,
            Err(_) => {
                return (StatusCode::INTERNAL_SERVER_ERROR, "Faild to create File").into_response();
            }
        };

        // 部分にわけてSSDに流し込み
        let mut field = field;
        while let Ok(Some(chunk)) = field.chunk().await {
            if let Err(_) = f.write_all(&chunk).await {
                return (StatusCode::INTERNAL_SERVER_ERROR, "Writeing Error").into_response();
            };
        }
    }
    "Upload finished".into_response()
}

async fn list_file() -> impl IntoResponse {
    "File List: ".into_response()
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tokio::fs::create_dir_all(BASE_DIR).await?;

    let app = Router::new()
        .route("/files/:filename", get(get_file))
        .route("/files", post(post_file))
        .route("/files", get(list_file));

    let addr = "0.0.0.8080";
    let listener = TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
