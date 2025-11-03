"""
Script di test per l'API longevity Backend

Prima di eseguire questo script:
1. Assicurati che il server sia avviato: python -m uvicorn main:app --reload
2. Crea un file .env con le tue chiavi API
"""

import requests
import json

# URL base del server (locale o Render)
BASE_URL = "http://localhost:8000"  # Cambia con l'URL di Render se necessario

def test_health_check():
    """Testa l'endpoint di health check"""
    print("🧪 Test Health Check...")
    try:
        response = requests.get(f"{BASE_URL}/")
        print(f"✅ Status Code: {response.status_code}")
        print(f"✅ Response: {json.dumps(response.json(), indent=2)}")
        return True
    except Exception as e:
        print(f"❌ Errore: {e}")
        return False

def test_ask_endpoint():
    """Testa l'endpoint /ask"""
    print("\n🧪 Test Endpoint /ask...")
    
    payload = {
        "question": "Qual è l'apporto giornaliero raccomandato di proteine per un adulto?",
        "user_data": {
            "age": 30,
            "weight": 75,
            "height": 175,
            "gender": "maschio",
            "activity_level": "moderato"
        }
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/ask",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"✅ Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Risposta ricevuta:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(f"❌ Errore: {response.text}")
        
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Errore: {e}")
        return False

def test_ask_simple():
    """Testa l'endpoint /ask senza dati biometrici"""
    print("\n🧪 Test Endpoint /ask (senza dati biometrici)...")
    
    payload = {
        "question": "Quali sono i benefici degli omega-3?"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/ask",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"✅ Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Risposta ricevuta:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(f"❌ Errore: {response.text}")
        
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Errore: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 Test API wellneAi Backend")
    print("=" * 50)
    
    # Test health check
    health_ok = test_health_check()
    
    if health_ok:
        # Test endpoint /ask
        test_ask_endpoint()
        test_ask_simple()
    else:
        print("\n❌ Il server non risponde. Assicurati che sia avviato!")
        print("   Avvia il server con: python -m uvicorn main:app --reload")


