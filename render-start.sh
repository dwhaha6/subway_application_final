#!/bin/bash
gunicorn --bind 0.0.0.0:$PORT --workers 2 --chdir subway_app app:app
