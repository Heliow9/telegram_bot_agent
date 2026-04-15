import requests

BASE_URL = "http://127.0.0.1:8000"


def login():
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={
            "email": "admin@aposta.com",
            "password": "123456",
        },
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    print("LOGIN OK")
    print(data)
    return data["access_token"]


def get_summary(token: str):
    response = requests.get(
        f"{BASE_URL}/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    response.raise_for_status()
    print("\nSUMMARY OK")
    print(response.json())


def get_predictions(token: str):
    response = requests.get(
        f"{BASE_URL}/dashboard/predictions?limit=10",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    response.raise_for_status()
    print("\nPREDICTIONS OK")
    print(response.json())


def main():
    token = login()
    get_summary(token)
    get_predictions(token)


if __name__ == "__main__":
    main()