import requests

# Default local game address (ensure your port matches the active game settings)
BASE_URL = "http://localhost:64123" 

def get_player_position():
    try:
        # Fetch data from the game's environment endpoint
        data = {"grammiUuid":"5b1d618dfc304ea0adef1cb59fadebbf", "text":"リッキー先生超かっこいい", "timeOut": 60}
        response = requests.post(f"{BASE_URL}/grammi/say", json=data)
        if response.status_code == 200:
            position_data = response.json()
            print(f"Current Position: {position_data}")
            return position_data
        else:
            print(f"Failed to fetch position. Status code: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("Could not connect to Omega Crafter. Is the game running?")

get_player_position()
