
import random
import time
import requests

BASE_URL = "http://127.0.0.1:8000"

endpoints = [
    "/demo/fast",
    "/demo/slow",
    "/demo/error"
]

TOTAL_REQUESTS = 30

print("Starting traffic simulation...\n")

for i in range(TOTAL_REQUESTS):
    endpoint = random.choice(endpoints)

    try:
        response = requests.get(
            BASE_URL + endpoint,
            timeout=5
        )

        print(
            f"Request {i + 1}/{TOTAL_REQUESTS} | "
            f"Endpoint: {endpoint} | "
            f"Status: {response.status_code}"
        )

    except requests.RequestException as error:
        print(f"Request failed: {error}")

    time.sleep(0.2)

print("\nTraffic simulation completed!")
