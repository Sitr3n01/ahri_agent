from google import genai
import os
from dotenv import load_dotenv
from pathlib import Path

def inspect_models():
    # Caminho absoluto para o .env na raiz do monorepo
    root_env = Path(__file__).parent.parent.parent / ".env"
    print(f"Loading .env from: {root_env}")
    load_dotenv(root_env)
    
    api_key = os.getenv("GEMINI_API_KEY_PAID") or os.getenv("GOOGLE_AI_STUDIO_API_KEY")
    if not api_key:
        print("No API key found in .env")
        # Mostra o que tem no env pra depurar
        # print(f"Env keys: {list(os.environ.keys())}")
        return

    client = genai.Client(api_key=api_key)
    try:
        models = list(client.models.list())
        if not models:
            print("No models found")
            return
        
        m = models[0]
        print(f"Inspecting model: {m.name}")
        print("Attributes found in m (filtered):")
        # O objeto Model no google-genai 1.0+ é do tipo Model (pydantic)
        # Vamos ver o que tem nele
        attrs = [a for a in dir(m) if not a.startswith("_")]
        for attr in attrs:
            try:
                val = getattr(m, attr)
                print(f"  {attr}: {type(val)} = {val}")
            except Exception as e:
                print(f"  {attr}: Error accessing: {e}")
                    
    except Exception as e:
        print(f"Error listing models: {e}")

if __name__ == "__main__":
    inspect_models()
