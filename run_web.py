# Launch one local FastAPI process: python run_web.py
import uvicorn

if __name__ == "__main__":
    uvicorn.run("bingo.web:app", host="127.0.0.1", port=8000, workers=1)