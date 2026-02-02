from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://smolib.com",          # Production
        "https://www.smolib.com",      # Production wwg
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "Hello, make changes to the backend"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, port=443)