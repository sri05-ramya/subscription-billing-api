from fastapi import FastAPI                      #from fastapi import FastAPI loads the FastAPI tool.

app = FastAPI(title="Subscription Billing API")  #app = FastAPI(...) creates our API and gives it a name.


@app.get("/health")                              #@app.get("/health") means “when someone opens /health, run the function below.”
def health():
    return {"status": "ok"}                      #return {"status": "ok"} sends this answer back as JSON.