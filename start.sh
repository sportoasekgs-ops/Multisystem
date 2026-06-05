#!/bin/bash
export PATH="$HOME/workspace/.pythonlibs/bin:$PATH"
exec gunicorn --config gunicorn_config.py main:app
