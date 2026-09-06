# SkillProof backend

From this `backend` directory, create/activate a virtual environment and install dependencies:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the local API:

```powershell
.\venv\Scripts\python.exe -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

The API is available at `http://127.0.0.1:8000`, with interactive documentation at `/docs`.
The local frontend on port 3000 is permitted by CORS. Assessment state is in-memory and resets whenever the API restarts.
