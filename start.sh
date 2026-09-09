#!/bin/bash
python3 /app/telegram_poll.py &
gunicorn -w 2 -b 0.0.0.0:18090 --timeout 120 app:app

