import os
import sys
from pathlib import Path

# Ensure root directory is in sys.path
BASE_DIR = Path(__file__).parent.resolve()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Import the existing FastAPI server (which mounts frontend/dist on /)
from server import app as fastapi_app

# ZeroGPU compatibility for Hugging Face Spaces
try:
    import spaces
    @spaces.GPU(duration=1)
    def dummy_gpu():
        return None
except Exception:
    pass

# Gradio interface mounting
try:
    import gradio as gr

    # Define a clean companion Gradio interface mounted at /gradio
    with gr.Blocks(title="PowerPilot AI - Companion Engine") as demo:
        gr.Markdown(
            """
            # ⚡ PowerPilot AI
            ### Autonomous Big Data & Power BI Agent
            
            The full interactive React 19 analytics dashboard is running at the root URL.
            
            - 👉 **[Launch Full Interactive Dashboard](/)**
            - 📊 **Engine**: Single-Pass DuckDB SIMD Profiler, Polars Streaming Cleaner, Modeler Agent, PBIP Builder.
            - 📁 **Endpoints**: /api/pipeline/run, /api/health, /api/pipeline/artifacts/{run_id}/{artifact_type}
            """
        )
        
        with gr.Row():
            gr.Button("🚀 Open PowerPilot Dashboard", variant="primary", link="/")

    # Mount Gradio at /gradio so Hugging Face Gradio SDK finds a valid Gradio application
    app = gr.mount_gradio_app(fastapi_app, demo, path="/gradio")
except Exception as err:
    print(f"[PowerPilot] Gradio mounting warning: {err}")
    app = fastapi_app

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 7860))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"[PowerPilot] Starting Unified Server on {host}:{port}...")
    uvicorn.run(app, host=host, port=port, reload=False)
