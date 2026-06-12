import os
from html import escape
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

app = FastAPI(title="API Fichiers Azure")

CONTAINER_NAME = "fichiers-api"


def get_container_client(create_if_missing: bool = False):
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

    if not connection_string:
        raise HTTPException(
            status_code=500,
            detail="Variable AZURE_STORAGE_CONNECTION_STRING manquante."
        )

    try:
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)

        if create_if_missing:
            try:
                container_client.create_container()
            except ResourceExistsError:
                pass

        return container_client

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur de connexion au Storage Account : {error}"
        )


def upload_to_blob(file: UploadFile) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Aucun fichier envoyé.")

    filename = Path(file.filename).name
    container_client = get_container_client(create_if_missing=True)

    try:
        content = file.file.read()
        blob_client = container_client.get_blob_client(filename)
        blob_client.upload_blob(content, overwrite=True)

        return {
            "message": "Fichier envoyé avec succès.",
            "filename": filename
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de l'envoi du fichier : {error}"
        )


def delete_blob(filename: str) -> dict:
    if not filename:
        raise HTTPException(status_code=400, detail="Nom de fichier manquant.")

    container_client = get_container_client()

    try:
        blob_client = container_client.get_blob_client(filename)
        blob_client.delete_blob()

        return {
            "message": "Fichier supprimé avec succès.",
            "filename": filename
        }

    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Fichier introuvable.")

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la suppression : {error}"
        )


@app.get("/", response_class=HTMLResponse)
def upload_page(status: str = "", filename: str = "") -> str:
    files = []

    try:
        container_client = get_container_client(create_if_missing=True)
        files = [blob.name for blob in container_client.list_blobs()]
    except Exception:
        files = []

    message = ""

    if status == "uploaded":
        message = f"<p style='color: green;'>Fichier envoyé : {escape(filename)}</p>"
    elif status == "deleted":
        message = f"<p style='color: green;'>Fichier supprimé : {escape(filename)}</p>"

    file_items = ""

    if files:
        for file_name in files:
            safe_name = escape(file_name)
            file_items += f"""
            <li>
                {safe_name}
                <form action="/delete" method="post" style="display:inline;">
                    <input type="hidden" name="filename" value="{safe_name}">
                    <button type="submit">Supprimer</button>
                </form>
            </li>
            """
    else:
        file_items = "<li>Aucun fichier dans le conteneur.</li>"

    return f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <title>API Fichiers Azure</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 40px auto;
                line-height: 1.5;
            }}

            form {{
                margin-bottom: 20px;
            }}

            button {{
                cursor: pointer;
            }}

            .box {{
                padding: 20px;
                border: 1px solid #ddd;
                border-radius: 8px;
                margin-bottom: 20px;
            }}
        </style>
    </head>
    <body>
        <h1>API Fichiers Azure</h1>

        {message}

        <div class="box">
            <h2>Envoyer un fichier</h2>
            <form action="/" method="post" enctype="multipart/form-data">
                <input type="file" name="file" required>
                <button type="submit">Envoyer</button>
            </form>
        </div>

        <div class="box">
            <h2>Fichiers présents dans Azure Blob Storage</h2>
            <ul>
                {file_items}
            </ul>
        </div>

        <p>
            <a href="/docs">Voir la documentation Swagger</a>
        </p>
    </body>
    </html>
    """


@app.post("/")
def upload_from_root(file: UploadFile = File(...)):
    result = upload_to_blob(file)
    filename = quote(result["filename"])

    return RedirectResponse(
        url=f"/?status=uploaded&filename={filename}",
        status_code=303
    )


@app.get("/files")
def list_files() -> dict:
    container_client = get_container_client(create_if_missing=True)
    files = [blob.name for blob in container_client.list_blobs()]

    return {
        "files": files
    }


@app.post("/delete")
def delete_from_root(filename: str = Form(...)):
    result = delete_blob(filename)
    safe_filename = quote(result["filename"])

    return RedirectResponse(
        url=f"/?status=deleted&filename={safe_filename}",
        status_code=303
    )


@app.post("/upload")
def upload_file(file: UploadFile = File(...)) -> dict:
    return upload_to_blob(file)


@app.delete("/remove")
def remove_file(filename: str) -> dict:
    return delete_blob(filename)