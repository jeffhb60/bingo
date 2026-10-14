# Entry point for Fast-API
import uvicorn

if __name__ == "__main__":
    uvicorn.run("bingo.web:app", host="127.0.0.1", port=8000)