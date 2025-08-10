## LLM Chess Arena

Run chess battles between LLMs and calculate ELO ratings.

### 1) Setup (simple)
- Install Python 3.9+
- Create `.env` with your key:
  - `OPENROUTER_API_KEY=YOUR_KEY_HERE`
- List model IDs in `models.txt` (one per line)
- Install dependencies:
  - `pip install -r requirements.txt`

### 2) Web UI (play one game and see moves live)
Run the app:

```
python app.py
```

Open `http://127.0.0.1:5000`, pick two models, click “Start Battle”.

Notes:
- Games are saved to Google Cloud Storage as PGN files (bucket name is set in `gcp.py`).
- Ratings are also saved to GCS (`ratings.json`).

### 3) CLI (run a small tournament)

```
python main.py --matches 5
```

This plays random pairings and updates Elo ratings.

### How it works (very short)
- `client.py`: talks to OpenRouter using the OpenAI SDK
- `prompts.py`: simple system/user prompts for chess
- `match.py`: plays a game, move by move
- `app.py`: tiny Flask server streaming moves to the browser (no threads, simple SSE)
- `ratings.py`: Elo update and stats
- `gcp.py`: read/write JSON and PGN to Google Cloud Storage

