from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from db.session import verify_connection, init_db, get_db
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import List
from contextlib import asynccontextmanager
import os
import shutil
import time

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing ESG Disclosure Assistant API...")
    is_connected = verify_connection()
    if is_connected:
        print("PostgreSQL connection verified successfully.")
        init_db()
    else:
        print("WARNING: PostgreSQL connection verification failed during startup.")
    yield

app = FastAPI(
    title="ESG Disclosure Assistant API",
    description="Backend API for ESG Disclosure Assistant with PostgreSQL integration",
    version="1.0.0",
    lifespan=lifespan
)

# Allow CORS requests from the Angular frontend (and standard localhost ports)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def run_ingestion_for_model(requestId: str, model: str):
    print(f"Starting RAG Ingestion task for request ID: {requestId} and model: {model}")
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    chroma_dir = os.path.join(base_dir, "rag_chroma_db", f"{requestId}_{model}")
    
    if os.path.exists(chroma_dir):
        print(f"Deleting existing vector store folder freshly in backend: {chroma_dir}")
        try:
            shutil.rmtree(chroma_dir)
        except Exception as e:
            print(f"Warning: Failed to delete existing vector store folder: {str(e)}")
            
    python_exec = os.path.join(base_dir, ".venv", "bin", "python")
    script_path = os.path.join(base_dir, "app", "ingest", "ingest_docs.py")
    
    if not os.path.exists(python_exec):
        python_exec = "python"
        
    env = os.environ.copy()
    
    import subprocess
    print(f"Triggering RAG Ingestion in background for request ID: {requestId} and model: {model}")
    try:
        res = subprocess.run(
            [python_exec, script_path, requestId, model],
            env=env,
            cwd=base_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if res.returncode == 0:
            print(f"RAG Ingestion SUCCESS for request ID {requestId} and model {model}:\n{res.stdout}")
        else:
            print(f"RAG Ingestion FAILED for request ID {requestId} and model {model}:\n{res.stderr}")
    except Exception as e:
        print(f"Error running RAG Ingestion subprocess for request ID {requestId} and model {model}: {str(e)}")

def run_rag_ingestion_task(requestId: str):
    from db.session import SessionLocal
    from sqlalchemy import text
    try:
        numeric_request_id = int(requestId.replace("req_", ""))
    except ValueError:
        numeric_request_id = 0

    model = "gemini-3.5"
    if numeric_request_id > 0:
        db = SessionLocal()
        try:
            query = text("SELECT model FROM upload_request WHERE request_id = :request_id")
            row = db.execute(query, {"request_id": numeric_request_id}).fetchone()
            if row and row.model:
                model = row.model
        except Exception as e:
            print(f"Error fetching model for request {requestId} in ingestion task: {e}")
        finally:
            db.close()

    run_ingestion_for_model(requestId, model)

@app.post("/esg/upload")
async def upload_documents(
    requestId: str = Form(None),
    year: int = Form(...),
    model: str = Form("gemini-3.5"),
    name: str = Form(None),
    frameworkName: str = Form("VSME (Voluntary Sustainability Reporting Standard for SMEs)"),
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    # If requestId is not provided, generate a unique ID
    if not requestId:
        requestId = f"req_{int(time.time() * 1000)}"
        
    # Get absolute path to backend/documents folder
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    documents_dir = os.path.join(base_dir, "documents")
    
    # Ensure documents directory and the specific requestId subdirectory exist
    request_dir = os.path.join(documents_dir, requestId)
    os.makedirs(request_dir, exist_ok=True)
    
    saved_files = []
    for file in files:
        if not file.filename:
            continue
        file_path = os.path.join(request_dir, file.filename)
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_files.append(file.filename)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save file '{file.filename}': {str(e)}"
            )

    # Try parsing the numeric part of the requestId to store in the database as BIGINT
    try:
        numeric_request_id = int(requestId.replace("req_", ""))
    except ValueError:
        numeric_request_id = int(time.time() * 1000)

    # Insert/update row into the upload_request database table
    try:
        db_folder_path = os.path.join("documents", requestId)
        
        # Count all valid files currently in the directory
        all_files = []
        if os.path.exists(request_dir):
            all_files = [f for f in os.listdir(request_dir) 
                         if os.path.isfile(os.path.join(request_dir, f)) and not f.startswith(".")]
        total_files_count = len(all_files)
        
        insert_query = text("""
            INSERT INTO upload_request (request_id, folder_path, total_files, status, model, name, framework_name)
            VALUES (:request_id, :folder_path, :total_files, :status, :model, :name, :framework_name)
            ON CONFLICT (request_id) DO UPDATE SET
                folder_path = EXCLUDED.folder_path,
                total_files = EXCLUDED.total_files,
                status = EXCLUDED.status,
                model = EXCLUDED.model,
                name = COALESCE(EXCLUDED.name, upload_request.name),
                framework_name = COALESCE(EXCLUDED.framework_name, upload_request.framework_name),
                updated_at = CURRENT_TIMESTAMP
        """)
        
        db.execute(
            insert_query,
            {
                "request_id": numeric_request_id,
                "folder_path": db_folder_path,
                "total_files": total_files_count,
                "status": "Pending Review",
                "model": model,
                "name": name,
                "framework_name": frameworkName
            }
        )
        db.commit()
        
        # Trigger dynamic RAG Ingestion in the background
        if background_tasks:
            background_tasks.add_task(run_rag_ingestion_task, requestId)
            
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database record creation failed: {str(e)}"
        )
            
    return {
        "status": "SUCCESS",
        "requestId": requestId,
        "year": year,
        "files": saved_files
    }

@app.get("/esg/requests")
def get_upload_requests(db: Session = Depends(get_db)):
    try:
        # Fetch all records from upload_request sorted by created_at descending
        query = text("""
            SELECT request_id, folder_path, total_files, status, created_at, report_data, model, name, framework_name
            FROM upload_request
            ORDER BY created_at DESC
        """)
        result = db.execute(query)
        rows = result.fetchall()
        
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        
        requests_list = []
        for row in rows:
            req_id_num = row.request_id
            folder_path = row.folder_path
            total_files = row.total_files
            status = row.status
            created_at = row.created_at
            report_data = row.report_data
            model_val = row.model if hasattr(row, 'model') else 'gemini-3.5'
            name_val = row.name if hasattr(row, 'name') and row.name is not None else ""
            framework_val = row.framework_name if hasattr(row, 'framework_name') and row.framework_name is not None else "VSME (Voluntary Sustainability Reporting Standard for SMEs)"
            
            # Format request ID back to string (e.g. req_12345)
            req_id_str = f"req_{req_id_num}"
            
            # Resolve documents directory and read files
            docs = []
            abs_folder_path = os.path.join(base_dir, folder_path)
            
            if os.path.exists(abs_folder_path) and os.path.isdir(abs_folder_path):
                try:
                    for filename in os.listdir(abs_folder_path):
                        if filename.startswith('.'):
                            continue
                        filepath = os.path.join(abs_folder_path, filename)
                        if os.path.isfile(filepath):
                            size_bytes = os.path.getsize(filepath)
                            size_mb = size_bytes / (1024 * 1024)
                            size_str = f"{size_mb:.1f} MB" if size_mb >= 0.1 else f"{size_bytes / 1024:.1f} KB"
                            docs.append({"name": filename, "size": size_str})
                except Exception as e:
                    print(f"Error reading files in {abs_folder_path}: {e}")
            
            # Resolve versioned PDF files in esg_report/{requestId}/
            generated_reports = []
            pdf_dir = os.path.join(base_dir, "esg_report", req_id_str)
            if os.path.exists(pdf_dir) and os.path.isdir(pdf_dir):
                import glob
                import re
                existing_pdfs = glob.glob(os.path.join(pdf_dir, "esg_report-v*.pdf"))
                versioned_files = []
                for filepath in existing_pdfs:
                    fname = os.path.basename(filepath)
                    match = re.search(r'-v(\d+)(?:-([\w-]+))?\.pdf$', fname)
                    if match:
                        versioned_files.append((int(match.group(1)), fname))
                if versioned_files:
                    versioned_files.sort(key=lambda x: x[0], reverse=True) # Descending order: latest first
                    generated_reports = [x[1] for x in versioned_files]
            
            # Format the created_at timestamp: e.g. "Jul 17, 2026"
            date_uploaded = created_at.strftime("%b %d, %Y") if created_at else ""
            year = created_at.year if created_at else 2026
            
            parsed_report = None
            if report_data:
                try:
                    import json
                    parsed_report = json.loads(report_data)
                except Exception:
                    parsed_report = report_data
            
            requests_list.append({
                "id": req_id_str,
                "year": year,
                "status": status,
                "numDocs": len(docs) if docs else total_files,
                "docs": docs,
                "dateUploaded": date_uploaded,
                "reportData": parsed_report,
                "generatedReports": generated_reports,
                "model": model_val,
                "name": name_val,
                "frameworkName": framework_val
            })
            
        return requests_list
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch upload requests: {str(e)}"
        )

@app.delete("/esg/requests/{requestId}")
def delete_upload_request(requestId: str, db: Session = Depends(get_db)):
    # Convert string ID to numeric
    try:
        numeric_request_id = int(requestId.replace("req_", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID format")
        
    try:
        # 1. Fetch record to get folder path so we can delete the files
        query = text("""
            SELECT folder_path FROM upload_request WHERE request_id = :request_id
        """)
        row = db.execute(query, {"request_id": numeric_request_id}).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Request not found")
            
        folder_path = row.folder_path
        
        # 2. Delete the database row
        delete_query = text("""
            DELETE FROM upload_request WHERE request_id = :request_id
        """)
        db.execute(delete_query, {"request_id": numeric_request_id})
        db.commit()
        
        # 3. Safely delete the files on disk
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        abs_folder_path = os.path.join(base_dir, folder_path)
        if os.path.exists(abs_folder_path):
            shutil.rmtree(abs_folder_path)
            
        # 4. Safely delete the chroma vector store directory if it exists
        for model in ["llama3", "gemini-3.5"]:
            chroma_dir = os.path.join(base_dir, "rag_chroma_db", f"{requestId}_{model}")
            if os.path.exists(chroma_dir):
                shutil.rmtree(chroma_dir)
            
        # 5. Safely delete the generated report directory if it exists
        report_dir = os.path.join(base_dir, "esg_report", requestId)
        if os.path.exists(report_dir):
            shutil.rmtree(report_dir)
            
        return {"status": "SUCCESS", "message": f"Request {requestId} and its documents deleted successfully."}
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete request: {str(e)}")

@app.put("/esg/requests/{requestId}/model")
def update_request_model(
    requestId: str,
    model: str,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    try:
        numeric_request_id = int(requestId.replace("req_", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID format")
        
    # Check if request exists
    query = text("SELECT id FROM upload_request WHERE request_id = :request_id")
    row = db.execute(query, {"request_id": numeric_request_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
        
    # Update request model
    update_query = text("""
        UPDATE upload_request
        SET model = :model,
            updated_at = CURRENT_TIMESTAMP
        WHERE request_id = :request_id
    """)
    db.execute(update_query, {"request_id": numeric_request_id, "model": model})
    db.commit()
    
    # Queue RAG ingestion for this newly selected model
    if background_tasks:
        background_tasks.add_task(run_ingestion_for_model, requestId, model)
    else:
        run_ingestion_for_model(requestId, model)
    
    return {"status": "SUCCESS", "message": f"Successfully switched model to {model} and queued RAG ingestion."}

@app.get("/esg/requests/{requestId}/files/{filename}")
def download_request_file(requestId: str, filename: str, db: Session = Depends(get_db)):
    # Convert string ID to numeric
    try:
        numeric_request_id = int(requestId.replace("req_", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID format")
        
    try:
        # 1. Fetch record to get folder path so we can locate the file
        query = text("""
            SELECT folder_path FROM upload_request WHERE request_id = :request_id
        """)
        row = db.execute(query, {"request_id": numeric_request_id}).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Request not found")
            
        folder_path = row.folder_path
        
        # 2. Resolve absolute path of file
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        file_path = os.path.join(base_dir, folder_path, filename)
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path, filename=filename, content_disposition_type="inline")
        else:
            raise HTTPException(status_code=404, detail=f"File '{filename}' not found on disk")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download document: {str(e)}")

@app.get("/esg/requests/{requestId}/files/{filename}/view")
def view_request_file(requestId: str, filename: str, db: Session = Depends(get_db)):
    # Convert string ID to numeric
    try:
        numeric_request_id = int(requestId.replace("req_", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID format")
        
    try:
        # 1. Fetch record to get folder path so we can locate the file
        query = text("""
            SELECT folder_path FROM upload_request WHERE request_id = :request_id
        """)
        row = db.execute(query, {"request_id": numeric_request_id}).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Request not found")
            
        folder_path = row.folder_path
        
        # 2. Resolve absolute path of file
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        file_path = os.path.join(base_dir, folder_path, filename)
        
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            raise HTTPException(status_code=404, detail=f"File '{filename}' not found on disk")
            
        ext = os.path.splitext(filename)[1].lower()
        
        media_types = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".txt": "text/plain; charset=utf-8",
            ".log": "text/plain; charset=utf-8",
            ".csv": "text/csv; charset=utf-8",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".svg": "image/svg+xml"
        }
        media_type = media_types.get(ext, "application/octet-stream")
        
        return FileResponse(
            file_path,
            media_type=media_type,
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "Access-Control-Allow-Origin": "*"
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to view document: {str(e)}")

@app.delete("/esg/requests/{requestId}/files/{filename}")
def delete_request_file(requestId: str, filename: str, background_tasks: BackgroundTasks = None, db: Session = Depends(get_db)):
    # Convert string ID to numeric
    try:
        numeric_request_id = int(requestId.replace("req_", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID format")
        
    try:
        # 1. Fetch record to get folder path so we can resolve the file
        query = text("""
            SELECT folder_path FROM upload_request WHERE request_id = :request_id
        """)
        row = db.execute(query, {"request_id": numeric_request_id}).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Request not found")
            
        folder_path = row.folder_path
        
        # 2. Resolve absolute path of file and delete it
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        file_path = os.path.join(base_dir, folder_path, filename)
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.remove(file_path)
        else:
            raise HTTPException(status_code=404, detail=f"File '{filename}' not found on disk")
            
        # 3. Count remaining files in directory
        abs_folder_path = os.path.join(base_dir, folder_path)
        all_files = []
        if os.path.exists(abs_folder_path):
            all_files = [f for f in os.listdir(abs_folder_path) 
                         if os.path.isfile(os.path.join(abs_folder_path, f)) and not f.startswith(".")]
        total_files_count = len(all_files)
        
        # 4. Update the database row with the new count
        update_query = text("""
            UPDATE upload_request 
            SET total_files = :total_files,
                updated_at = CURRENT_TIMESTAMP
            WHERE request_id = :request_id
        """)
        db.execute(update_query, {"total_files": total_files_count, "request_id": numeric_request_id})
        db.commit()
        
        # Trigger dynamic RAG Ingestion in the background to sync the vector store
        if background_tasks:
            background_tasks.add_task(run_rag_ingestion_task, requestId)
            
        return {"status": "SUCCESS", "message": f"File '{filename}' deleted from request '{requestId}'."}
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")

@app.get("/esg/report/generate/stream")
def generate_esg_report_stream(requestId: str, module: str = "basic", db: Session = Depends(get_db)):
    try:
        numeric_request_id = int(requestId.replace("req_", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID format")
        
    # Check if request exists
    query = text("SELECT id, model FROM upload_request WHERE request_id = :request_id")
    row = db.execute(query, {"request_id": numeric_request_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
        
    model_val = row.model if hasattr(row, 'model') and row.model else 'gemini-3.5'

    import asyncio
    import json

    async def event_generator():
        try:
            # Step 0
            yield f"data: {json.dumps({'step': 0, 'text': 'Initializing RAG pipeline & parsing questionnaire module...'})}\n\n"
            await asyncio.sleep(0.5)
            
            # Step 1
            yield f"data: {json.dumps({'step': 1, 'text': 'Searching ingested documents for disclosures...'})}\n\n"
            await asyncio.sleep(0.5)
            
            # Step 2
            yield f"data: {json.dumps({'step': 2, 'text': 'Analyzing ESG metrics & generating compliance answers...'})}\n\n"
            
            # Since query_report_for_request is synchronous, run in executor
            from app.query.query import query_report_for_request
            loop = asyncio.get_running_loop()
            report_data = await loop.run_in_executor(None, query_report_for_request, requestId, module, model_val)
            
            # Step 3
            yield f"data: {json.dumps({'step': 3, 'text': 'Calculating confidence scores & citations...'})}\n\n"
            await asyncio.sleep(0.5)
            
            # Serialize report data to store in db
            report_data_str = json.dumps(report_data)
            
            # Save report data and update updated_at
            update_query = text("""
                UPDATE upload_request 
                SET report_data = :report_data,
                    status = 'Completed',
                    updated_at = CURRENT_TIMESTAMP
                WHERE request_id = :request_id
            """)
            db.execute(update_query, {
                "request_id": numeric_request_id,
                "report_data": report_data_str
            })
            db.commit()
            
            # Step 4
            yield f"data: {json.dumps({'step': 4, 'text': 'Formatting report layout & compiling professional PDF...'})}\n\n"
            
            # Try to pre-generate the professional PDF report
            pdf_generated = True
            try:
                from app.query.report_generator import generate_report_json, create_pdf_from_json
                from app.core.utils import ReportUtility
                report_json = await loop.run_in_executor(None, generate_report_json, requestId, module, model_val)
                report_json = ReportUtility.enrich_report_json_from_db(report_json, report_data)
                
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                pdf_dir = os.path.join(base_dir, "esg_report", requestId)
                os.makedirs(pdf_dir, exist_ok=True)
                
                # Find next version number
                import glob
                import re
                existing_pdfs = glob.glob(os.path.join(pdf_dir, "esg_report-v*.pdf"))
                versions = []
                for filepath in existing_pdfs:
                    fname = os.path.basename(filepath)
                    match = re.search(r'-v(\d+)(?:-([\w-]+))?\.pdf$', fname)
                    if match:
                        versions.append(int(match.group(1)))
                next_version = max(versions) + 1 if versions else 1
                
                version_filename = f"esg_report-v{next_version}-{module}.pdf"
                pdf_path = os.path.join(pdf_dir, version_filename)
                
                await loop.run_in_executor(None, create_pdf_from_json, report_json, pdf_path)
                
                # Cache the report_json to disk
                json_path = os.path.join(pdf_dir, "report_data.json")
                with open(json_path, "w", encoding="utf-8") as jf:
                    json.dump(report_json, jf, indent=2)
            except Exception as pdf_err:
                print(f"Warning: PDF report pre-generation failed: {str(pdf_err)}")
                pdf_generated = False
                
            # Step 5
            yield f"data: {json.dumps({'step': 5, 'text': 'Saving generated version & finalizing status...'})}\n\n"
            await asyncio.sleep(0.5)
            
            # Final response
            final_payload = {
                "step": 6,
                "completed": True,
                "status": "SUCCESS",
                "pdf_generated": pdf_generated,
                "data": report_data
            }
            yield f"data: {json.dumps(final_payload)}\n\n"
            
        except Exception as err:
            try:
                db.rollback()
            except Exception:
                pass
            yield f"data: {json.dumps({'step': -1, 'error': True, 'text': str(err)})}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/esg/report/generate")
def generate_esg_report(requestId: str, module: str = "basic", db: Session = Depends(get_db)):
    try:
        numeric_request_id = int(requestId.replace("req_", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID format")
        
    try:
        # Check if request exists
        query = text("SELECT id, model FROM upload_request WHERE request_id = :request_id")
        row = db.execute(query, {"request_id": numeric_request_id}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Request not found")
            
        model_val = row.model if hasattr(row, 'model') and row.model else 'gemini-3.5'
            
        # Run RAG querying using query.py (for workforce list at details bottom)
        from app.query.query import query_report_for_request
        report_data = query_report_for_request(requestId, module=module, model=model_val)
        
        # Serialize report data to store in db
        import json
        report_data_str = json.dumps(report_data)
        
        # Save report data and update updated_at
        print("Updating new report data to database...")
        update_query = text("""
            UPDATE upload_request 
            SET report_data = :report_data,
                status = 'Completed',
                updated_at = CURRENT_TIMESTAMP
            WHERE request_id = :request_id
        """)
        db.execute(update_query, {
            "request_id": numeric_request_id,
            "report_data": report_data_str
        })
        db.commit()

        # Try to pre-generate the professional PDF report using report.txt template
        pdf_generated = True
        try:
            from app.query.report_generator import generate_report_json, create_pdf_from_json
            from app.core.utils import ReportUtility
            report_json = generate_report_json(requestId, module=module, model=model_val)
            report_json = ReportUtility.enrich_report_json_from_db(report_json, report_data)
            
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            pdf_dir = os.path.join(base_dir, "esg_report", requestId)
            os.makedirs(pdf_dir, exist_ok=True)
            
            # Find next version number
            import glob
            import re
            existing_pdfs = glob.glob(os.path.join(pdf_dir, "esg_report-v*.pdf"))
            versions = []
            for filepath in existing_pdfs:
                fname = os.path.basename(filepath)
                match = re.search(r'-v(\d+)(?:-([\w-]+))?\.pdf$', fname)
                if match:
                    versions.append(int(match.group(1)))
            next_version = max(versions) + 1 if versions else 1
            
            version_filename = f"esg_report-v{next_version}-{module}.pdf"
            pdf_path = os.path.join(pdf_dir, version_filename)
            create_pdf_from_json(report_json, pdf_path)
            
            # Cache the report_json to disk
            json_path = os.path.join(pdf_dir, "report_data.json")
            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump(report_json, jf, indent=2)
        except Exception as pdf_err:
            print(f"Warning: PDF report pre-generation failed: {str(pdf_err)}")
            pdf_generated = False
        
        return {
            "status": "SUCCESS", 
            "message": "ESG report generated successfully.",
            "pdf_generated": pdf_generated,
            "data": report_data
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")

@app.get("/esg/requests/{requestId}/report/download")
def download_esg_report(requestId: str, filename: str = None, db: Session = Depends(get_db)):
    try:
        numeric_request_id = int(requestId.replace("req_", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID format")
        
    # Check if request exists
    query = text("SELECT id FROM upload_request WHERE request_id = :request_id")
    row = db.execute(query, {"request_id": numeric_request_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
        
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pdf_dir = os.path.join(base_dir, "esg_report", requestId)
    
    if filename:
        safe_filename = os.path.basename(filename)
        pdf_path = os.path.join(pdf_dir, safe_filename)
        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail=f"Report version '{filename}' not found.")
    else:
        import glob
        import re
        pdf_path = None
        if os.path.exists(pdf_dir):
            existing_pdfs = glob.glob(os.path.join(pdf_dir, "esg_report-v*.pdf"))
            versioned_files = []
            for filepath in existing_pdfs:
                fname = os.path.basename(filepath)
                match = re.search(r'-v(\d+)(?:-([\w-]+))?\.pdf$', fname)
                if match:
                    versioned_files.append((int(match.group(1)), fname))
            if versioned_files:
                versioned_files.sort(reverse=True)
                pdf_path = os.path.join(pdf_dir, versioned_files[0][1])
                
        # Generate version 1 dynamically if no versions exist
        if not pdf_path or not os.path.exists(pdf_path):
            try:
                # Try to resolve module from files or fallback to basic
                module_val = "basic"
                if os.path.exists(pdf_dir):
                    existing_pdfs = glob.glob(os.path.join(pdf_dir, "esg_report-v*.pdf"))
                    if existing_pdfs:
                        latest_file = max(existing_pdfs, key=os.path.getmtime)
                        fname = os.path.basename(latest_file)
                        match = re.search(r'-v\d+-([\w-]+)\.pdf$', fname)
                        if match:
                            module_val = match.group(1)

                from app.query.report_generator import generate_report_json, create_pdf_from_json
                report_json = generate_report_json(requestId, module=module_val)
                os.makedirs(pdf_dir, exist_ok=True)
                pdf_path = os.path.join(pdf_dir, f"esg_report-v1-{module_val}.pdf")
                create_pdf_from_json(report_json, pdf_path)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to generate PDF report: {str(e)}")
                
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF report not found and generation failed.")
        
    import re
    fname = os.path.basename(pdf_path)
    match = re.search(r'(-v\d+(?:-[\w-]+)?\.pdf)$', fname)
    version_suffix = match.group(1) if match else ".pdf"
    download_name = f"ESG_Report_{requestId}{version_suffix}"
    
    return FileResponse(
        pdf_path, 
        media_type="application/pdf", 
        filename=download_name
    )

def parse_questionnaire_file(file_path: str):
    import re
    sections = []
    current_section = None
    
    if not os.path.exists(file_path):
        return []
        
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.endswith("Questionnaire"):
            continue
            
        if re.match(r'^[BC]\d+\.', line):
            current_section = {
                "title": line,
                "questions": []
            }
            sections.append(current_section)
        else:
            if current_section is not None:
                current_section["questions"].append(line)
            else:
                current_section = {
                    "title": "General",
                    "questions": [line]
                }
                sections.append(current_section)
                
    return sections

@app.get("/esg/requests/{requestId}/report/json")
def get_report_json(requestId: str, db: Session = Depends(get_db)):
    try:
        numeric_request_id = int(requestId.replace("req_", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID format")
        
    # Check if request exists
    query = text("SELECT report_data, model FROM upload_request WHERE request_id = :request_id")
    row = db.execute(query, {"request_id": numeric_request_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
        
    model_val = row.model if hasattr(row, 'model') and row.model else 'gemini-3.5'

    # Check disk cache first to prevent redundant LLM generation on page loads
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pdf_dir = os.path.join(base_dir, "esg_report", requestId)
    json_path = os.path.join(pdf_dir, "report_data.json")
    
    # Parse database report data if present for enrichment
    db_report_data = []
    if row.report_data:
        try:
            import json as py_json
            parsed = py_json.loads(row.report_data)
            if isinstance(parsed, dict) and "questionnaire_data" in parsed:
                db_report_data = parsed["questionnaire_data"]
            elif isinstance(parsed, list):
                db_report_data = parsed
        except Exception as pe:
            print(f"Warning: Failed to parse db report_data: {pe}")

    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as jf:
                import json as py_json
                report_json = py_json.load(jf)
                # Enrich cached report json with database questionnaire answers using utility class
                from app.core.utils import ReportUtility
                return ReportUtility.enrich_report_json_from_db(report_json, db_report_data, requestId)
        except Exception as e:
            print(f"Warning: Failed to read cached report_data.json: {e}")

    # Fetch from database report_data column if disk cache is missing
    if row.report_data:
        try:
            import json as py_json
            return py_json.loads(row.report_data)
        except Exception:
            return row.report_data

    return {}

@app.get("/esg/questionnaires")
def get_questionnaires():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    basic_path = os.path.join(base_dir, "questionnaires", "basic.txt")
    comprehensive_path = os.path.join(base_dir, "questionnaires", "comprehensive.txt")
    
    return {
        "basic": parse_questionnaire_file(basic_path),
        "comprehensive": parse_questionnaire_file(comprehensive_path)
    }

@app.get("/")
def read_root():
    return {"message": "ESG Disclosure Assistant API is running"}

@app.get("/health")
def health_check():
    db_connected = verify_connection()
    return {
        "status": "healthy" if db_connected else "unhealthy",
        "database": "connected" if db_connected else "disconnected"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)